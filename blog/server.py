import time
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler


def serve(output_dir="dist", port=8000):
    """启动本地预览服务器 + 文件监听自动重建"""
    from blog.builder import (build_all, build_single, parse_meta,
                              _render_body, render)

    output_dir = Path(output_dir)

    # 自定义 Handler：通过 directory 参数指定根目录
    def make_handler(dist_path):
        class _Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(dist_path), **kwargs)
        return _Handler

    def run_server():
        handler = make_handler(output_dir)
        server = HTTPServer(("0.0.0.0", port), handler)
        print(f"服务器已启动: http://127.0.0.1:{port}")
        print(f"输出目录: {output_dir}")
        server.serve_forever()

    def collect_mtimes():
        """收集所有监听目录中文件的修改时间戳"""
        mtimes = {}
        for dir_name in ["content", "templates", "static"]:
            watch_path = Path(dir_name)
            if watch_path.is_dir():
                for f in watch_path.rglob("*"):
                    if f.is_file():
                        mtimes[f] = f.stat().st_mtime
        return mtimes

    # 初始化构建
    print("开始监听文件变化...")
    build_all(output_dir=str(output_dir))
    last_mtimes = collect_mtimes()

    # 服务器放在子线程
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(0.5)

    # 主循环：监听 + 增量重建
    while True:
        time.sleep(2)
        current_mtimes = collect_mtimes()

        if current_mtimes != last_mtimes:
            # 找出具体变化的文件
            changed = [
                f for f in current_mtimes
                if current_mtimes.get(f) != last_mtimes.get(f)
            ]
            print(f"\n检测到变化: {[f.name for f in changed]}")

            # 分类：模板/静态文件变化 → 全量重建；文章变化 → 增量重建
            structural_change = any(
                str(f).startswith(("templates", "static")) for f in changed
            )
            content_changes = [
                f for f in changed
                if str(f).startswith("content") and f.suffix == ".txt"
            ]

            if structural_change:
                # 模板或静态文件变了，所有页面都受影响
                build_all(output_dir=str(output_dir))
            elif content_changes:
                # 只重建变化的文章 + 首页
                for txt_file in content_changes:
                    build_single(txt_file, output_dir=str(output_dir))
                # 首页始终需要重建（列表可能变化）
                _rebuild_index(output_dir)
            else:
                build_all(output_dir=str(output_dir))

            last_mtimes = current_mtimes


def _rebuild_index(output_dir):
    """仅重建首页（不重新扫描全部文章）"""
    from blog.builder import build_all
    # 简单实现：直接调用 build_all（已排序的文章列表始终一致）
    build_all(output_dir=str(output_dir))
