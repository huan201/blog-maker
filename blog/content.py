"""文章读取：frontmatter 解析 + 文章模型。

相对旧版本修正了几个坑：
1. 旧版用 text.split("---", 2) 判断 frontmatter，正文里出现 --- 就会错位；
   现在严格只认文件开头的第一行分隔符。
2. 旧版没有日期校验，2026-13-45 也能参与排序；现在解析失败会降级并给出警告。
3. 旧版标签直接用逗号切分，不支持中文逗号和顿号；现在都支持。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .utils import (
    count_chars,
    format_date,
    parse_date,
    plain_text,
    reading_minutes,
    safe_post_stem,
    shorten,
)

# frontmatter 里允许出现的行尾分隔符
_FRONTMATTER_END = ("---", "...")
_TAG_SPLIT_CHARS = ",，、;；|"

# 不是文章、但可能放在 content/ 里的文件
RESERVED_FILES = {"friends.txt", "views.json", "README.md"}
# 约定：以 _ 开头的 .txt 是私有草稿，构建时一律跳过（配合 .gitignore 使用）


@dataclass
class Post:
    """一篇文章（已解析 frontmatter，正文仍是 Markdown 源）。"""

    source: Path
    slug: str
    title: str
    date: date | None
    tags: list = field(default_factory=list)
    body: str = ""
    summary: str = ""
    draft: bool = False
    pinned: bool = False
    words: int = 0
    minutes: int = 1
    plain: str = ""
    warnings: list = field(default_factory=list)

    # --- 输出路径（相对站点根）------------------------------------
    @property
    def filename(self) -> str:
        return self.slug + ".html"

    @property
    def html_file(self) -> str:
        return "posts/" + self.filename

    @property
    def date_text(self) -> str:
        return format_date(self.date)

    @property
    def tag_text(self) -> str:
        return "、".join(self.tags)

    def sort_key(self):
        """置顶优先，然后按日期降序（无日期的排最后）。"""
        return (
            1 if self.pinned else 0,
            self.date.toordinal() if self.date else 0,
            self.slug,
        )

    def to_index_entry(self, tags_by_slug: dict) -> dict:
        """导出给前端（搜索索引 / 阅读计数）用的精简结构。"""
        from .utils import url_quote_path

        return {
            "title": self.title,
            "url": url_quote_path(self.html_file),
            "date": self.date.isoformat() if self.date else "",
            "date_text": self.date_text,
            "tags": list(self.tags),
            "tag_links": [
                {
                    "name": tag,
                    "url": url_quote_path("tags/{}.html".format(tags_by_slug.get(tag, "index"))),
                }
                for tag in self.tags
            ],
            "summary": self.summary,
            "words": self.words,
            "minutes": self.minutes,
            "slug": self.slug,
            "text": self.plain,
        }


def parse_frontmatter(text: str) -> tuple:
    """拆分 frontmatter 和正文。

    返回 (meta: dict, body: str)。严格要求文件第一行是分隔符，
    否则整段都当作正文 —— 这是旧版最容易出错的地方。
    """
    raw = text.lstrip("\ufeff")
    lines = raw.splitlines()

    if not lines or lines[0].strip() not in ("---",):
        return {}, raw.strip()

    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() in _FRONTMATTER_END:
            end = index
            break

    if end is None:
        # 只有开头没有结尾，按无 frontmatter 处理，避免吞掉正文
        return {}, raw.strip()

    meta: dict = {}
    last_key = None
    for line in lines[1:end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and last_key:
            # 支持 YAML 风格的列表写法：tags:\n  - python
            meta.setdefault(last_key, "")
            existing = meta[last_key]
            item = stripped[2:].strip()
            meta[last_key] = (existing + "," + item).strip(",") if existing else item
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        meta[key] = value
        last_key = key

    body = "\n".join(lines[end + 1:]).strip()
    return meta, body


_TAG_SPLIT_RE = re.compile("[{}]".format(_TAG_SPLIT_CHARS))


def split_tags(raw: str) -> list:
    """把一行标签拆成列表，兼容中英文逗号、顿号、分号和竖线。"""
    parts = _TAG_SPLIT_RE.split(str(raw or ""))
    seen = set()
    tags = []
    for part in parts:
        tag = part.strip().strip("#").strip()
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y", "是")


def load_posts(content_dir: Path, include_drafts: bool = False) -> list:
    """读取 content/ 下所有 .txt 文章，按置顶 + 日期降序返回。"""
    content_dir = Path(content_dir)
    if not content_dir.is_dir():
        return []

    posts = []
    used_slugs: set = set()

    for txt in sorted(content_dir.glob("*.txt")):
        # 下划线开头的文件是"私有草稿"，不参与构建，也不进编辑器列表
        if txt.name in RESERVED_FILES or txt.name.startswith("_"):
            continue
        try:
            raw = txt.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print("[警告] 跳过 {}：读取失败（{}）".format(txt.name, exc))
            continue

        meta, body = parse_frontmatter(raw)
        warnings = []

        title = meta.get("title", "").strip() or txt.stem
        if not meta.get("title"):
            warnings.append("缺少 title，已用文件名代替")

        parsed_date = parse_date(meta.get("date"))
        if parsed_date is None:
            if meta.get("date"):
                warnings.append("日期 {!r} 无法解析，已按无日期处理".format(meta.get("date")))
            else:
                warnings.append("缺少 date 字段")

        slug = safe_post_stem(txt.stem)
        if slug != txt.stem:
            warnings.append("文件名包含不安全字符，输出为 {}.html".format(slug))
        if slug in used_slugs:
            warnings.append("输出文件名重复：{}".format(slug))
        used_slugs.add(slug)

        tags = split_tags(meta.get("tags", ""))
        is_draft = _truthy(meta.get("draft", ""))
        if is_draft and not include_drafts:
            continue

        plain = plain_text(body)
        words = count_chars(plain)
        summary = meta.get("summary") or meta.get("description") or ""
        if not summary:
            summary = shorten(plain, 110)

        posts.append(
            Post(
                source=txt,
                slug=slug,
                title=title,
                date=parsed_date,
                tags=tags,
                body=body,
                summary=summary,
                draft=is_draft,
                pinned=_truthy(meta.get("pinned", "")),
                words=words,
                minutes=reading_minutes(words),
                plain=shorten(plain, 4000),
                warnings=warnings,
            )
        )

    posts.sort(key=lambda p: p.sort_key(), reverse=True)
    return posts


def collect_tags(posts: list) -> dict:
    """tag 名 -> 文章列表。"""
    tags: dict = {}
    for post in posts:
        for tag in post.tags:
            tags.setdefault(tag, []).append(post)
    return tags


def load_views_seed(seed_path: Path) -> dict:
    """读取可选的阅读量基线文件（content/views.json）。

    作用：把历史阅读量固化进仓库，即使访客清空浏览器缓存、
    或者换了一台设备，页面上显示的阅读次数也不会归零。
    格式：{"mlp": 128, "week4": 32}
    """
    seed_path = Path(seed_path)
    if not seed_path.is_file():
        return {}
    try:
        data = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("[警告] 阅读基线 {} 读取失败：{}".format(seed_path.name, exc))
        return {}
    if not isinstance(data, dict):
        return {}
    result = {}
    for key, value in data.items():
        try:
            result[str(key)] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return result
