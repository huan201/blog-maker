r"""Markdown 渲染。

旧版本这里有一堆问题，重构后做了这些事：

* 用 mistune 官方的 math 插件代替手写的"下划线转义"，
  公式里的 x_i 不会再被吃成斜体，代码块里的内容也完全不受影响。
* LaTeX 的 \[ \] \( \) 只在非代码区域转换，不会破坏代码示例。
* 标题自动生成锚点 id 并收集目录（TOC）。
* 代码块自动带上语言标签和复制按钮的外壳（无需 JS 也能看）。
* 表格外面包一层可横向滚动的容器，手机上不会撑破布局。
* 站外链接自动补 target=_blank 和 rel=noopener。
* 图片自动补 loading=lazy。

math 插件输出的是 \( \) 与 $$ $$，所以前端 MathJax 的 inlineMath 要同时配置这两种。
"""
from __future__ import annotations

import re

import mistune

from .utils import escape_html, slugify

# 代码围栏与行内代码：这两块里的内容必须原样保留
_FENCE = re.compile(r"^(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"(`+)[^`\n]*?\1")

_TABLE = re.compile(r"(<table[\s\S]*?</table>)")
_ASSET_ATTR = re.compile(r'(src|href)="(?!https?:|//|data:|#|mailto:)([^"]*)"')
_EXTERNAL = ("http://", "https://", "//")


def _map_outside(pattern: re.Pattern, func, text: str) -> str:
    """只对 pattern 匹配之外的片段应用 func。"""
    pieces = []
    last = 0
    for match in pattern.finditer(text):
        pieces.append(func(text[last: match.start()]))
        pieces.append(match.group(0))
        last = match.end()
    pieces.append(func(text[last:]))
    return "".join(pieces)


def _latex_to_dollar(segment: str) -> str:
    """把 LaTeX 的行内/行间定界符换成 MathJax 认识的 $ 与 $$。"""
    segment = segment.replace(r"\[", "$$").replace(r"\]", "$$")
    segment = segment.replace(r"\(", "$").replace(r"\)", "$")
    return segment


def normalize_latex(body: str) -> str:
    """在渲染之前统一公式定界符，代码块内部不动。"""
    lines = body.splitlines(keepends=True)
    out = []
    fence = None
    for line in lines:
        match = _FENCE.match(line.lstrip())
        if match:
            marker = match.group(1)[0]
            if fence is None:
                fence = marker
                out.append(line)
                continue
            if fence == marker:
                fence = None
                out.append(line)
                continue
        if fence is not None:
            out.append(line)
        else:
            out.append(_map_outside(_INLINE_CODE, _latex_to_dollar, line))
    return "".join(out)


class BlogRenderer(mistune.HTMLRenderer):
    """在 mistune 默认渲染器上加一点点"博客需要的东西"。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.toc = []
        self._ids = set()

    # --- 标题：生成锚点 + 收集目录 ---------------------------------
    def heading(self, text: str, level: int, **attrs) -> str:
        plain = re.sub(r"<[^>]+>", "", text)
        import html as _html

        plain = _html.unescape(plain).strip()
        base = slugify(plain, fallback="section")
        anchor = base
        index = 2
        while anchor in self._ids:
            anchor = "{}-{}".format(base, index)
            index += 1
        self._ids.add(anchor)

        if 2 <= level <= 4:
            self.toc.append({"level": level, "id": anchor, "text": plain})

        tag = "h{}".format(level)
        return '<{tag} id="{anchor}">{text}<a class="heading-anchor" href="#{anchor}" aria-label="锚点链接">#</a></{tag}>\n'.format(
            tag=tag, anchor=escape_html(anchor), text=text
        )

    # --- 代码块：语言标签 + 复制按钮 --------------------------------
    def block_code(self, code: str, info: str | None = None) -> str:
        lang = ""
        if info:
            lang = info.strip().split(None, 1)[0]
        lang_attr = ""
        lang_label = "代码"
        if lang:
            safe_lang = re.sub(r"[^\w+#.-]", "", lang)
            lang_attr = ' class="language-{}"'.format(safe_lang)
            lang_label = safe_lang
        body = mistune.util.escape(code)
        return (
            '<div class="code-block">'
            '<div class="code-block__bar">'
            '<span class="code-block__lang">{label}</span>'
            '<button class="code-block__copy" type="button" aria-label="复制代码">复制</button>'
            "</div>"
            "<pre><code{attr}>{body}</code></pre>"
            "</div>\n"
        ).format(label=escape_html(lang_label), attr=lang_attr, body=body)

    # --- 链接：外链新窗口打开 --------------------------------------
    def link(self, text: str, url: str, title: str | None = None) -> str:
        href = self.safe_url(url)
        extra = ""
        if url.startswith(_EXTERNAL):
            extra = ' target="_blank" rel="noopener noreferrer"'
        title_attr = ' title="{}"'.format(escape_html(title)) if title else ""
        return '<a href="{href}"{extra}{title}>{text}</a>'.format(
            href=href, extra=extra, title=title_attr, text=text
        )

    # --- 图片：懒加载 ----------------------------------------------
    def image(self, text: str, url: str, title: str | None = None) -> str:
        src = self.safe_url(url)
        alt = escape_html(re.sub(r"<[^>]+>", "", text))
        title_attr = ' title="{}"'.format(escape_html(title)) if title else ""
        return (
            '<img src="{src}" alt="{alt}"{title} loading="lazy" decoding="async" />'.format(
                src=src, alt=alt, title=title_attr
            )
        )


def _build_markdown(options: dict, allow_html: bool):
    plugins = ["url"]
    if options.get("tables", True):
        plugins.append("table")
    if options.get("footnotes", True):
        plugins.append("footnotes")
    if options.get("task_lists", True):
        plugins.append("task_lists")
    if options.get("strikethrough", True):
        plugins.append("strikethrough")
    if options.get("math", True):
        plugins.append("math")
    renderer = BlogRenderer(escape=not allow_html)
    return mistune.create_markdown(renderer=renderer, plugins=plugins), renderer


def fix_asset_paths(html: str, prefix: str) -> str:
    """把正文里的 static/... 资源路径改写成相对当前页面的路径。

    比旧版的正则替换更保守：只改 src / href 属性，不碰正文文本。
    """
    if not prefix:
        return html

    def replace(match: "re.Match") -> str:
        attr, value = match.group(1), match.group(2)
        if value.startswith(prefix) or value.startswith("#"):
            return match.group(0)
        if value.startswith("static/") or value.startswith("./static/"):
            value = value.lstrip("./")
            return '{}="{}{}"'.format(attr, prefix, value)
        if value.startswith("/"):
            return match.group(0)
        # 站内相对链接（例如 posts/xxx.html）保持原样
        return match.group(0)

    return _ASSET_ATTR.sub(replace, html)


def render_markdown(body: str, *, options: dict | None = None, allow_html: bool = True,
                    asset_prefix: str = "") -> tuple:
    """渲染一篇正文，返回 (html, toc)。"""
    options = options or {}
    if options.get("math", True):
        body = normalize_latex(body)

    md, renderer = _build_markdown(options, allow_html)
    try:
        html = md(body)
    except Exception as exc:  # 渲染失败也不该让整站构建挂掉
        print("[警告] Markdown 渲染失败：{}，已降级为纯文本".format(exc))
        html = "<pre>{}</pre>".format(escape_html(body))

    html = _TABLE.sub(r'<div class="table-scroll">\1</div>', html)
    html = fix_asset_paths(html, asset_prefix)
    return html, renderer.toc
