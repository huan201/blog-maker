"""向后兼容入口：python build.py 等价于 python -m blog build"""
from blog.builder import build_all

if __name__ == "__main__":
    build_all()
