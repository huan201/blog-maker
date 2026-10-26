"""极简模板引擎。

只做一件简单的事：把模板里的双花括号占位符换成变量值。

和旧版的关键区别：**单遍扫描**。
旧版对每个变量各做一次 re.sub，导致正文里只要出现某个占位符的字样
就会被二次替换成路径，属于很难排查的幽灵 bug。
这里用一次 re.sub 完成，替换进去的内容不会被再次扫描。
"""
from __future__ import annotations

import re
from pathlib import Path

# 双花括号 + 变量名；单遍替换，替换进去的正文不会再被扫描
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class TemplateError(Exception):
    """模板相关的错误。"""


class TemplateEngine:
    """按名字加载 templates/ 下的模板并渲染。"""

    def __init__(self, templates_dir: Path):
        self.templates_dir = Path(templates_dir)
        self._cache: dict = {}
        self.missing: list = []

    def load(self, name: str) -> str:
        """读取模板（带缓存），找不到时抛出可读的错误。"""
        if name not in self._cache:
            path = self.templates_dir / name
            if not path.is_file():
                raise TemplateError("模板不存在: {}".format(path))
            self._cache[name] = path.read_text(encoding="utf-8")
        return self._cache[name]

    def render_string(self, template: str, context: dict) -> str:
        """单遍替换占位符。"""

        def replace(match: "re.Match") -> str:
            key = match.group(1)
            if key in context:
                value = context[key]
                return value if isinstance(value, str) else str(value)
            self.missing.append(key)
            return match.group(0)  # 原样保留，方便一眼看出哪里漏了

        return _PLACEHOLDER.sub(replace, template)

    def render(self, name: str, **context) -> str:
        return self.render_string(self.load(name), context)

    def placeholders(self, names) -> dict:
        """列出模板里用到的占位符，给 check 命令做静态检查。"""
        found = {}
        for name in names:
            try:
                text = self.load(name)
            except TemplateError:
                continue
            found[name] = sorted(set(_PLACEHOLDER.findall(text)))
        return found