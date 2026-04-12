# -*- coding: utf-8 -*-
"""ui/spy_window.py - Lightweight floating element inspector.

Like AutoHotkey Window Spy - instant cursor/window info via Windows API only.
CDP is used ONLY when user presses F8/CAPTURE (not continuously).
"""

import base64
import ctypes
import ctypes.wintypes
import json
import os
import socket
import struct
import threading
import tkinter as tk
import urllib.request

from core.logger import get_logger

# Palette
BG   = "#0A0A0F"; CARD = "#12121A"; ACC  = "#6C63FF"
FG   = "#E0DFFF"; MUT  = "#555575"; GRN  = "#4CAF88"
RED  = "#F06070"; YEL  = "#F0C060"; PRP  = "#9D5CF6"

# JS to read the hovered element (injected once on capture request)
_JS_INJECT = r"""
(function() {
    function getCSSSelector(el) {
        if (!el || el === document.body) return 'body';
        var parts = [], cur = el;
        while (cur && cur !== document.documentElement) {
            var sel = cur.tagName.toLowerCase();
            if (cur.id) { sel += '#' + cur.id; parts.unshift(sel); break; }
            var idx = 1, sib = cur.previousElementSibling;
            while (sib) { if (sib.tagName === cur.tagName) idx++; sib = sib.previousElementSibling; }
            if (idx > 1) sel += ':nth-of-type(' + idx + ')';
            parts.unshift(sel); cur = cur.parentElement;
        }
        return parts.join(' > ');
    }
    function getXPath(el) {
        if (!el) return '';
        var path = [], cur = el;
        while (cur && cur.nodeType === 1) {
            var idx = 1, sib = cur.previousElementSibling;
            while (sib) { if (sib.tagName === cur.tagName) idx++; sib = sib.previousElementSibling; }
            path.unshift(cur.tagName.toLowerCase() + '[' + idx + ']');
            cur = cur.parentElement;
        }
        return '/' + path.join('/');
    }
    if (!window.__sx_spy_listener) {
        window.__sx_spy_listener = true;
        window.__sx_spy = {};
        document.addEventListener('mousemove', function(e) {
            var el = document.elementFromPoint(e.clientX, e.clientY);
            if (el) {
                var css = getCSSSelector(el);
                var xpath = getXPath(el);
                window.__sx_spy = {
                    tagName: el.tagName.toLowerCase(),
                    text: (el.innerText || el.value || el.textContent || '').trim().slice(0, 100),
                    id: el.id || '',
                    className: (typeof el.className === 'string' ? el.className : '') || '',
                    value: el.value || '',
                    href: el.href || '',
                    selector: css, css_selector: css, xpath: xpath
                };
            }
        }, true);
    }
    return 'ok';
})();
"""
_JS_READ = "JSON.stringify(window.__sx_spy || {})"


# ---------------------------------------------------------------------------
# Minimal CDP WebSocket client (stdlib only, no external deps)
# ---------------------------------------------------------------------------

