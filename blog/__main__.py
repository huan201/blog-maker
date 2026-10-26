"""命令行入口。

    python -m blog build            构建站点到 dist/
    python -m blog build --clean    先清空输出目录再构建
    python -m blog build --content ../my-posts   用仓库外的文章目录
    python -m blog serve            本地预览（127.0.0.1:8000）+ 自动重建
    python -m blog new "标题"       新建一篇文章
    python -m blog check            体检：配置 / 模板 / 文章 / 资源引用
    python -m blog stats            站点统计
    python -m blog clean            清空输出目录（有安全保护）

所有命令都支持 --root 指定项目根目录，因此在任何路径下都能执行。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

from .builder import MANIFEST_NAME, Builder
from .config import CONFIG_FILENAME, Config, _deep_merge, load_config, validate
from .content import collect_tags, load_posts
from .templating import TemplateEngine
from .utils import slugify

REQUIRED_TEMPLATES = (
    "base.html",
    "index.html",
    "post.html",
    "tags.html",
    "tag.html",
    "search.html",
    "friends.html",
    "404.html",
)

_ASSET_REF = re.compile(r'(?:src|href)="([^"]+)"|\]\(([^)]+)\)')


def _common_options() -> argparse.ArgumentParser:
    """--root / --config 在主命令和子命令上都能写。

    用 SUPPRESS 作为默认值，这样子命令不会把主命令已经解析到的值冲掉。
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS, help="项目根目录（默认当前目录）")
    common.add_argument(
        "--config", default=argparse.SUPPRESS, help="配置文件路径（默认 blog.config.json）"
    )
    return common


def _build_parser() -> argparse.ArgumentParser:
    common = _common_options()
    parser = argparse.ArgumentParser(
        prog="python -m blog",
        description="极简静态博客生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
        parents=[common],
    )
    parser.add_argument("--version", action="store_true", help="显示版本号")
    sub = parser.add_subparsers(dest="command")

    build = sub.add_parser("build", help="构建站点", parents=[common])
    build.add_argument("-o", "--output", default=None, help="输出目录（默认读取配置）")
    build.add_argument(
        "-c", "--content", default=None,
        help="文章目录（默认读取配置；可以指向仓库外的目录，这样文章源文件不必提交）"
    )
    build.add_argument("--clean", action="store_true", help="构建前清空输出目录")
    build.add_argument("--drafts", action="store_true", help="把 draft: true 的文章也一起构建")
    build.add_argument("--quiet", action="store_true", help="只打印结果，不打印每篇文章")

    serve = sub.add_parser("serve", help="启动本地预览服务器", parents=[common])
    serve.add_argument("-o", "--output", default=None, help="输出目录")
    serve.add_argument("-p", "--port", type=int, default=8000, help="端口（默认 8000）")
    serve.add_argument("--host", default="127.0.0.1", help="监听地址（默认只监听本机）")
    serve.add_argument("--no-watch", action="store_true", help="关闭文件变化自动重建")
    serve.add_argument("--drafts", action="store_true", help="预览草稿")

    clean = sub.add_parser("clean", help="清空输出目录", parents=[common])
    clean.add_argument("-o", "--output", default=None, help="要清空的输出目录")
    clean.add_argument("-y", "--yes", action="store_true", help="不再询问")

    new = sub.add_parser("new", help="新建文章", parents=[common])
    new.add_argument("title", help="文章标题")
    new.add_argument("-t", "--tags", default="", help="标签，用逗号分隔")
    new.add_argument("-d", "--date", default=None, help="日期，默认今天")

    sub.add_parser("check", help="检查配置、模板与资源引用", parents=[common])
    sub.add_parser("stats", help="输出站点统计", parents=[common])

    return parser


