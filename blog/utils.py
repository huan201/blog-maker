"""通用工具函数：路径安全、slug、日期、文本处理。

这个模块刻意不依赖项目里的其它模块，方便单独测试和复用。
"""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

__all__ = [
    "escape_html",
    "slugify",
    "unique_slug",
    "safe_post_stem",
    "parse_date",
    "format_date",
    "rfc822",
    "count_chars",
    "reading_minutes",
    "plain_text",
    "shorten",
    "join_url",
    "url_quote_path",
    "safe_join",
]

# --- HTML / 文本 ---------------------------------------------------------

_HTML_TAG = re.compile(r"<[^>]+>")
_CODE_FENCE = re.compile(r"^[ ]*(```|~~~).*$[\s\S]*?^[ ]*\1.*$", re.MULTILINE)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_BLOCK_MATH = re.compile(r"\$\$[\s\S]*?\$\$")
_INLINE_MATH = re.compile(r"\$[^$\n]+\$")
_IMAGE_MD = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_MD = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_MULTI_WS = re.compile(r"[ \t\u3000]+")
_MULTI_NL = re.compile(r"\n{3,}")


def escape_html(value: object) -> str:
    """HTML 转义（包含引号），可安全用于属性值与标签之间。"""
    return html.escape(str(value), quote=True)


def plain_text(markdown_text: str) -> str:
    """把 Markdown 粗略转成纯文本，用于摘要与搜索索引。"""
    text = _CODE_FENCE.sub(" ", markdown_text)
    text = _INLINE_CODE.sub(" ", text)
    text = _BLOCK_MATH.sub(" ", text)
    text = _INLINE_MATH.sub(" ", text)
    text = _IMAGE_MD.sub(" ", text)
    text = _LINK_MD.sub(r"\1", text)
    text = re.sub(r"^[ ]{0,3}#{1,6}[ ]*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ ]{0,3}>[ ]?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ ]*[-*+][ ]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ ]*\d+\.[ ]+", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("__", "").replace("~~", "")
    text = text.replace("`", "")
    text = _HTML_TAG.sub(" ", text)
    text = text.replace("&nbsp;", " ")
    text = _MULTI_WS.sub(" ", text)
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


def shorten(text: str, limit: int = 120, suffix: str = "…") -> str:
    """按字符数截断，尽量在标点或空格处断开。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    for mark in ("。", "！", "？", "；", "，", ".", "!", "?", ";", ",", " "):
        pos = head.rfind(mark)
        if pos >= limit // 2:
            return head[: pos + 1].rstrip() + suffix
    return head.rstrip() + suffix


def count_chars(text: str) -> int:
    """统计非空白字符数（中英文都按字符计，符合中文习惯）。"""
    return len(re.sub(r"\s+", "", text))


def reading_minutes(chars: int, chars_per_minute: int = 400) -> int:
    """估算阅读时长（分钟，至少 1 分钟）。"""
    return max(1, round(chars / chars_per_minute))


# --- slug / 文件名 -------------------------------------------------------

_UNSAFE_SLUG = re.compile(r"[\\/:*?\"<>|#%&{}$!'@+`^=~\[\]\s\x00-\x1f]+")
_MULTI_DASH = re.compile(r"-{2,}")
_BAD_STEM = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


def slugify(text: str, fallback: str = "item") -> str:
    """把标题/标签名变成安全的文件名片段。

    保留中文、字母和数字，这样 URL 依然可读；
    只把路径分隔符、空白以及 URL / shell 里容易出问题的字符折叠成短横线。
    """
    normalized = unicodedata.normalize("NFKC", str(text)).strip()
    normalized = _UNSAFE_SLUG.sub("-", normalized)
    normalized = _MULTI_DASH.sub("-", normalized).strip("-._ ")
    if not normalized:
        normalized = fallback
    return normalized[:80]


def unique_slug(base: str, used: set) -> str:
    """同名冲突时追加序号，保证输出文件名唯一。"""
    candidate = base
    index = 2
    while candidate.lower() in used:
        candidate = "{}-{}".format(base, index)
        index += 1
    used.add(candidate.lower())
    return candidate


def safe_post_stem(stem: str) -> str:
    """文章输出文件直接沿用源文件名，保持 URL 稳定（评论/计数不会失效）。"""
    cleaned = _BAD_STEM.sub("-", stem).strip()
    return cleaned or "post"


# --- 日期 ---------------------------------------------------------------

_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")


def parse_date(value: object) -> date | None:
    """宽松解析日期；无法解析时返回 None（调用方负责降级）。"""
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace("/", "-").replace(".", "-")
    text = text.split("T")[0].split(" ")[0]
    match = _DATE_RE.match(text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def format_date(value: date | None, missing: str = "日期未填") -> str:
    """人类可读的中文日期。"""
    if value is None:
        return missing
    return "{} 年 {} 月 {} 日".format(value.year, value.month, value.day)


def rfc822(value: date | None) -> str:
    """RSS 需要的 RFC 822 时间格式。"""
    moment = datetime(value.year, value.month, value.day) if value else datetime.now()
    moment = moment.replace(tzinfo=timezone.utc)
    return moment.strftime("%a, %d %b %Y %H:%M:%S +0000")


# --- URL ----------------------------------------------------------------

def join_url(base: str, path: str) -> str:
    """拼接站点根地址和相对路径。"""
    if not base:
        return path
    return base.rstrip("/") + "/" + path.lstrip("/")


def url_quote_path(path: str) -> str:
    """对路径中的中文等字符做百分号编码，保留斜杠。"""
    return quote(path, safe="/-._~")


def safe_join(root: Path, *parts: str) -> Path:
    """把用户输入拼进目录，并确保结果不会逃出 root（防路径穿越）。"""
    root = Path(root).resolve()
    candidate = root.joinpath(*parts).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("路径越界: {}".format(candidate))
    return candidate
