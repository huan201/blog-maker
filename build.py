"""兼容入口：python build.py 等价于 python -m blog build

保留这个文件只是为了兼容旧的使用习惯，推荐直接用 CLI。
"""
from blog.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main(["build"]))
