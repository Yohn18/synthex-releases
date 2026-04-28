# -*- coding: utf-8 -*-
"""
modules/webhook_server.py
HTTP server yang menerima event dari Tasker / AutoNotification (Android).
Support WiFi (IP langsung) dan USB tunnel (adb reverse tcp:PORT tcp:PORT).

Endpoint:
    POST /event  — event umum (notifikasi, SMS, app_opened, dll)
    GET  /ping   — health check
"""
import json
import socket
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from core.logger import get_logger

logger = get_logger("webhook_server")

DEFAULT_PORT  = 7799
DEFAULT_TOKEN = "synthex"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default stdout logs

    def do_GET(self):
        if self.path == "/ping":
            self._respond(200, {"status": "ok", "app": "Synthex"})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        srv: "WebhookServer" = self.server._ws
        parsed = urlparse(self.path)
        if parsed.path not in ("/event", "/notify", "/sms"):
            self._respond(404, {"error": "unknown path"}); return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            self._respond(400, {"error": "bad json"}); return

        # Token auth
        token = data.get("token", "") or self.headers.get("X-Synthex-Token", "")
        if srv._token and token != srv._token:
            self._respond(401, {"error": "unauthorized"}); return

        srv._dispatch(data)
        self._respond(200, {"ok": True})

    def _respond(self, code: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class WebhookServer:
    """
    HTTP server untuk menerima event dari Tasker.

    Penggunaan:
        srv = WebhookServer(port=7799, token="synthex")
        srv.on_event = lambda ev: print(ev)
        srv.start()
        ...
        srv.stop()
    """

    def __init__(self, port: int = DEFAULT_PORT, token: str = DEFAULT_TOKEN):
        self._port    = port
        self._token   = token
        self._server: HTTPServer | None = None
        self._thread:  threading.Thread | None = None
        self._running = False
        self._lock    = threading.Lock()
        self._log: list[dict] = []  # max 300 events

        self.on_event = None  # callable(event_dict)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        if self._running:
            return True
        try:
            srv = HTTPServer(("0.0.0.0", self._port), _Handler)
            srv._ws = self
            self._server  = srv
            self._running = True
            self._thread  = threading.Thread(target=srv.serve_forever, daemon=True)
            self._thread.start()
            logger.info("WebhookServer listening on port %d", self._port)
            return True
        except Exception as exc:
            logger.error("WebhookServer start failed: %s", exc)
            self._running = False
            return False

    def stop(self):
        self._running = False
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._server = None
        logger.info("WebhookServer stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def port(self) -> int:
        return self._port

    # ── Event dispatch ────────────────────────────────────────────────────────

    def _dispatch(self, event: dict):
        event.setdefault("_ts", time.time())
        with self._lock:
            self._log.insert(0, event)
            if len(self._log) > 300:
                self._log.pop()
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as exc:
                logger.error("on_event error: %s", exc)

    def get_log(self) -> list[dict]:
        with self._lock:
            return list(self._log)

    # ── Network helpers ───────────────────────────────────────────────────────

    @staticmethod
    def get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    # ── USB tunnel helpers ────────────────────────────────────────────────────

    def setup_usb_tunnel(self, adb_path: str, serial: str = "") -> tuple[bool, str]:
        """adb reverse tcp:PORT tcp:PORT — HP bisa konek via USB ke localhost:PORT."""
        cmd = [adb_path]
        if serial:
            cmd += ["-s", serial]
        cmd += ["reverse", f"tcp:{self._port}", f"tcp:{self._port}"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                logger.info("USB tunnel OK: adb reverse tcp:%d tcp:%d", self._port, self._port)
                return True, ""
            return False, r.stderr.strip()
        except Exception as exc:
            return False, str(exc)

    def remove_usb_tunnel(self, adb_path: str, serial: str = ""):
        cmd = [adb_path]
        if serial:
            cmd += ["-s", serial]
        cmd += ["reverse", "--remove", f"tcp:{self._port}"]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except Exception:
            pass
