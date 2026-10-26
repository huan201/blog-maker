"""站点配置。

所有可自定义的东西都集中在项目根目录的 blog.config.json 里，
本模块负责把它和内置默认值做深度合并，并把相对路径解析成绝对路径。

设计原则：**任何配置缺失都不应该让构建崩溃**，只降级并在 check 命令里提示。
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

CONFIG_FILENAME = "blog.config.json"

DEFAULTS = {
    "site": {
        "title": "我的博客",
        "subtitle": "记录学习与思考",
        "description": "一个用 Python 手写的极简静态博客",
        "author": "",
        "language": "zh-CN",
        # 站点根地址，用于 RSS / sitemap / Open Graph 的绝对链接
        "url": "",
        # GitHub Pages 部署在子路径时填 /仓库名/，部署在根域名时填 /
        "base_path": "/",
        "github": "",
        "email": "",
        "keywords": "",
        "footer": "",
    },
    "build": {
        "content_dir": "content",
        "templates_dir": "templates",
        "static_dir": "static",
        "output_dir": "dist",
        "include_drafts": False,
        "page_size": 0,
    },
    "markdown": {
        "allow_html": True,
        "footnotes": True,
        "tables": True,
        "task_lists": True,
        "strikethrough": True,
        "autolink": True,
        "math": True,
    },
    "comments": {
        "enabled": True,
        # utterances: 只需要仓库名，最简单
        # giscus:      需要 repo_id / category_id，功能更全
        "provider": "utterances",
        "repo": "huan201/blog-maker",
        "repo_id": "",
        "category": "Announcements",
        "category_id": "",
        "mapping": "pathname",
        "issue_term": "pathname",
        "label": "comment",
        "reactions_enabled": True,
        "input_position": "top",
        "lazy": True,
    },
    "metrics": {
        "enabled": True,
        # local: 仅浏览器本地（零依赖、永不丢失，默认）
        # abacus / goatcounter / custom: 全局计数（跨设备共享）
        "provider": "local",
        "namespace": "huan201-blog",
        "site_code": "",
        "endpoint": "",
        "seed_file": "content/views.json",
    },
    "theme": {
        "accent": "#0071e3",
        "appearance": "auto",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并：override 里的值覆盖 base，dict 递归，其它类型直接替换。"""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """配置对象，支持 blog.get("site.title") 这种点号取值。"""

    def __init__(self, data: dict, root: Path, source: Path | None = None):
        self._data = data
        self.root = Path(root).resolve()
        self.source = source

    # --- 基础访问 ---------------------------------------------------
    def get(self, dotted: str, default=None):
        node = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def section(self, name: str) -> dict:
        value = self._data.get(name)
        return value if isinstance(value, dict) else {}

    def as_dict(self) -> dict:
        return copy.deepcopy(self._data)

    def with_overrides(self, overrides: dict) -> "Config":
        return Config(_deep_merge(self._data, overrides), self.root, self.source)

    # --- 路径 -------------------------------------------------------
    def path(self, key: str, default: str) -> Path:
        """把 build.* 里的相对路径解析成项目内的绝对路径。"""
        value = self.get("build." + key, default) or default
        candidate = Path(value)
        return candidate if candidate.is_absolute() else (self.root / candidate)

    @property
    def content_dir(self) -> Path:
        return self.path("content_dir", "content")

    @property
    def templates_dir(self) -> Path:
        return self.path("templates_dir", "templates")

    @property
    def static_dir(self) -> Path:
        return self.path("static_dir", "static")

    @property
    def output_dir(self) -> Path:
        return self.path("output_dir", "dist")

    # --- URL --------------------------------------------------------
    @property
    def base_url(self) -> str:
        """站点的绝对根地址（不带结尾斜杠），没配置时返回空字符串。"""
        url = str(self.get("site.url", "") or "").strip()
        return url.rstrip("/")

    def site_url(self, relative: str) -> str:
        """生成绝对链接；site.url 没配置时退化成相对链接。"""
        relative = relative.lstrip("/")
        if not self.base_url:
            return relative
        return self.base_url + "/" + relative

    @property
    def base_path(self) -> str:
        path = str(self.get("site.base_path", "/") or "/")
        if not path.startswith("/"):
            path = "/" + path
        if not path.endswith("/"):
            path += "/"
        return path


def load_config(root: Path | str = ".", config_file: str | None = None) -> Config:
    """读取并合并配置。找不到配置文件时使用默认值（不会报错）。"""
    root = Path(root).resolve()
    source = None
    overrides: dict = {}

    if config_file:
        candidate = Path(config_file)
        if not candidate.is_absolute():
            candidate = root / candidate
    else:
        candidate = root / CONFIG_FILENAME

    if candidate.is_file():
        try:
            raw = candidate.read_text(encoding="utf-8")
            parsed = json.loads(raw) if raw.strip() else {}
            if isinstance(parsed, dict):
                overrides = parsed
            source = candidate
        except json.JSONDecodeError as exc:
            raise SystemExit(
                "{} 不是合法的 JSON：第 {} 行第 {} 列，{}\n"
                "提示：不要用记事本之外的编辑器加注释，JSON 不支持注释。".format(
                    candidate.name, exc.lineno, exc.colno, exc.msg
                )
            )

    # 环境变量可以覆盖关键配置，方便 CI 或临时调试
    env_url = os.environ.get("BLOG_SITE_URL")
    if env_url:
        overrides.setdefault("site", {})["url"] = env_url

    return Config(_deep_merge(DEFAULTS, overrides), root, source)


def validate(config: Config) -> list:
    """返回配置层面的警告列表（check 命令会打印出来）。"""
    warnings = []

    url = config.get("site.url", "")
    if not url:
        warnings.append(
            "site.url 为空：RSS / sitemap / Open Graph 会退化成相对链接，"
            "建议填写成 https://<用户名>.github.io/ 或 https://<用户名>.github.io/<仓库>/"
        )

    provider = config.get("comments.provider", "none")
    if config.get("comments.enabled", True):
        if provider not in ("giscus", "utterances", "none"):
            warnings.append("comments.provider 只支持 giscus / utterances / none，当前为 {!r}".format(provider))
        elif provider in ("giscus", "utterances") and not config.get("comments.repo"):
            warnings.append("评论已开启但 comments.repo 为空，页面会显示配置提示而不会加载评论框")
        if provider == "giscus" and not (config.get("comments.repo_id") and config.get("comments.category_id")):
            warnings.append(
                "comments.provider 为 giscus 但缺少 repo_id / category_id，"
                "将自动降级为 utterances（同样存放在 GitHub，不会丢数据）"
            )

    metric_provider = config.get("metrics.provider", "local")
    if metric_provider not in ("local", "abacus", "goatcounter", "custom"):
        warnings.append("metrics.provider 只支持 local / abacus / goatcounter / custom，当前为 {!r}".format(metric_provider))
    if metric_provider == "goatcounter" and not config.get("metrics.site_code"):
        warnings.append("metrics.provider 为 goatcounter 但缺少 metrics.site_code，将回退到本地计数")
    if metric_provider == "custom" and not config.get("metrics.endpoint"):
        warnings.append("metrics.provider 为 custom 但缺少 metrics.endpoint，将回退到本地计数")

    for key in ("content_dir", "templates_dir"):
        path = config.path(key, key)
        if not path.is_dir():
            warnings.append("目录不存在：{}（{}）".format(path, key))

    return warnings
