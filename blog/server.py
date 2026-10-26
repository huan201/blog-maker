"""本地预览服务器 + 编辑器后端。

安全与稳定性要点：

* **只监听 127.0.0.1**：默认不让同一局域网的人直接改你的文章。
* **防路径穿越**：所有文件操作都经过文件名白名单 + 扩展名白名单 + safe_join。
* **ThreadingHTTPServer**：构建时页面不会卡住。
* **查询串不打断路由**：先用 urlsplit 解析再匹配。
* **防抖的文件监听**：保存一次不会触发多轮全量重建。
* **上传落在 static/**：进仓库、能部署，而不是放在会被清空的 dist 里。
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .builder import Builder
from .config import Config
from .content import RESERVED_FILES, parse_frontmatter
from .utils import safe_join

# 上传文件允许的扩展名，避免有人往仓库里塞可执行文件
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".bmp", ".ico"}
FILE_EXT = IMAGE_EXT | {
    ".pdf", ".zip", ".rar", ".7z", ".tar", ".gz", ".txt", ".md", ".csv",
    ".json", ".ipynb", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".py", ".js", ".ts", ".mp3", ".mp4", ".webm", ".wav",
}
MAX_UPLOAD_BYTES = 32 * 1024 * 1024  # 32MB


class Site:
    """一次 serve 会话的共享状态。"""

    def __init__(self, config: Config, include_drafts: bool):
        self.config = config
        self.include_drafts = include_drafts
        self.lock = threading.Lock()
        self.last_summary = ""
        self.last_build = 0.0

    def rebuild(self, clean: bool = False) -> str:
        with self.lock:
            result = Builder(self.config, include_drafts=self.include_drafts).build(clean=clean)
            self.last_summary = result.summary()
            self.last_build = time.time()
            for warning in result.warnings:
                print("  [警告] {}".format(warning))
            return self.last_summary


def _make_handler(site: Site):
    config = site.config
    content_dir = config.content_dir
    static_dir = config.static_dir
    output_dir = config.output_dir

    class BlogHandler(SimpleHTTPRequestHandler):
        server_version = "MiniBlog/2.0"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(output_dir), **kwargs)

        # --- 路由 ---------------------------------------------------
        def do_GET(self):
            route = urlsplit(self.path)
            path = unquote(route.path)

            if path in ("/editor", "/editor/"):
                self._serve_editor()
            elif path == "/api/posts":
                self._api_list_posts()
            elif path.startswith("/api/posts/"):
                self._api_get_post(path[len("/api/posts/"):])
            elif path == "/api/config":
                self._api_config()
            elif path.startswith("/api/"):
                self.send_error(404, "Unknown API")
            else:
                super().do_GET()

        def do_POST(self):
            route = urlsplit(self.path)
            path = unquote(route.path)

            if path.startswith("/api/upload"):
                query = parse_qs(route.query)
                self._api_upload(query.get("type", ["image"])[0])
            elif path.startswith("/api/posts/"):
                self._api_save_post(path[len("/api/posts/"):])
            elif path == "/api/build":
                self._api_build()
            else:
                self._error_json(405, "Method Not Allowed")

        def do_DELETE(self):
            route = urlsplit(self.path)
            path = unquote(route.path)
            if path.startswith("/api/posts/"):
                self._api_delete_post(path[len("/api/posts/"):])
            else:
                self._error_json(405, "Method Not Allowed")

        # --- 日志 ---------------------------------------------------
        def log_message(self, fmt, *args):
            # 静态资源不刷屏，只记录 API 请求和错误
            try:
                message = fmt % args
            except (TypeError, ValueError):
                message = str(args)
            quiet = "/api/" not in message and "/editor" not in message
            is_error = re.search(r"\s[45]\d\d\s", message) is not None
            if not quiet or is_error:
                print("  [{}] {}".format(self.command, message))

        # --- 编辑器 -------------------------------------------------
        def _serve_editor(self):
            editor = config.templates_dir / "editor.html"
            if not editor.is_file():
                self.send_error(404, "editor.html not found")
                return
            html = editor.read_text(encoding="utf-8")
            html = html.replace("{{ site_title }}", str(config.get("site.title", "我的博客")))
            self._send("text/html; charset=utf-8", html.encode("utf-8"))

        # --- 文章 API -----------------------------------------------
        def _resolve_content(self, name: str) -> Path:
            """把 URL 里的文件名安全地解析成文章目录下的路径。"""
            name = name.strip()
            if not name or "/" in name or "\\" in name or name in (".", ".."):
                raise ValueError("非法文件名")
            if not name.endswith(".txt"):
                raise ValueError("只允许 .txt 文件")
            if name in RESERVED_FILES or name.startswith("_"):
                raise ValueError("该文件由构建器保留，不能用编辑器修改")
            return safe_join(content_dir, name)

        def _api_list_posts(self):
            posts = []
            if content_dir.is_dir():
                files = sorted(
                    (
                        f for f in content_dir.glob("*.txt")
                        if f.name not in RESERVED_FILES and not f.name.startswith("_")
                    ),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )
                for item in files:
                    try:
                        meta, _ = parse_frontmatter(item.read_text(encoding="utf-8"))
                        title = meta.get("title") or item.stem
                    except (OSError, UnicodeDecodeError):
                        title = "解析失败：{}".format(item.stem)
                        meta = {}
                    posts.append(
                        {
                            "filename": item.name,
                            "title": title,
                            "date": meta.get("date", ""),
                            "tags": meta.get("tags", ""),
                            "mtime": item.stat().st_mtime,
                        }
                    )
            self._send_json(posts)

        def _api_config(self):
            self._send_json(
                {
                    "siteTitle": config.get("site.title", "我的博客"),
                    "comments": config.section("comments"),
                    "metrics": config.section("metrics"),
                }
            )

        def _api_get_post(self, raw_name: str):
            try:
                path = self._resolve_content(raw_name)
            except ValueError as exc:
                self._error_json(400, str(exc))
                return
            if not path.is_file():
                self._error_json(404, "文章不存在")
                return
            self._send(
                "text/plain; charset=utf-8",
                path.read_text(encoding="utf-8").encode("utf-8"),
            )

        def _api_save_post(self, raw_name: str):
            try:
                path = self._resolve_content(raw_name)
            except ValueError as exc:
                self._error_json(400, str(exc))
                return

            body = self._read_body().decode("utf-8", errors="replace")
            if not body.strip():
                self._error_json(400, "内容为空")
                return

            content_dir.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".txt.tmp")
            temp.write_text(body, encoding="utf-8")
            temp.replace(path)  # 原子写入，断电也不会留下半个文件

            action = "更新" if path.exists() else "新建"
            print("  [保存] {} {}".format(action, path.name))
            try:
                summary = site.rebuild()
                self._send_json({"ok": True, "filename": path.name, "build": summary})
            except Exception as exc:  # noqa: BLE001
                print("  [错误] 重建失败：{}".format(exc))
                self._send_json(
                    {"ok": True, "filename": path.name, "build": "构建失败: {}".format(exc)}
                )

        def _api_delete_post(self, raw_name: str):
            try:
                path = self._resolve_content(raw_name)
            except ValueError as exc:
                self._error_json(400, str(exc))
                return
            if not path.is_file():
                self._error_json(404, "文章不存在")
                return
            path.unlink()
            print("  [删除] {}".format(path.name))
            try:
                summary = site.rebuild()
            except Exception as exc:  # noqa: BLE001
                summary = "构建失败: {}".format(exc)
            self._send_json({"ok": True, "build": summary})

        def _api_build(self):
            try:
                summary = site.rebuild(clean=False)
            except Exception as exc:  # noqa: BLE001
                self._error_json(500, "构建失败: {}".format(exc))
                return
            self._send_json({"ok": True, "build": summary})

        # --- 上传 ---------------------------------------------------
        def _api_upload(self, upload_type: str):
            try:
                self._do_upload(upload_type)
            except ValueError as exc:
                self._error_json(400, str(exc))
            except Exception as exc:  # noqa: BLE001
                print("  [上传错误] {}".format(exc))
                self._error_json(500, "上传失败")

        def _do_upload(self, upload_type: str):
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                raise ValueError("Content-Type 必须是 multipart/form-data")

            match = re.search(r'boundary=("?)([^";\s]+)\1', content_type)
            if not match:
                raise ValueError("无法解析 multipart boundary")
            boundary = match.group(2).encode()

            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0:
                raise ValueError("Content-Length 为 0")
            if length > MAX_UPLOAD_BYTES:
                raise ValueError("文件超过 {} MB 限制".format(MAX_UPLOAD_BYTES // (1024 * 1024)))

            body = self.rfile.read(length)
            delimiter = b"\r\n--" + boundary
            if body.endswith(b"\r\n"):
                body = body[:-2]

            file_data = None
            filename = ""
            for part in body.split(delimiter):
                if b"filename=" not in part:
                    continue
                split_at = part.find(b"\r\n\r\n")
                if split_at == -1:
                    continue
                header = part[:split_at].decode("utf-8", errors="replace")
                found = re.search(r'filename="?([^";\r\n]+)"?', header)
                if found:
                    filename = found.group(1)
                file_data = part[split_at + 4:]
                break

            if file_data is None:
                raise ValueError("没有找到上传的文件")

            file_data = file_data.rstrip(b"\r\n")

            # 只取最后一段文件名，防止 ../../evil.png
            filename = Path(filename.replace("\\", "/")).name
            filename = re.sub(r"[^\w.\u4e00-\u9fff\- ]", "_", filename).strip()
            if not filename or filename in (".", ".."):
                raise ValueError("文件名为空")

            suffix = Path(filename).suffix.lower()
            allowed = IMAGE_EXT if upload_type == "image" else FILE_EXT
            if suffix not in allowed:
                raise ValueError("不支持的文件类型：{}".format(suffix or "(无扩展名)"))

            subdir = "images" if upload_type == "image" else "attachments"
            target_dir = static_dir / subdir
            target_dir.mkdir(parents=True, exist_ok=True)
            target = safe_join(static_dir, subdir, filename)
            target.write_bytes(file_data)

            # 同步一份到输出目录，立刻可以预览
            dist_dir = output_dir / "static" / subdir
            dist_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(target), str(dist_dir / filename))

            print("  [上传] {} -> {}".format(filename, target.relative_to(config.root)))
            self._send_json(
                {
                    "ok": True,
                    "path": "static/{}/{}".format(subdir, filename),
                    "filename": filename,
                    "size": len(file_data),
                }
            )

        # --- 工具 ---------------------------------------------------
        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", 0) or 0)
            return self.rfile.read(length) if length else b""

        def _send_json(self, data):
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send("application/json; charset=utf-8", payload)

        def _error_json(self, status, message):
            payload = json.dumps({"ok": False, "error": message}, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _send(self, content_type, body: bytes):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def end_headers(self):
            # 本地预览永远不缓存，避免改了看不到效果（API 响应除外）
            if not self.path.startswith("/api/"):
                self.send_header("Cache-Control", "no-cache, must-revalidate")
            super().end_headers()

    return BlogHandler


def _snapshot(paths) -> dict:
    state = {}
    for root in paths:
        root = Path(root)
        if not root.is_dir():
            continue
        for item in root.rglob("*"):
            if item.is_file():
                try:
                    state[item] = item.stat().st_mtime
                except OSError:
                    continue
    return state


def serve(config: Config, host: str = "127.0.0.1", port: int = 8000,
          watch: bool = True, include_drafts: bool = False) -> None:
    """启动预览服务器（前台阻塞）。"""
    site = Site(config, include_drafts=include_drafts)

    print("正在构建…")
    print("  " + site.rebuild(clean=False))

    handler = _make_handler(site)
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True

    shown_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    print("")
    print("  预览:   http://{}:{}".format(shown_host, port))
    print("  编辑器: http://{}:{}/editor".format(shown_host, port))
    print("  文章目录: {}".format(config.content_dir))
    print("  输出目录: {}".format(config.output_dir))
    print("  停止:   Ctrl+C")
    print("")

    if watch:
        thread = threading.Thread(target=_watch_loop, args=(site,), daemon=True)
        thread.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


def _watch_loop(site: Site) -> None:
    """极简文件监听：轮询 mtime + 防抖，变更后全量重建。"""
    config = site.config
    watched = [config.content_dir, config.templates_dir, config.static_dir]
    upload_dirs = [
        str(config.static_dir / "images"),
        str(config.static_dir / "attachments"),
    ]

    def ignored(path) -> bool:
        text = str(path)
        return any(text.startswith(prefix) for prefix in upload_dirs)

    last = _snapshot(watched)
    while True:
        time.sleep(1.0)
        current = _snapshot(watched)
        changed = [
            path for path in set(current) | set(last)
            if current.get(path) != last.get(path) and not ignored(path)
        ]
        if changed:
            time.sleep(0.4)  # 防抖：等编辑器把这一批文件写完
            current = _snapshot(watched)
            names = sorted({path.name for path in changed})
            print("\n检测到变化: {}".format(", ".join(names[:5]) + (" …" if len(names) > 5 else "")))
            try:
                print("  " + site.rebuild())
            except Exception as exc:  # noqa: BLE001
                print("  [错误] 重建失败：{}".format(exc))
        last = current
