import time
import json
import threading
import shutil
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler


def serve(output_dir="dist", port=8000):
    """启动本地预览服务器 + 文件监听自动重建"""
    from blog.builder import (build_all, build_single, parse_meta,
                              _render_body, render)

    output_dir = Path(output_dir)
    content_dir = Path("content")

    # --- 自定义 Handler：文件服务 + /api 路由 + /editor ---
    class BlogHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            # 默认从 dist/ 提供静态文件
            super().__init__(*args, directory=str(output_dir), **kwargs)

        def do_GET(self):
            if self.path in ("/editor", "/editor.html"):
                self._serve_editor()
            elif self.path == "/api/posts":
                self._api_list_posts()
            elif self.path.startswith("/api/posts/"):
                self._api_get_post()
            else:
                super().do_GET()

        def do_POST(self):
            if self.path.startswith("/api/upload"):
                self._api_upload()
            elif self.path.startswith("/api/posts/"):
                self._api_save_post()
            else:
                self.send_error(405, "Method Not Allowed")

        def log_message(self, format, *args):
            # 静默静态文件日志，只打印 API 请求
            if "/api/" in str(args) or "/editor" in str(args):
                print(f"  [{self.command}] {args[0]}")

        # --- /editor：返回编辑器页面 ---
        def _serve_editor(self):
            editor_file = Path("templates") / "editor.html"
            if editor_file.is_file():
                html = editor_file.read_text(encoding="utf-8")
                self._send("text/html; charset=utf-8", html.encode("utf-8"))
            else:
                self.send_error(404, "Editor not found")

        # --- API：文章列表 ---
        def _api_list_posts(self):
            posts = []
            for f in sorted(content_dir.glob("*.txt"), key=lambda x: x.stat().st_mtime, reverse=True):
                try:
                    raw = f.read_text(encoding="utf-8")
                    meta, _ = parse_meta(raw)
                    posts.append({
                        "filename": f.name,
                        "title": meta.get("title", "无标题"),
                        "date": meta.get("date", ""),
                        "tags": meta.get("tags", ""),
                        "mtime": f.stat().st_mtime,
                    })
                except Exception:
                    posts.append({"filename": f.name, "title": "解析失败", "date": "", "tags": "", "mtime": 0})
            self._send_json(posts)

        # --- API：读取单篇文章 ---
        def _api_get_post(self):
            filename = self.path.replace("/api/posts/", "")
            filepath = content_dir / filename
            if not filepath.is_file() or filepath.suffix != ".txt":
                self.send_error(404, "Post not found")
                return
            content = filepath.read_text(encoding="utf-8")
            self._send("text/plain; charset=utf-8", content.encode("utf-8"))

        # --- API：保存文章 ---
        def _api_save_post(self):
            filename = self.path.replace("/api/posts/", "")
            filepath = content_dir / filename
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            filepath.write_text(body, encoding="utf-8")
            print(f"  [保存] {filename}")
            # 触发重建
            try:
                build_single(filepath, output_dir=str(output_dir))
                _rebuild_index(output_dir)
            except Exception as e:
                print(f"  [警告] 重建失败: {e}")
            self._send_json({"ok": True, "filename": filename})

        # --- API：上传图片/附件 ---
        def _api_upload(self):
            try:
                self._do_upload()
            except Exception as e:
                print(f"  [上传错误] {e}")
                try:
                    self.send_error(500, str(e))
                except Exception:
                    pass

        def _do_upload(self):
            import re as _re
            from urllib.parse import urlparse, parse_qs

            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self.send_error(400, "Content-Type 不是 multipart/form-data")
                return

            # 提取 boundary
            m = _re.search(r'boundary=("?)([^";\s]+)\1', content_type)
            if not m:
                self.send_error(400, "无法解析 boundary")
                return
            boundary = m.group(2).encode()

            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                self.send_error(400, "Content-Length 为 0")
                return
            body = self.rfile.read(length)

            # 按 boundary 分隔各 part
            delimiter = b"\r\n--" + boundary
            # 先去掉末尾 closing delimiter（\r\n--boundary--）
            closing = delimiter + b"--"
            if body.endswith(b"\r\n"):
                body = body[:-2]
            if body.endswith(closing):
                body = body[: -len(closing)]

            parts = body.split(delimiter)
            file_data = None
            filename = "upload"
            for part in parts:
                if not part or b"filename=" not in part:
                    continue
                split_pos = part.find(b"\r\n\r\n")
                if split_pos == -1:
                    continue
                header = part[:split_pos].decode("utf-8", errors="replace")
                file_data = part[split_pos + 4:]
                fm = _re.search(r'filename="?([^";\r\n]+)"?', header)
                if fm:
                    filename = fm.group(1)
                break

            if not file_data:
                self.send_error(400, "未找到上传文件")
                return

            # 去掉末尾残留的 \r\n
            file_data = file_data.rstrip(b"\r\n")

            # 根据 query 参数决定目标子目录
            query = parse_qs(urlparse(self.path).query)
            upload_type = query.get("type", ["image"])[0]
            subdir = "images" if upload_type == "image" else "attachments"

            source_dir = Path("static") / subdir
            source_dir.mkdir(exist_ok=True)
            filepath = source_dir / filename
            filepath.write_bytes(file_data)

            dist_dir = output_dir / "static" / subdir
            dist_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(filepath), str(dist_dir / filename))

            url_path = f"static/{subdir}/{filename}"
            print(f"  [上传] {filename} -> {filepath}")
            self._send_json({"ok": True, "path": url_path, "filename": filename})

        # --- 工具：发送 JSON ---
        def _send_json(self, data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send("application/json; charset=utf-8", body)

        def _send(self, content_type, body):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def run_server():
        server = HTTPServer(("0.0.0.0", port), BlogHandler)
        print(f"服务器已启动: http://127.0.0.1:{port}")
        print(f"输出目录: {output_dir}")
        print(f"编辑器: http://127.0.0.1:{port}/editor")
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
            changed = [
                f for f in current_mtimes
                if current_mtimes.get(f) != last_mtimes.get(f)
            ]
            # 忽略 static/images/ 和 static/attachments/ 的变化
            # 这些由上传 API 自己处理，触发重建会导致连接重置
            changed = [
                f for f in changed
                if not str(f).startswith(("static\\images", "static\\attachments",
                                          "static/images", "static/attachments"))
            ]
            if not changed:
                last_mtimes = current_mtimes
                continue

            print(f"\n检测到变化: {[f.name for f in changed]}")

            structural_change = any(
                str(f).startswith(("templates", "static")) for f in changed
            )
            content_changes = [
                f for f in changed
                if str(f).startswith("content") and f.suffix == ".txt"
            ]

            if structural_change:
                build_all(output_dir=str(output_dir))
            elif content_changes:
                for txt_file in content_changes:
                    build_single(txt_file, output_dir=str(output_dir))
                _rebuild_index(output_dir)
            else:
                build_all(output_dir=str(output_dir))

            last_mtimes = current_mtimes


def _rebuild_index(output_dir):
    """仅重建首页"""
    from blog.builder import build_all
    build_all(output_dir=str(output_dir))