def _load(args) -> Config:
    root = Path(getattr(args, "root", ".")).resolve()
    config = load_config(root, getattr(args, "config", None))

    overrides: dict = {}
    output = getattr(args, "output", None)
    if output:
        overrides.setdefault("build", {})["output_dir"] = output
    content = getattr(args, "content", None)
    if content:
        overrides.setdefault("build", {})["content_dir"] = content

    if overrides:
        config = Config(_deep_merge(config.as_dict(), overrides), config.root, config.source)
    return config


def cmd_build(args) -> int:
    config = _load(args)
    include_drafts = True if getattr(args, "drafts", False) else None
    builder = Builder(config, include_drafts=include_drafts)

    if not getattr(args, "quiet", False):
        print("构建: {}".format(config.root))
        print("  文章目录: {}".format(config.content_dir))
        print("  输出目录: {}".format(config.output_dir))

    result = builder.build(clean=getattr(args, "clean", False))

    if not getattr(args, "quiet", False):
        for post in builder.posts:
            print("  [{}] {} -> {}".format(
                post.date.isoformat() if post.date else "无日期", post.title, post.html_file
            ))

    for warning in result.warnings:
        print("  [警告] {}".format(warning))

    missing = sorted(set(builder.engine.missing))
    if missing:
        print("  [警告] 模板缺少这些占位符的取值：{}".format(", ".join(missing)))

    print("完成: " + result.summary())
    return 0


def cmd_serve(args) -> int:
    from .server import serve

    config = _load(args)
    serve(
        config,
        host=args.host,
        port=args.port,
        watch=not args.no_watch,
        include_drafts=args.drafts,
    )
    return 0


def cmd_clean(args) -> int:
    config = _load(args)
    target = config.output_dir.resolve()
    root = config.root.resolve()

    # 安全保护：clean 曾经只要 -o . 就会把整个项目删掉
    if target == root or target in root.parents:
        print("拒绝执行：{} 是项目目录本身或其上级目录。".format(target))
        return 1
    if target == Path(target.anchor) or target == Path.home().resolve():
        print("拒绝执行：{} 太危险了。".format(target))
        return 1

    if not target.is_dir():
        print("目录不存在：{}".format(target))
        return 0

    has_manifest = (target / MANIFEST_NAME).is_file()
    if not has_manifest and any(target.iterdir()) and not args.yes:
        print("{} 里没有构建清单，可能不是本工具生成的目录。".format(target))
        print("确认要全部删除请加 --yes。")
        return 1

    shutil.rmtree(target)
    print("已清空：{}".format(target))
    return 0


def cmd_new(args) -> int:
    config = _load(args)
    content_dir = config.content_dir
    content_dir.mkdir(parents=True, exist_ok=True)

    title = args.title.strip()
    if not title:
        print("标题不能为空。")
        return 1

    day = args.date or date.today().isoformat()
    slug = slugify(title, fallback="post")
    # 中文标题用日期做文件名，ASCII 标题直接沿用标题
    if not re.match(r"^[A-Za-z0-9_-]+$", slug):
        slug = "{}-{}".format(day.replace("-", ""), slug)

    target = content_dir / "{}.txt".format(slug)
    index = 2
    while target.exists():
        target = content_dir / "{}-{}.txt".format(slug, index)
        index += 1

    template = (
        "---\n"
        "title: {title}\n"
        "date: {day}\n"
        "tags: {tags}\n"
        "---\n"
        "\n"
        "## 小标题\n"
        "\n"
        "从这里开始写正文。支持 **Markdown**、表格、代码块和 $LaTeX$ 公式。\n"
    ).format(title=title, day=day, tags=args.tags.strip())

    target.write_text(template, encoding="utf-8")
    print("已创建：{}".format(target))
    print("写完执行 python -m blog build，或者 python -m blog serve 边写边看。")
    return 0


