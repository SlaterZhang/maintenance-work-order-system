#!/usr/bin/env python3
"""本机单端口统一入口（跨平台开发服务器）：静态托管 web/ + 反代 /a /b /c /d。

与服务器上的 ``deploy/nginx.conf`` 同口径，用于 Windows / macOS 本机演示：
nginx 在 Windows 上不好装，而直接用浏览器打开 ``web/index.html``（file://）
会踩两个坑——前端默认地址 /a /b /c /d 在 file:// 下解析成 file:///a 必然
fetch 失败；且 main.js 会把已保存的本机直连地址判为"公网不可达"而丢弃。
本脚本在 127.0.0.1:8888 起一个同源入口，前端零配置即可用。

  python scripts/dev_server.py              # 默认 127.0.0.1:8888
  python scripts/dev_server.py --port 9000  # 换端口
  python -m scripts.dev_server              # 等价

只用标准库（http.server / urllib.request），不依赖 fastapi 等运行期依赖，
因此在依赖尚未安装时也能先跑起来给个明确报错。

路由（与 nginx 一致）：
  /            → web/ 静态文件（index.html 为入口，缺省 index.html）
  /a/...       → 127.0.0.1:8101/...   （A 设备监测）
  /b/...       → 127.0.0.1:8102/...   （B 故障预警）
  /c/...       → 127.0.0.1:8103/...   （C 维修工单）
  /d/...       → 127.0.0.1:8104/...   （D 身份通知）

proxy_pass 尾斜杠语义：前缀被剥掉，后端只见 /api/v1/...（与 nginx 相同）。
"""

from __future__ import annotations

import argparse
import mimetypes
import posixpath
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = REPO_ROOT / "web"

# 服务前缀 → 后端端口（与 deploy/nginx.conf 的 location 段一一对应）
PROXY_ROUTES = {"a": 8101, "b": 8102, "c": 8103, "d": 8104}

DEFAULT_PORT = 8888
DEFAULT_HOST = "127.0.0.1"

# 这些请求头由本机代理层自己决定，不转发客户端/urllib 的版本
HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)

