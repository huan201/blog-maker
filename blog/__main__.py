"""博客生成器 CLI 入口

用法:
    python -m blog build             # 构建博客
    python -m blog build -o public   # 构建到自定义目录
    python -m blog serve             # 启动预览服务器
    python -m blog serve -o public   # 预览自定义输出目录
    python -m blog clean             # 清空输出目录
"""
import argparse
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="python -m blog",
        description="极简静态博客生成器"
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # --- build 子命令 ---
    build_parser = subparsers.add_parser("build", help="构建博客")
    build_parser.add_argument(
        "-o", "--output", default="dist",
        help="输出目录 (默认: dist)"
    )

    # --- serve 子命令 ---
    serve_parser = subparsers.add_parser("serve", help="启动预览服务器")
    serve_parser.add_argument(
        "-o", "--output", default="dist",
        help="输出目录 (默认: dist)"
    )
    serve_parser.add_argument(
        "-p", "--port", type=int, default=8000,
        help="服务器端口 (默认: 8000)"
    )

    # --- clean 子命令 ---
    clean_parser = subparsers.add_parser("clean", help="清空输出目录")
    clean_parser.add_argument(
        "-o", "--output", default="dist",
        help="要清空的输出目录 (默认: dist)"
    )

    args = parser.parse_args()

    if args.command == "build":
        from blog.builder import build_all
        build_all(output_dir=args.output)

    elif args.command == "serve":
        from blog.server import serve
        serve(output_dir=args.output, port=args.port)

    elif args.command == "clean":
        output_path = Path(args.output)
        if output_path.exists():
            shutil.rmtree(output_path)
            print(f"已清空: {output_path}")
        else:
            print(f"目录不存在: {output_path}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
