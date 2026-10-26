"""站点构建。

设计要点：

* **不依赖工作目录**：所有路径都来自配置对象，可以在任意目录执行构建。
* **增量安全**：输出目录里有一个 .build-manifest.json 记录上次生成了哪些文件，
  本次没再生成的文件会被清理（解决删掉文章后 dist 里还留着幽灵页面的问题），
  但**不在清单里的文件一律不动**，用户上传的图片、附件永远不会被误删。
* **一次性构建**：没有半吊子的"单篇增量"逻辑，小站全量构建是毫秒级的。
* **自动生成 .nojekyll**：不然 GitHub Pages 的 Jekyll 会忽略下划线开头的文件。
* **内容与生成器解耦**：文章目录可以放在仓库外（--content），
  于是你可以让文章源文件不进这个仓库。
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .content import Post, collect_tags, load_posts, load_views_seed, parse_frontmatter
from .markdown_renderer import render_markdown
from .templating import TemplateEngine
from .utils import (
    escape_html,
    format_date,
    rfc822,
    shorten,
    slugify,
    unique_slug,
    url_quote_path,
)

MANIFEST_NAME = ".build-manifest.json"

# MathJax 3 的配置必须写在加载脚本之前。
# 注意反斜杠：源码里写四个，浏览器里的 JS 解析成两个，MathJax 拿到的就是 \( 和 \)
MATHJAX_HEAD = (
    "<script>\n"
    "window.MathJax = {\n"
    "  tex: {\n"
    "    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],\n"
    "    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]\n"
    "  },\n"
    "  options: { enableMenu: false }\n"
    "};\n"
    "</script>\n"
    '<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>'
)

# highlight.js 走 CDN，加载失败也不影响正文阅读
HIGHLIGHT_FOOT = (
    '<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>\n'
    "<script>\n"
    "(function () {\n"
    "  if (!window.hljs) return;\n"
    "  var blocks = document.querySelectorAll('.code-block pre code');\n"
    "  for (var i = 0; i < blocks.length; i += 1) {\n"
    "    try { hljs.highlightElement(blocks[i]); } catch (e) {}\n"
    "  }\n"
    "})();\n"
    "</script>"
)

# 这些目录一旦存在于输出目录，就绝不能被清理逻辑删掉（可能是历史上传资源）
PRESERVED_DIRS = ("static/images", "static/attachments")


class BuildResult:
    """构建结果，方便 CLI 打印统计。"""

    def __init__(self):
        self.posts = 0
        self.tags = 0
        self.pages = 0
        self.removed = 0
        self.warnings = []

    def summary(self) -> str:
        return "文章 {} 篇 · 标签 {} 个 · 页面 {} 个 · 清理 {} 个旧文件".format(
            self.posts, self.tags, self.pages, self.removed
        )


class Builder:
    def __init__(self, config: Config, include_drafts: bool | None = None):
        self.config = config
        self.include_drafts = (
            bool(config.get("build.include_drafts", False))
            if include_drafts is None
            else include_drafts
        )
        self.engine = TemplateEngine(config.templates_dir)
        self.output = config.output_dir
        self.generated: set = set()
        self.result = BuildResult()
        self.posts: list = []
        self.tags: dict = {}
        self.tags_by_slug: dict = {}
        self.views_seed: dict = {}

    # -- 小工具 ------------------------------------------------------
    def _write(self, rel: str, text: str) -> None:
        target = self.output / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        self.generated.add(rel)
        self.result.pages += 1

    def _runtime_config(self, base: str, *, with_comments: bool = False) -> str:
        payload = {
            "base": base,
            "basePath": self.config.base_path,
            "accent": self.config.get("theme.accent", "#0071e3"),
            "appearance": self.config.get("theme.appearance", "auto"),
            "metrics": self._metrics_config(),
            "viewsSeed": self.views_seed,
        }
        if with_comments:
            payload["comments"] = self._comments_config()
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        # 防止配置里出现 </script> 把脚本标签提前闭合
        raw = raw.replace("</", "<\\/")
        return raw

    def _metrics_config(self) -> dict:
        metrics = dict(self.config.section("metrics"))
        metrics.pop("seed_file", None)
        return metrics

    def _comments_config(self) -> dict:
        comments = dict(self.config.section("comments"))
        provider = str(comments.get("provider", "none")).lower()

        if not comments.get("enabled", True) or provider == "none":
            return {"provider": "none"}

        if provider == "giscus" and not (
            comments.get("repo_id") and comments.get("category_id")
        ):
            self.result.warnings.append(
                "giscus 缺少 repo_id / category_id，已自动降级为 utterances"
            )
            provider = "utterances"

        if provider in ("giscus", "utterances") and not comments.get("repo"):
            return {"provider": "unconfigured"}

        comments["provider"] = provider
        comments.pop("enabled", None)
        return comments

    # -- 页面骨架 ----------------------------------------------------
    def _nav_links(self, base: str, active: str) -> str:
        items = [
            ("index.html", "首页", "home"),
            ("tags/index.html", "标签", "tags"),
            ("friends/index.html", "友链", "friends"),
            ("search.html", "搜索", "search"),
        ]
        links = []
        for href, label, key in items:
            cls = "nav__link is-active" if key == active else "nav__link"
            links.append(
                '<a class="{cls}" href="{base}{href}">{label}</a>'.format(
                    cls=cls, base=base, href=href, label=label
                )
            )
        return "\n            ".join(links)

    def _page(
        self,
        rel_out: str,
        depth: int,
        template: str,
        page_vars: dict,
        *,
        title: str,
        description: str = "",
        active: str = "",
        with_comments: bool = False,
        extra_head: str = "",
        extra_foot: str = "",
        body_class: str = "",
    ) -> None:
        base = "../" * depth
        inner = self.engine.render(template, **page_vars)

        site_title = self.config.get("site.title", "我的博客")
        full_title = title if title == site_title else "{} · {}".format(title, site_title)
        description = description or str(self.config.get("site.description", ""))

        context = {
            "lang": self.config.get("site.language", "zh-CN"),
            "site_title": escape_html(site_title),
            "site_subtitle": escape_html(self.config.get("site.subtitle", "")),
            "title": escape_html(full_title),
            "page_title": escape_html(title),
            "description": escape_html(shorten(description, 160)),
            "canonical": escape_html(self.config.site_url(rel_out)),
            "base": base,
            "root_abs": self.config.base_path,
            "nav_links": self._nav_links(base, active),
            "content": inner,
            "accent": escape_html(self.config.get("theme.accent", "#0071e3")),
            "appearance": self.config.get("theme.appearance", "auto"),
            "year": str(datetime.now().year),
            "author": escape_html(self.config.get("site.author", "")),
            "footer_html": self._footer_html(base),
            "github_url": escape_html(self.config.get("site.github", "")),
            "runtime_json": self._runtime_config(base, with_comments=with_comments),
            "extra_head": extra_head,
            "extra_foot": extra_foot,
            "body_class": body_class,
            "rss_url": base + "feed.xml",
        }

        html = self.engine.render("base.html", **context)
        self._write(rel_out, html)

    def _footer_html(self, base: str) -> str:
        site_title = escape_html(self.config.get("site.title", "我的博客"))
        custom = escape_html(self.config.get("site.footer", ""))
        links = [
            '<a href="{0}feed.xml">RSS</a>'.format(base),
            '<a href="{0}sitemap.xml">Sitemap</a>'.format(base),
        ]
        github = self.config.get("site.github", "")
        if github:
            links.insert(
                0,
                '<a href="{0}" target="_blank" rel="noopener noreferrer">GitHub</a>'.format(
                    escape_html(github)
                ),
            )
        email = self.config.get("site.email", "")
        if email:
            links.append('<a href="mailto:{0}">邮件</a>'.format(escape_html(email)))
        return (
            '<p class="footer__line">© {year} {site}{custom}</p>'
            '<p class="footer__links">{links}</p>'
        ).format(
            year=datetime.now().year,
            site=site_title,
            custom=" · " + custom if custom else "",
            links=" · ".join(links),
        )

    # -- 组件 --------------------------------------------------------
    def _tag_href(self, tag: str) -> str:
        slug = self.tags_by_slug.get(tag, "index")
        return "tags/{}.html".format(url_quote_path(slug))

    def _tag_pills(self, tags: list) -> str:
        if not tags:
            return ""
        pills = [
            '<a class="pill" href="{href}">{name}</a>'.format(
                href=self._tag_href(tag), name=escape_html(tag)
            )
            for tag in tags
        ]
        return '<div class="pills">{}</div>'.format("".join(pills))

    def _post_card(self, post: Post) -> str:
        meta_bits = []
        if post.date:
            meta_bits.append(
                '<time datetime="{0}">{1}</time>'.format(
                    post.date.isoformat(), escape_html(format_date(post.date))
                )
            )
        else:
            meta_bits.append("<span>日期未填</span>")
        meta_bits.append("<span>{} 字</span>".format(post.words))
        meta_bits.append("<span>约 {} 分钟</span>".format(post.minutes))
        meta_bits.append(
            '<span data-views data-view-key="{0}">—</span>'.format(escape_html(post.slug))
        )

        return (
            '<article class="card">'
            '<a class="card__hit" href="{url}">'
            '<h2 class="card__title">{title}</h2>'
            '<p class="card__summary">{summary}</p>'
            "</a>"
            '<div class="card__meta">{meta}</div>'
            "{tags}"
            "</article>"
        ).format(
            url=url_quote_path(post.html_file),
            title=escape_html(post.title),
            summary=escape_html(post.summary),
            meta='<span class="dot"></span>'.join(meta_bits),
            tags=self._tag_pills(post.tags),
        )

    def _post_list(self, posts: list) -> str:
        if not posts:
            return '<p class="empty">这里还没有文章。</p>'
        return '<div class="cards">\n{}\n</div>'.format(
            "\n".join(self._post_card(post) for post in posts)
        )

    # -- 主流程 ------------------------------------------------------
    def build(self, clean: bool = False) -> BuildResult:
        content_dir = self.config.content_dir
        self.posts = load_posts(content_dir, include_drafts=self.include_drafts)
        self.tags = collect_tags(self.posts)

        used: set = set()
        for tag in sorted(self.tags):
            self.tags_by_slug[tag] = unique_slug(slugify(tag, fallback="tag"), used)

        seed_path = self.config.get("metrics.seed_file", "content/views.json")
        seed_file = Path(seed_path)
        if not seed_file.is_absolute():
            seed_file = self.config.root / seed_file
        self.views_seed = load_views_seed(seed_file)

        self.output.mkdir(parents=True, exist_ok=True)
        if clean:
            self.result.removed += self._clean_output()

        for post in self.posts:
            for warning in post.warnings:
                self.result.warnings.append("{}: {}".format(post.source.name, warning))

        self._build_posts()
        self._build_index()
        self._build_tags()
        self._build_search()
        self._build_friends()
        self._build_error_page()
        self._build_feeds()
        self._copy_static()
        self._write_nojekyll()
        self.result.removed += self._cleanup_stale()
        self._write_manifest()

        self.result.posts = len(self.posts)
        self.result.tags = len(self.tags)
        return self.result

    # -- 各页面 ------------------------------------------------------
    def _build_posts(self) -> None:
        ordered = self.posts
        for index, post in enumerate(ordered):
            prev_post = ordered[index - 1] if index > 0 else None
            next_post = ordered[index + 1] if index + 1 < len(ordered) else None

            body_html, toc = render_markdown(
                post.body,
                options=self.config.section("markdown"),
                allow_html=bool(self.config.get("markdown.allow_html", True)),
                asset_prefix="../",
            )

            toc_html = ""
            if len(toc) >= 2:
                items = "".join(
                    '<li class="toc__item toc__item--h{level}">'
                    '<a href="#{anchor}">{text}</a></li>'.format(
                        level=item["level"],
                        anchor=escape_html(item["id"]),
                        text=escape_html(item["text"]),
                    )
                    for item in toc
                )
                toc_html = (
                    '<nav class="toc" aria-label="目录">'
                    '<p class="toc__title">目录</p><ul class="toc__list">{items}</ul></nav>'
                ).format(items=items)

            pager = ""
            pager_parts = []
            if prev_post:
                pager_parts.append(
                    '<a class="pager__link pager__link--prev" href="{url}">'
                    '<span class="pager__hint">上一篇</span>'
                    '<span class="pager__title">{title}</span></a>'.format(
                        url=url_quote_path(prev_post.html_file),
                        title=escape_html(prev_post.title),
                    )
                )
            if next_post:
                pager_parts.append(
                    '<a class="pager__link pager__link--next" href="{url}">'
                    '<span class="pager__hint">下一篇</span>'
                    '<span class="pager__title">{title}</span></a>'.format(
                        url=url_quote_path(next_post.html_file),
                        title=escape_html(next_post.title),
                    )
                )
            if pager_parts:
                pager = '<nav class="pager" aria-label="翻页">{}</nav>'.format("".join(pager_parts))

            meta_bits = [
                '<time datetime="{0}">{1}</time>'.format(
                    post.date.isoformat() if post.date else "", escape_html(post.date_text)
                )
            ]
            meta_bits.append("<span>{} 字</span>".format(post.words))
            meta_bits.append("<span>约 {} 分钟</span>".format(post.minutes))
            meta_bits.append(
                '<span data-views data-view-key="{0}" data-view-track="1">—</span>'.format(
                    escape_html(post.slug)
                )
            )

            self._page(
                post.html_file,
                1,
                "post.html",
                {
                    "title": escape_html(post.title),
                    "meta": '<span class="dot"></span>'.join(meta_bits),
                    "tags": self._tag_pills(post.tags),
                    "body": body_html,
                    "toc": toc_html,
                    "pager": pager,
                    "comments": self._comments_markup(),
                    "slug": escape_html(post.slug),
                    "views_base": str(self.views_seed.get(post.slug, 0)),
                },
                title=post.title,
                description=post.summary,
                with_comments=True,
                body_class="page-post",
                extra_head=MATHJAX_HEAD,
                extra_foot=HIGHLIGHT_FOOT,
            )

    def _comments_markup(self) -> str:
        return (
            '<section class="comments" id="comments" aria-label="评论">'
            '<div class="comments__head">'
            '<h2 class="comments__title">评论</h2>'
            '<p class="comments__hint">评论由 GitHub 托管，刷新或重新部署都不会丢失。</p>'
            "</div>"
            '<div class="comments__mount" id="comments-mount">'
            '<p class="comments__loading">正在加载评论…</p>'
            "</div>"
            "</section>"
        )

    def _build_index(self) -> None:
        site_title = escape_html(self.config.get("site.title", "我的博客"))
        subtitle = escape_html(self.config.get("site.subtitle", ""))
        total_words = sum(post.words for post in self.posts)

        stats = [
            ("{}".format(len(self.posts)), "篇文章"),
            ("{}".format(len(self.tags)), "个标签"),
            ("{}".format(total_words), "字"),
        ]
        stats_html = "".join(
            '<div class="stat"><span class="stat__value">{value}</span>'
            '<span class="stat__label">{label}</span></div>'.format(value=value, label=label)
            for value, label in stats
        )

        hero = (
            '<header class="hero">'
            '<p class="hero__eyebrow">{subtitle}</p>'
            '<h1 class="hero__title">{title}</h1>'
            '<p class="hero__lead">{description}</p>'
            '<div class="hero__stats">{stats}</div>'
            "</header>"
        ).format(
            subtitle=subtitle or "欢迎光临",
            title=site_title,
            description=escape_html(self.config.get("site.description", "")),
            stats=stats_html,
        )

        self._page(
            "index.html",
            0,
            "index.html",
            {"hero": hero, "posts": self._post_list(self.posts)},
            title=str(self.config.get("site.title", "我的博客")),
            description=str(self.config.get("site.description", "")),
            active="home",
        )

    def _build_tags(self) -> None:
        cloud = "".join(
            '<a class="tag-card" href="{href}">'
            '<span class="tag-card__name">{name}</span>'
            '<span class="tag-card__count">{count}</span></a>'.format(
                # 标签总览页本身就在 tags/ 目录里，所以链接只用文件名
                href=url_quote_path(self.tags_by_slug[tag]) + ".html",
                name=escape_html(tag),
                count=len(self.tags[tag]),
            )
            for tag in sorted(self.tags, key=lambda t: (-len(self.tags[t]), t))
        )

        self._page(
            "tags/index.html",
            1,
            "tags.html",
            {"cloud": cloud or '<p class="empty">还没有任何标签。</p>', "count": str(len(self.tags))},
            title="标签",
            description="按标签浏览全部文章",
            active="tags",
        )

        for tag, posts in self.tags.items():
            slug = self.tags_by_slug[tag]
            self._page(
                "tags/{}.html".format(slug),
                1,
                "tag.html",
                {
                    "tag": escape_html(tag),
                    "count": str(len(posts)),
                    "posts": self._post_list(posts),
                },
                title="标签：{}".format(tag),
                description="标签 {} 下的全部文章".format(tag),
                active="tags",
            )

    def _build_search(self) -> None:
        entries = []
        for post in self.posts:
            entry = post.to_index_entry(self.tags_by_slug)
            entry["views_base"] = self.views_seed.get(post.slug, 0)
            entries.append(entry)
        payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
        self._write("posts.json", payload)

        self._page(
            "search.html",
            0,
            "search.html",
            {"index_url": "posts.json"},
            title="搜索",
            description="搜索全部文章的标题、正文和标签",
            active="search",
            extra_foot='<script src="static/js/search.js" defer></script>',
        )

    def _build_friends(self) -> None:
        friends_file = self.config.content_dir / "friends.txt"
        if not friends_file.is_file():
            return
        try:
            raw = friends_file.read_text(encoding="utf-8")
        except OSError as exc:
            self.result.warnings.append("友链读取失败：{}".format(exc))
            return

        meta, body = parse_frontmatter(raw)
        html, _ = render_markdown(
            body,
            options=self.config.section("markdown"),
            allow_html=bool(self.config.get("markdown.allow_html", True)),
        )
        self._page(
            "friends/index.html",
            1,
            "friends.html",
            {"friend_links": html, "title": escape_html(meta.get("title", "友链"))},
            title=meta.get("title", "友链"),
            description="友情链接",
            active="friends",
        )

    def _build_error_page(self) -> None:
        # 404 页会被 GitHub Pages 在任何不存在的路径下返回，
        # 因此里面的链接必须用站点根路径，不能靠相对路径。
        self._page(
            "404.html",
            0,
            "404.html",
            {"root_abs": self.config.base_path},
            title="页面不存在",
            description="没有找到你要的页面",
        )

    def _build_feeds(self) -> None:
        base_url = self.config.base_url
        site_title = str(self.config.get("site.title", "我的博客"))
        description = str(self.config.get("site.description", ""))

        items = []
        for post in self.posts[:20]:
            link = self.config.site_url(post.html_file)
            items.append(
                "<item>"
                "<title>{title}</title>"
                "<link>{link}</link>"
                "<guid isPermaLink=\"true\">{link}</guid>"
                "<pubDate>{date}</pubDate>"
                "<description>{desc}</description>"
                "</item>".format(
                    title=escape_html(post.title),
                    link=escape_html(link),
                    date=rfc822(post.date),
                    desc=escape_html(post.summary),
                )
            )

        feed = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">'
            "<channel>"
            "<title>{title}</title>"
            "<link>{home}</link>"
            "<description>{desc}</description>"
            "<language>{lang}</language>"
            '<atom:link href="{feed_url}" rel="self" type="application/rss+xml" />'
            "{items}"
            "</channel></rss>\n"
        ).format(
            title=escape_html(site_title),
            home=escape_html(base_url + "/" if base_url else "index.html"),
            desc=escape_html(description),
            lang=self.config.get("site.language", "zh-CN"),
            feed_url=escape_html(self.config.site_url("feed.xml")),
            items="".join(items),
        )
        self._write("feed.xml", feed)

        urls = ["index.html", "tags/index.html", "search.html", "friends/index.html"]
        urls += [post.html_file for post in self.posts]
        urls += ["tags/{}.html".format(self.tags_by_slug[tag]) for tag in self.tags]
        lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(
                "  <url><loc>{}</loc><lastmod>{}</lastmod></url>".format(
                    escape_html(self.config.site_url(url_quote_path(url))), lastmod
                )
                for url in urls
            )
            + "\n</urlset>\n"
        )
        self._write("sitemap.xml", sitemap)

        base_path = self.config.base_path
        robots = "User-agent: *\nAllow: /\n\nSitemap: {}\n".format(
            self.config.site_url("sitemap.xml") if base_url else base_path + "sitemap.xml"
        )
        self._write("robots.txt", robots)

    def _copy_static(self) -> None:
        source = self.config.static_dir
        if not source.is_dir():
            self.result.warnings.append("static 目录不存在：{}".format(source))
            return
        target = self.output / "static"
        target.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            destination = target / item.name
            try:
                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, destination)
            except OSError as exc:
                self.result.warnings.append("复制 {} 失败：{}".format(item.name, exc))

    def _write_nojekyll(self) -> None:
        self._write(".nojekyll", "")

    # -- 清理 --------------------------------------------------------
    def _clean_output(self) -> int:
        """完整清空输出目录，但保住用户上传的资源。"""
        if not self.output.is_dir():
            return 0
        stash = self.output.parent / (self.output.name + ".keep")
        moved = []
        for rel in PRESERVED_DIRS:
            src = self.output / rel
            if src.is_dir():
                dst = stash / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                moved.append(rel)

        removed = 0
        for item in self.output.iterdir():
            try:
                if item.is_dir():
                    removed += sum(1 for _ in item.rglob("*") if _.is_file())
                    shutil.rmtree(item)
                else:
                    item.unlink()
                    removed += 1
            except OSError:
                continue

        for rel in moved:
            src = stash / rel
            dst = self.output / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        shutil.rmtree(stash, ignore_errors=True)
        return removed

    def _cleanup_stale(self) -> int:
        manifest_path = self.output / MANIFEST_NAME
        previous = set()
        if manifest_path.is_file():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    previous = {str(item) for item in data}
            except (OSError, ValueError):
                previous = set()

        removed = 0
        for rel in sorted(previous - self.generated):
            target = self.output / rel
            if not target.is_file():
                continue
            if any(rel.startswith(keep) for keep in PRESERVED_DIRS):
                continue
            try:
                target.unlink()
                removed += 1
            except OSError:
                continue

        # 顺手清理空目录（tags/ 下删光后别留下空壳）
        for path in sorted(self.output.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                try:
                    path.rmdir()
                except OSError:
                    pass
        return removed

    def _write_manifest(self) -> None:
        manifest_path = self.output / MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(sorted(self.generated), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def build(config: Config, *, clean: bool = False, include_drafts: bool | None = None) -> BuildResult:
    """对外入口：构建整站。"""
    return Builder(config, include_drafts=include_drafts).build(clean=clean)