MIME_OVERRIDES = {
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def _log(message: str) -> None:
    print(message, flush=True)


class UnifiedEntryHandler(BaseHTTPRequestHandler):
    """静态文件 + 四服务反向代理。"""

    server_version = "ims-dev-server/1.0"
    protocol_version = "HTTP/1.1"

    # ---------- 基础 ----------
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        # 保持单行、带前缀，便于和 uvicorn 日志区分
        _log("[WEB ] %s - %s" % (self.address_string(), fmt % args))

    def _send_bytes(self, status: int, body: bytes, content_type: str,
                    extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_error_text(self, status: int, message: str) -> None:
        body = (message + "\n").encode("utf-8")
        self._send_bytes(status, body, "text/plain; charset=utf-8")

    # ---------- 静态 ----------
    def _resolve_static(self, url_path: str) -> Path | None:
        """把 URL 路径映射到 web/ 下的真实文件，防目录穿越。"""
        clean = posixpath.normpath(urllib.parse.unquote(url_path))
        # normpath 后仍可能以 .. 开头（如 /../x → ../x）
        clean = clean.lstrip("/")
        if clean in (".", ""):
            clean = "index.html"
        candidate = (WEB_ROOT / clean).resolve()
        try:
            candidate.relative_to(WEB_ROOT.resolve())
        except ValueError:
            return None  # 穿越到 web/ 之外
        if candidate.is_dir():
            candidate = candidate / "index.html"
        return candidate

    def _serve_static(self) -> None:
        path = self._resolve_static(self.path.split("?", 1)[0].split("#", 1)[0])
        if path is None:
            self._send_error_text(403, "403 Forbidden：路径越界")
            return
        if not path.is_file():
            if self.path.split("?", 1)[0] in ("/", "/index.html"):
                self._send_error_text(
                    404, f"404：找不到前端入口 {WEB_ROOT / 'index.html'}（web/ 目录是否完整？）"
                )
            else:
                self._send_error_text(404, f"404 Not Found：{self.path}")
            return
        try:
            body = path.read_bytes()
        except OSError as exc:
            self._send_error_text(500, f"500：读取 {path} 失败：{exc}")
            return
        content_type = MIME_OVERRIDES.get(path.suffix.lower())
        if content_type is None:
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self._send_bytes(200, body, content_type)

    # ---------- 代理 ----------
    def _proxy(self, prefix: str, port: int, body: bytes | None = None) -> None:
        # 前缀被剥掉：/a/api/v1/x → /api/v1/x（与 nginx proxy_pass 尾斜杠一致）
        rest = self.path[len(prefix):]
        if not rest.startswith("/"):
            rest = "/" + rest
        target = f"http://127.0.0.1:{port}{rest}"

        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP
        }
        # 让后端看到真实的 Host（部分服务端逻辑会读）
        headers["Host"] = f"127.0.0.1:{port}"
        headers["X-Real-IP"] = self.address_string()
        headers["X-Forwarded-For"] = self.address_string()
        headers["X-Forwarded-Proto"] = "http"

        request = urllib.request.Request(
            target, data=body, headers=headers, method=self.command
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as upstream:
                payload = upstream.read()
                status = upstream.status
                resp_headers = upstream.headers
        except urllib.error.HTTPError as exc:
            # 4xx/5xx 也是正常响应，原样透传给浏览器（前端要读 message/code）
            payload = exc.read()
            status = exc.code
            resp_headers = exc.headers
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            self._send_error_text(
                502,
                f"502 Bad Gateway：无法连接 {prefix.rstrip('/')} 服务"
                f"（127.0.0.1:{port}）。请确认四服务已启动"
                f"（scripts/start_all.ps1 或 scripts/start_all.sh），"
                f"原始错误：{reason}",
            )
            return
        except OSError as exc:
            self._send_error_text(502, f"502 Bad Gateway：{exc}")
            return

        self.send_response(status)
        for name, value in resp_headers.items():
            if name.lower() in HOP_BY_HOP:
                continue
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    # ---------- 分发 ----------
    def _dispatch(self, body: bytes | None = None) -> None:
        head = self.path.lstrip("/").split("/", 1)[0].split("?", 1)[0].lower()
        if head in PROXY_ROUTES:
            self._proxy("/" + head, PROXY_ROUTES[head], body)
        else:
            self._serve_static()

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch()

    def _read_body(self) -> bytes:
        length = self.headers.get("Content-Length")
        if not length:
            return b""
        try:
            return self.rfile.read(int(length))
        except (ValueError, OSError):
            return b""

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch(self._read_body())

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch(self._read_body())

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch(self._read_body())

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch(self._read_body())

    def do_OPTIONS(self) -> None:  # noqa: N802
        # 同源入口下浏览器一般不发预检；保留直连场景的兜底
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="本机单端口统一入口：静态托管 web/ 并反代 /a /b /c /d 到四服务"
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"监听地址（默认 {DEFAULT_HOST}）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"监听端口（默认 {DEFAULT_PORT}）")
    args = parser.parse_args(argv)

    if not (WEB_ROOT / "index.html").is_file():
        _log(f"[WEB ] 警告：未找到前端入口 {WEB_ROOT / 'index.html'}")

    server = ThreadingHTTPServer((args.host, args.port), UnifiedEntryHandler)
    _log(f"[WEB ] 统一入口已启动：http://{args.host}:{args.port}/")
    _log(f"[WEB ] 静态目录：{WEB_ROOT}")
    for prefix, port in PROXY_ROUTES.items():
        _log(f"[WEB ]   /{prefix}/  →  http://127.0.0.1:{port}/")
    _log("[WEB ] Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log("\n[WEB ] 已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
