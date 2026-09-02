"""Localhost OAuth callback server for TikTok Ads."""

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .utils import logger

_code_container = {"code": None, "error": None}
_server_lock = threading.Lock()
_server_instance = None
_server_port = None


class CallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.debug("TikTok OAuth callback: " + format % args)

    def do_GET(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/callback"):
            self.send_response(404)
            self.end_headers()
            return
        params = parse_qs(parsed.query)
        error = params.get("error", [None])[0]
        code = params.get("auth_code", [None])[0] or params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        if error:
            _code_container["error"] = error
            html = f"<html><body><h1>Authorization failed</h1><p>{error}</p></body></html>"
        elif code:
            _code_container["code"] = code
            html = "<html><body><h1>TikTok Ads connected</h1><p>You can close this window.</p></body></html>"
        else:
            html = "<html><body><h1>Missing auth_code</h1></body></html>"
        self.wfile.write(html.encode("utf-8"))


def start_callback_server(preferred_port: int = 8080) -> int:
    global _server_instance, _server_port
    with _server_lock:
        if _server_instance is not None:
            return _server_port
        last_error = None
        for candidate in range(preferred_port, preferred_port + 20):
            try:
                server = HTTPServer(("127.0.0.1", candidate), CallbackHandler)
                _server_instance = server
                _server_port = candidate
                break
            except OSError as e:
                last_error = e
                continue
        else:
            raise RuntimeError(f"Could not bind TikTok OAuth callback server: {last_error}")
        _code_container["code"] = None
        _code_container["error"] = None
        thread = threading.Thread(target=_server_instance.serve_forever, daemon=True)
        thread.start()
        logger.info(f"TikTok OAuth callback server listening on 127.0.0.1:{_server_port}")
        return _server_port


def wait_for_code(timeout: int = 300) -> Optional[str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _code_container.get("code"):
            return _code_container["code"]
        if _code_container.get("error"):
            logger.error(f"TikTok OAuth error: {_code_container['error']}")
            return None
        time.sleep(0.5)
    return None