def cmd_check(args) -> int:
    config = _load(args)
    problems = 0

    print("项目根目录: {}".format(config.root))
    print("文章目录:   {}".format(config.content_dir))
    print("配置文件:   {}".format(config.source or "（未找到 {}，使用默认值）".format(CONFIG_FILENAME)))
    print("")

    # 1. 配置
    print("[1/4] 配置检查")
    warnings = validate(config)
    for item in warnings:
        print("  ! " + item)
    problems += len(warnings)
    if not warnings:
        print("  ok")

    # 2. 模板
    print("\n[2/4] 模板检查")
    for name in REQUIRED_TEMPLATES:
        path = config.templates_dir / name
        if path.is_file():
            print("  ok  {}".format(name))
        else:
            print("  !!  缺少模板 {}".format(name))
            problems += 1

    # 3. 文章
    print("\n[3/4] 文章检查")
    posts = load_posts(config.content_dir, include_drafts=True)
    if not posts:
        print("  ! {} 下没有找到文章".format(config.content_dir))
        problems += 1
    for post in posts:
        flags = "草稿" if post.draft else "正常"
        print("  ok  {:<24} {} 字  {}".format(post.source.name, post.words, flags))
        for warning in post.warnings:
            print("       ! " + warning)
            problems += 1

    # 4. 资源引用
    print("\n[4/4] 静态资源引用检查")
    missing = 0
    for post in posts:
        for match in _ASSET_REF.finditer(post.body):
            reference = (match.group(1) or match.group(2) or "").strip()
            if not reference.startswith("static/"):
                continue
            target = config.root / reference
            if not target.is_file():
                print("  !!  {} 里引用了不存在的资源: {}".format(post.source.name, reference))
                missing += 1
    problems += missing
    if not missing:
        print("  ok")

    # 附加：做一次临时构建，检查模板占位符是否都有取值
    print("\n[附加] 试构建（输出到项目内的临时目录，不动 dist/）")
    temp_dir = config.root / ".blog-check"
    shutil.rmtree(temp_dir, ignore_errors=True)
    try:
        probe = Config(
            _deep_merge(config.as_dict(), {"build": {"output_dir": str(temp_dir)}}),
            config.root,
            config.source,
        )
        builder = Builder(probe, include_drafts=True)
        result = builder.build()
        missing_keys = sorted(set(builder.engine.missing))
        if missing_keys:
            print("  !! 模板里这些占位符没有对应取值: {}".format(", ".join(missing_keys)))
            problems += len(missing_keys)
        else:
            print("  ok  " + result.summary())
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    tags = collect_tags(posts)
    print("\n标签: {} 个".format(len(tags)))
    print("")
    if problems:
        print("发现 {} 个问题。".format(problems))
        return 1
    print("没有发现问题。")
    return 0


def cmd_stats(args) -> int:
    config = _load(args)
    posts = load_posts(config.content_dir, include_drafts=True)
    tags = collect_tags(posts)
    words = sum(post.words for post in posts)
    drafts = [post for post in posts if post.draft]

    print("文章    {} 篇（其中草稿 {} 篇）".format(len(posts), len(drafts)))
    print("总字数  {}".format(words))
    print("标签    {} 个".format(len(tags)))
    if posts:
        dates = [post.date for post in posts if post.date]
        if dates:
            print("时间跨度 {} → {}".format(min(dates), max(dates)))
        print("")
        print("按标签统计：")
        for tag, items in sorted(tags.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            print("  {:<16} {}".format(tag, len(items)))
    return 0


def main(argv=None) -> int:
    # Windows 控制台默认不是 UTF-8，中文日志会变成乱码，这里统一一下
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = _build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "version", False):
        from . import __version__

        print("blog {}".format(__version__))
        return 0

    handlers = {
        "build": cmd_build,
        "serve": cmd_serve,
        "clean": cmd_clean,
        "new": cmd_new,
        "check": cmd_check,
        "stats": cmd_stats,
    }

    if not args.command:
        parser.print_help()
        return 0

    try:
        return handlers[args.command](args) or 0
    except KeyboardInterrupt:
        print("\n已取消。")
        return 130
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - 给用户一个可读的失败信息
        print("出错了: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