class _CDP:
    def __init__(self, ws_url, timeout=4.0):
        url = ws_url.replace("ws://", "").replace("wss://", "")
        slash = url.find("/")
        host_port = url[:slash] if slash != -1 else url
        path      = url[slash:] if slash != -1 else "/"
        host, port = (host_port.rsplit(":", 1) if ":" in host_port
                      else (host_port, "9222"))
        self._sock = socket.create_connection((host, int(port)), timeout=timeout)
        self._sock.settimeout(None)
        self._send_lock = threading.Lock()
        self._id = 0
        self._pending = {}
        self._plock   = threading.Lock()
        self._closed  = False
        self._do_handshake(host, port, path)
        threading.Thread(target=self._reader, daemon=True,
                         name="cdp-reader").start()

    def _do_handshake(self, host, port, path):
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET {} HTTP/1.1\r\n"
            "Host: {}:{}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).format(path, host, port, key).encode()
        self._sock.sendall(req)
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("CDP handshake: connection closed")
            resp += chunk
        if b"101 " not in resp:
            raise ConnectionError("CDP handshake failed")

    def _reader(self):
        buf = b""
        try:
            while not self._closed:
                chunk = self._sock.recv(8192)
                if not chunk:
                    break
                buf += chunk
                while True:
                    frame, buf = self._parse_frame(buf)
                    if frame is None:
                        break
                    self._dispatch(frame)
        except Exception:
            pass
        finally:
            self._closed = True
            with self._plock:
                for entry in self._pending.values():
                    entry[0].set()

    @staticmethod
    def _parse_frame(buf):
        if len(buf) < 2:
            return None, buf
        b1     = buf[1]
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        offset = 2
        if length == 126:
            if len(buf) < 4:
                return None, buf
            length = struct.unpack(">H", buf[2:4])[0]
            offset = 4
        elif length == 127:
            if len(buf) < 10:
                return None, buf
            length = struct.unpack(">Q", buf[2:10])[0]
            offset = 10
        if masked:
            offset += 4
        if len(buf) < offset + length:
            return None, buf
        payload = buf[offset: offset + length]
        if masked:
            mask    = buf[offset - 4: offset]
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        opcode = buf[0] & 0x0F
        rest   = buf[offset + length:]
        if opcode in (1, 2):
            return payload.decode("utf-8", errors="replace"), rest
        return "", rest

    def _dispatch(self, text):
        if not text:
            return
        try:
            data = json.loads(text)
        except Exception:
            return
        msg_id = data.get("id")
        if msg_id is not None:
            with self._plock:
                entry = self._pending.get(msg_id)
            if entry:
                entry[1] = data.get("result")
                entry[0].set()

    def _send_frame(self, payload):
        n    = len(payload)
        mask = os.urandom(4)
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if n < 126:
            header = bytes([0x81, 0x80 | n])
        elif n < 65536:
            header = bytes([0x81, 0xFE]) + struct.pack(">H", n)
        else:
            header = bytes([0x81, 0xFF]) + struct.pack(">Q", n)
        with self._send_lock:
            self._sock.sendall(header + mask + data)

    def cmd(self, method, params=None, timeout=3.0):
        with self._plock:
            self._id += 1
            cmd_id = self._id
            evt    = threading.Event()
            self._pending[cmd_id] = [evt, None]
        msg = json.dumps({"id": cmd_id, "method": method,
                          "params": params or {}})
        self._send_frame(msg.encode())
        evt.wait(timeout)
        with self._plock:
            entry = self._pending.pop(cmd_id, [None, None])
        return entry[1]

    def evaluate(self, expression, timeout=2.0):
        res = self.cmd("Runtime.evaluate",
                       {"expression": expression, "returnByValue": True},
                       timeout=timeout)
        if res and "result" in res:
            return res["result"].get("value")
        return None

    def close(self):
        self._closed = True
        try:
            self._sock.close()
        except Exception:
            pass


class _CDPTracker:
    """Connect to Chrome CDP on demand, inject JS, read element under cursor."""

    CDP_PORT = 9222

    def __init__(self):
        self._cdp      = None
        self._lock     = threading.Lock()
        self._injected = False

    def get_element_now(self):
        """Connect (if needed), inject JS, return element dict or {}."""
        cdp = self._connect_if_needed()
        if cdp is None:
            return {}
        try:
            if not self._injected:
                result = cdp.evaluate(_JS_INJECT, timeout=3.0)
                self._injected = (result == "ok")
            raw = cdp.evaluate(_JS_READ, timeout=2.0)
            if not raw:
                return {}
            info = json.loads(raw) if isinstance(raw, str) else {}
            return info if info.get("tagName") else {}
        except Exception:
            with self._lock:
                self._cdp      = None
                self._injected = False
            return {}

    def _connect_if_needed(self):
        with self._lock:
            cdp = self._cdp
        if cdp and not cdp._closed:
            return cdp
        try:
            raw  = urllib.request.urlopen(
                "http://localhost:{}/json".format(self.CDP_PORT),
                timeout=2.0).read()
            tabs = json.loads(raw)
            ws_url = None
            for tab in tabs:
                if tab.get("type") == "page" and tab.get("webSocketDebuggerUrl"):
                    ws_url = tab["webSocketDebuggerUrl"]
                    break
            if not ws_url:
                return None
            cdp = _CDP(ws_url, timeout=3.0)
            with self._lock:
                self._cdp      = cdp
                self._injected = False
            return cdp
        except Exception:
            return None

    def close(self):
        with self._lock:
            if self._cdp:
                self._cdp.close()
                self._cdp = None


