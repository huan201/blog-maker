"""向后兼容入口：python serve.py 等价于 python -m blog serve"""
from blog.server import serve

if __name__ == "__main__":
    serve()
