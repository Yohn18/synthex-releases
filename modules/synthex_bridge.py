# -*- coding: utf-8 -*-
"""
modules/synthex_bridge.py
HTTP bridge server — phone opens http://PC_IP:PORT in browser.
Provides Vysor-like companion panel without requiring an APK.

Can be "installed" as PWA: Chrome → Add to Home Screen → acts like an app.
"""
import concurrent.futures
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from core.logger import get_logger

logger = get_logger("synthex_bridge")

_DEFAULT_PORT = 8765
_COMPANION_HTML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "synthex_companion.html")


def _get_local_ip() -> str:
    """Best-guess LAN IP for this PC."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


class _State:
    """Shared mutable state between HTTP handler and Synthex app."""
    def __init__(self):
        self.lock         = threading.Lock()
        self.macros: list = []         # current macro rules
        self.devices: list = []        # connected ADB devices
        self.mirror_serial: str = ""   # currently mirrored serial
        self.last_command: dict = {}   # last command received from phone
        self.command_queue: list = []  # pending commands for Synthex to process
        self.macro_engine  = None      # reference to MacroEngine


class SynthexBridge:
    """
    Lightweight HTTP server. Phone opens http://PC_IP:PORT.
    Synthex app updates state; phone polls /api/status every 3s.
    Phone POSTs to /api/command to trigger actions.
    """

    def __init__(self, adb_manager=None, port: int = _DEFAULT_PORT):
        self._adb      = adb_manager
        self._port     = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="BridgeAdb")
        self.state  = _State()
        self.on_command: callable | None = None   # callback(cmd_dict)

    @property
    def running(self) -> bool:
        return (self._server is not None
                and self._thread is not None
                and self._thread.is_alive())

    @property
    def url(self) -> str:
        return "http://{}:{}".format(_get_local_ip(), self._port)

    def update_status(self, macros=None, devices=None, mirror_serial=None):
        with self.state.lock:
            if macros      is not None: self.state.macros        = macros
            if devices     is not None: self.state.devices       = devices
            if mirror_serial is not None: self.state.mirror_serial = mirror_serial

    def pop_commands(self) -> list:
        with self.state.lock:
            cmds = list(self.state.command_queue)
            self.state.command_queue.clear()
            return cmds

    def start(self) -> bool:
        if self.running:
            return True
        state    = self.state
        adb      = self._adb
        on_cmd   = self.on_command
        executor = self._executor

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass  # silence access log

            def _send(self, code: int, ctype: str, body: bytes):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self):
                parsed = urlparse(self.path)
                path   = parsed.path.rstrip("/") or "/"

                if path == "/" or path == "/index.html":
                    if os.path.isfile(_COMPANION_HTML):
                        with open(_COMPANION_HTML, "rb") as f:
                            body = f.read()
                    else:
                        body = b"<h1>Synthex Companion</h1><p>synthex_companion.html not found</p>"
                    self._send(200, "text/html; charset=utf-8", body)

                elif path == "/api/status":
                    with state.lock:
                        payload = {
                            "macros":        state.macros,
                            "devices":       state.devices,
                            "mirror_serial": state.mirror_serial,
                            "ts":            time.time(),
                        }
                    self._send(200, "application/json",
                               json.dumps(payload).encode())

                elif path == "/manifest.json":
                    manifest = {
                        "name": "Synthex",
                        "short_name": "Synthex",
                        "start_url": "/",
                        "display": "standalone",
                        "background_color": "#0a0a0f",
                        "theme_color": "#6c4aff",
                        "icons": []
                    }
                    self._send(200, "application/json",
                               json.dumps(manifest).encode())

                else:
                    self._send(404, "text/plain", b"Not found")

            def do_POST(self):
                parsed = urlparse(self.path)
                path   = parsed.path.rstrip("/")

                length = int(self.headers.get("Content-Length", 0))
                body_raw = self.rfile.read(length) if length else b""
                try:
                    cmd = json.loads(body_raw) if body_raw else {}
                except Exception:
                    cmd = {}

                if path == "/api/command":
                    cmd["_ts"] = time.time()
                    with state.lock:
                        state.command_queue.append(cmd)
                        state.last_command = cmd
                    if on_cmd:
                        try:
                            on_cmd(cmd)
                        except Exception:
                            pass
                    self._send(200, "application/json", b'{"ok":true}')

                elif path == "/api/adb":
                    # Direct ADB shell command from companion
                    action = cmd.get("action", "")
                    serial = cmd.get("serial", "")
                    result = {"ok": False, "msg": ""}
                    if adb and adb.available:
                        s_args = ["-s", serial] if serial else []
                        def _run_adb(action=action, s_args=s_args, cmd=cmd):
                            if action == "tap":
                                x, y = cmd.get("x", 540), cmd.get("y", 960)
                                rc, out, err = adb._run(
                                    *s_args, "shell", "input", "tap", str(x), str(y))
                                return {"ok": rc == 0, "msg": out or err}
                            elif action == "swipe":
                                x1,y1 = cmd.get("x1",540), cmd.get("y1",300)
                                x2,y2 = cmd.get("x2",540), cmd.get("y2",1200)
                                ms     = cmd.get("ms", 350)
                                rc, out, err = adb._run(
                                    *s_args, "shell", "input", "swipe",
                                    str(x1),str(y1),str(x2),str(y2),str(ms))
                                return {"ok": rc == 0, "msg": out or err}
                            elif action == "key":
                                kc = cmd.get("keycode", 3)
                                rc, out, err = adb._run(
                                    *s_args, "shell", "input", "keyevent", str(kc))
                                return {"ok": rc == 0, "msg": out or err}
                            elif action == "text":
                                txt = cmd.get("text", "")
                                rc, out, err = adb._run(
                                    *s_args, "shell", "input", "text", txt)
                                return {"ok": rc == 0, "msg": out or err}
                            return {"ok": False, "msg": "unknown action"}
                        try:
                            result = executor.submit(_run_adb).result(timeout=10)
                        except Exception as e:
                            result = {"ok": False, "msg": str(e)}
                    self._send(200, "application/json",
                               json.dumps(result).encode())
                else:
                    self._send(404, "text/plain", b"Not found")

        try:
            self._server = ThreadingHTTPServer(("0.0.0.0", self._port), _Handler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True, name="SynthexBridge")
            self._thread.start()
            logger.info("SynthexBridge started at %s", self.url)
            return True
        except Exception as e:
            logger.error("SynthexBridge start failed: %s", e)
            self._server = None
            return False

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None
        logger.info("SynthexBridge stopped.")