# ---------------------------------------------------------------------------
# FloatingSpyWindow - Lightweight, like AutoHotkey Window Spy
# ---------------------------------------------------------------------------

class FloatingSpyWindow:
    """
    280x400 always-on-top draggable window.

    Cursor position and window info update every 100ms via Windows API only.
    Element info only updates when CAPTURE / F8 is pressed (uses CDP then).
    """

    def __init__(self, parent, browser=None, on_capture=None,
                 on_use_in_macro=None):
        # browser arg kept for backwards-compat; not used
        self.on_capture      = on_capture
        self.on_use_in_macro = on_use_in_macro
        self.logger          = get_logger("spy_window")
        self._tracker        = _CDPTracker()

        self._pinned  = False
        self._drag_x  = 0
        self._drag_y  = 0
        self._poll_id = None
        self._f8_listener = None

        # Try win32gui for window-under-cursor info
        try:
            import win32gui
            self._win32gui = win32gui
        except ImportError:
            self._win32gui = None

        self._win = tk.Toplevel(parent)
        self._win.title("Synthex Spy")
        self._win.configure(bg=BG)
        self._win.attributes("-topmost", True)
        self._win.resizable(False, False)
        self._win.overrideredirect(True)

        self._build()

        sw = self._win.winfo_screenwidth()
        self._win.geometry("280x400+{}+60".format(sw - 300))
        self._win.update_idletasks()

        self._start_poll()
        self._start_f8()

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _build(self):
        win = self._win

        # Header (draggable)
        hdr = tk.Frame(win, bg=ACC, height=32, cursor="fleur")
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  Synthex Spy", bg=ACC, fg=BG,
                 font=("Segoe UI", 10, "bold")).pack(side="left", pady=5)
        tk.Button(hdr, text="X", bg=ACC, fg=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=8, cursor="hand2",
                  activebackground=RED, activeforeground=BG,
                  command=self.close).pack(side="right", padx=2, pady=4)
        self._bind_drag(hdr)

        # Mouse Position
        mp = tk.Frame(win, bg=CARD, padx=10, pady=6)
        mp.pack(fill="x", padx=5, pady=(5, 0))
        tk.Label(mp, text="Mouse Position", bg=CARD, fg=MUT,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w")
        self._xy_var = tk.StringVar(value="X: 0    Y: 0")
        tk.Label(mp, textvariable=self._xy_var, bg=CARD, fg=FG,
                 font=("Consolas", 10)).pack(anchor="w")
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        tk.Label(mp, text="Screen: {} x {}".format(sw, sh), bg=CARD, fg=MUT,
                 font=("Consolas", 8)).pack(anchor="w")

        # Window under cursor
        wf = tk.Frame(win, bg=CARD, padx=10, pady=6)
        wf.pack(fill="x", padx=5, pady=(4, 0))
        tk.Label(wf, text="Window", bg=CARD, fg=MUT,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w")
        self._win_title_var = tk.StringVar(value="Title: -")
        self._win_class_var = tk.StringVar(value="Class: -")
        self._win_hwnd_var  = tk.StringVar(value="Handle: -")
        for v in (self._win_title_var, self._win_class_var, self._win_hwnd_var):
            tk.Label(wf, textvariable=v, bg=CARD, fg=FG,
                     font=("Consolas", 8), anchor="w",
                     wraplength=252).pack(anchor="w")

        # Element info (only updated on F8/CAPTURE)
        ef = tk.Frame(win, bg=CARD, padx=10, pady=6)
        ef.pack(fill="x", padx=5, pady=(4, 0))
        tk.Label(ef, text="Element  (press F8 to capture)", bg=CARD, fg=MUT,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w")

        self._elem_vars = {}
        for label, key in [
            ("Tag",   "tagName"),
            ("Text",  "text"),
            ("ID",    "id"),
            ("CSS",   "css_selector"),
            ("XPath", "xpath"),
            ("Value", "value"),
        ]:
            row = tk.Frame(ef, bg=CARD)
            row.pack(fill="x", pady=1)
            tk.Label(row, text="{:<6}:".format(label), bg=CARD, fg=MUT,
                     font=("Consolas", 8), width=8, anchor="w").pack(side="left")
            var = tk.StringVar(value="-")
            tk.Label(row, textvariable=var, bg=CARD, fg=FG,
                     font=("Consolas", 8), anchor="w",
                     wraplength=185).pack(side="left")
            self._elem_vars[key] = var

        # Buttons row
        btm = tk.Frame(win, bg=BG, padx=6, pady=8)
        btm.pack(fill="x", side="bottom")

        tk.Button(btm, text="CAPTURE  F8", bg=ACC, fg=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=10, pady=6, cursor="hand2",
                  activebackground="#8880FF", activeforeground=BG,
                  command=self._capture).pack(side="left", expand=True,
                                              fill="x", padx=(0, 3))

        self._pin_var = tk.StringVar(value="PIN")
        self._pin_btn = tk.Button(btm, textvariable=self._pin_var,
                                   bg=CARD, fg=FG,
                                   font=("Segoe UI", 9, "bold"),
                                   relief="flat", bd=0,
                                   padx=10, pady=6, cursor="hand2",
                                   command=self._toggle_pin)
        self._pin_btn.pack(side="left", padx=(0, 3))

        tk.Button(btm, text="X", bg=RED, fg=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=10, pady=6, cursor="hand2",
                  command=self.close).pack(side="left")

        # Status line
        self._status_var = tk.StringVar(value="Hover cursor anywhere")
        tk.Label(win, textvariable=self._status_var, bg=BG, fg=MUT,
                 font=("Segoe UI", 7), wraplength=268).pack(
            padx=6, pady=(0, 4))

    def _bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self._drag_start)
        widget.bind("<B1-Motion>",     self._drag_move)
        for child in widget.winfo_children():
            self._bind_drag(child)

    def _drag_start(self, e):
        self._drag_x = e.x_root - self._win.winfo_x()
        self._drag_y = e.y_root - self._win.winfo_y()

    def _drag_move(self, e):
        self._win.geometry(
            "+{}+{}".format(e.x_root - self._drag_x,
                            e.y_root - self._drag_y))

    # ------------------------------------------------------------------
    # Lightweight 100ms poll - Windows API only, no network
    # ------------------------------------------------------------------

    @staticmethod
    def _get_cursor_pos():
        pt = ctypes.wintypes.POINT()
        try:
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        except Exception:
            pass
        return pt.x, pt.y

    def _get_window_info(self, x, y):
        title = "-"; cls = "-"; hwnd_hex = "-"
        if self._win32gui:
            try:
                hwnd = self._win32gui.WindowFromPoint((x, y))
                if hwnd:
                    title   = (self._win32gui.GetWindowText(hwnd) or "-")
                    cls     = (self._win32gui.GetClassName(hwnd) or "-")
                    hwnd_hex = "0x{:08X}".format(hwnd)
            except Exception:
                pass
        return title, cls, hwnd_hex

    def _start_poll(self):
        self._poll()

    def _poll(self):
        if not self._win.winfo_exists():
            return
        if not self._pinned:
            x, y = self._get_cursor_pos()
            self._xy_var.set("X: {}    Y: {}".format(x, y))
            title, cls, hwnd = self._get_window_info(x, y)
            self._win_title_var.set("Title: " + title[:36])
            self._win_class_var.set("Class: " + cls[:36])
            self._win_hwnd_var.set("Handle: " + hwnd)
        self._poll_id = self._win.after(100, self._poll)

    # ------------------------------------------------------------------
    # F8 hotkey
    # ------------------------------------------------------------------

    def _start_f8(self):
        def _listen():
            try:
                from pynput import keyboard
                def _on_press(key):
                    if key == keyboard.Key.f8:
                        self._win.after(0, self._capture)
                self._f8_listener = keyboard.Listener(on_press=_on_press)
                self._f8_listener.start()
            except Exception as e:
                self.logger.debug("F8 hotkey unavailable: {}".format(e))
        threading.Thread(target=_listen, daemon=True, name="spy-f8").start()

    # ------------------------------------------------------------------
    # PIN toggle
    # ------------------------------------------------------------------

    def _toggle_pin(self):
        self._pinned = not self._pinned
        if self._pinned:
            self._pin_var.set("UNPIN")
            self._pin_btn.configure(bg=YEL, fg=BG)
            self._status_var.set("Pinned. Click UNPIN to resume tracking.")
        else:
            self._pin_var.set("PIN")
            self._pin_btn.configure(bg=CARD, fg=FG)
            self._status_var.set("Hover cursor anywhere")

    # ------------------------------------------------------------------
    # CAPTURE - only here do we try CDP
    # ------------------------------------------------------------------

    def _capture(self):
        """Called on F8 or CAPTURE button. Try CDP; fall back to X,Y coords."""
        x, y = self._get_cursor_pos()
        self._status_var.set("Capturing at ({}, {})...".format(x, y))

        def _do():
            info = self._tracker.get_element_now()
            if info and info.get("tagName"):
                info["x"] = x
                info["y"] = y
                self._win.after(0, lambda: self._status_var.set(
                    "Captured: <{}>".format(info.get("tagName", ""))))
            else:
                info = {"type": "coords", "x": x, "y": y}
                self._win.after(0, lambda: self._status_var.set(
                    "No CDP - saved position ({}, {})".format(x, y)))

            self._win.after(0, lambda i=info: self._show_element(i))
            if self.on_capture:
                self.on_capture(dict(info))

        threading.Thread(target=_do, daemon=True, name="spy-capture").start()

    def _show_element(self, info):
        if not info:
            return
        if info.get("type") == "coords":
            for k in self._elem_vars:
                self._elem_vars[k].set("-")
            self._elem_vars["value"].set("({}, {})".format(
                info.get("x", "?"), info.get("y", "?")))
        else:
            tag = info.get("tagName", "") or "-"
            self._elem_vars["tagName"].set(tag)
            self._elem_vars["text"].set(
                (info.get("text", "") or "-")[:40])
            self._elem_vars["id"].set(info.get("id", "") or "-")
            css = (info.get("css_selector", info.get("selector", ""))
                   or "-")
            self._elem_vars["css_selector"].set(css[:40])
            self._elem_vars["xpath"].set(
                (info.get("xpath", "") or "-")[:40])
            self._elem_vars["value"].set(info.get("value", "") or "-")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def close(self):
        if self._poll_id:
            try:
                self._win.after_cancel(self._poll_id)
            except Exception:
                pass
        if self._f8_listener:
            try:
                self._f8_listener.stop()
            except Exception:
                pass
        self._tracker.close()
        try:
            self._win.destroy()
        except Exception:
            pass

    @property
    def is_alive(self):
        try:
            return bool(self._win.winfo_exists())
        except Exception:
            return False
