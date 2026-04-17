# -*- coding: utf-8 -*-
"""ui/spy_window.py - AHK-style spy window with coordinate saving."""

import base64
import ctypes
import ctypes.wintypes
import json
import os
import socket
import struct
import threading
import tkinter as tk
from tkinter import messagebox

from core.logger import get_logger

# ── Palette ──────────────────────────────────────────────────────────────────
BG    = "#0A0A0F"
CARD  = "#12121A"
CARD2 = "#1A1A28"
ACC   = "#6C4AFF"
ACC2  = "#4A9EFF"
FG    = "#E0DFFF"
MUT   = "#555575"
GRN   = "#4CAF88"
RED   = "#F06070"
YEL   = "#F0C060"
BORD  = "#2A2A44"

SAVED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "data", "spy_coords.json")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_saved():
    try:
        with open(SAVED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_all(entries):
    os.makedirs(os.path.dirname(SAVED_FILE), exist_ok=True)
    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def _get_cursor_pos():
    pt = ctypes.wintypes.POINT()
    try:
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    except Exception:
        pass
    return pt.x, pt.y


def _get_color_at(x, y):
    """Return hex color of pixel at (x, y) using GDI."""
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        color = ctypes.windll.gdi32.GetPixel(hdc, x, y)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        r = color & 0xFF
        g = (color >> 8) & 0xFF
        b = (color >> 16) & 0xFF
        return "#{:02X}{:02X}{:02X}".format(r, g, b), (r, g, b)
    except Exception:
        return "#??????", (0, 0, 0)


def _get_window_info(x, y):
    title = "-"
    cls   = "-"
    hwnd_hex = "-"
    client_x = "-"
    client_y = "-"
    try:
        import win32gui
        hwnd = win32gui.WindowFromPoint((x, y))
        if hwnd:
            title    = win32gui.GetWindowText(hwnd) or "-"
            cls      = win32gui.GetClassName(hwnd) or "-"
            hwnd_hex = "0x{:08X}".format(hwnd)
            # Client-relative coords
            pt = ctypes.wintypes.POINT(x, y)
            ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(pt))
            client_x = str(pt.x)
            client_y = str(pt.y)
    except Exception:
        pass
    return title, cls, hwnd_hex, client_x, client_y


# ── CDP (used only on F8/CAPTURE) ─────────────────────────────────────────────

_JS_INJECT = r"""
(function() {
    function getCSS(el) {
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
                window.__sx_spy = {
                    tagName: el.tagName.toLowerCase(),
                    text: (el.innerText || el.value || el.textContent || '').trim().slice(0, 80),
                    id: el.id || '',
                    className: (typeof el.className === 'string' ? el.className : '') || '',
                    value: el.value || '',
                    href: el.href || '',
                    selector: getCSS(el),
                    css_selector: getCSS(el),
                    xpath: getXPath(el)
                };
            }
        }, true);
    }
    return 'ok';
})();
"""
_JS_READ = "JSON.stringify(window.__sx_spy || {})"


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
        threading.Thread(target=self._reader, daemon=True).start()

    def _do_handshake(self, host, port, path):
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET {} HTTP/1.1\r\nHost: {}:{}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            "Sec-WebSocket-Key: {}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).format(path, host, port, key).encode()
        self._sock.sendall(req)
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("CDP handshake failed")
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
    CDP_PORT = 9222

    def __init__(self):
        self._cdp      = None
        self._lock     = threading.Lock()
        self._injected = False

    def get_element_now(self):
        import urllib.request
        cdp = None
        with self._lock:
            cdp = self._cdp
        if cdp is None or cdp._closed:
            try:
                raw  = urllib.request.urlopen(
                    "http://localhost:{}/json".format(self.CDP_PORT),
                    timeout=2.0).read()
                tabs = json.loads(raw)
                ws_url = next(
                    (t["webSocketDebuggerUrl"] for t in tabs
                     if t.get("type") == "page" and t.get("webSocketDebuggerUrl")),
                    None)
                if not ws_url:
                    return {}
                cdp = _CDP(ws_url, timeout=3.0)
                with self._lock:
                    self._cdp      = cdp
                    self._injected = False
            except Exception:
                return {}
        try:
            if not self._injected:
                r = cdp.evaluate(_JS_INJECT, timeout=3.0)
                self._injected = (r == "ok")
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

    def close(self):
        with self._lock:
            if self._cdp:
                self._cdp.close()
                self._cdp = None


# ── UIA via comtypes (built-in, tidak perlu install package tambahan) ──────────
# Menggunakan Windows UI Automation yang sudah ada di semua Windows 7+
# Bekerja di Chrome, Firefox, Edge tanpa setup apapun.

_UIA_CLSID   = "{ff48dba4-60ef-4201-aa87-54103eef594e}"
_UIA_DLL     = r"C:\Windows\System32\UIAutomationCore.dll"
_uia_obj     = None   # singleton IUIAutomation
_uia_obj_lock = threading.Lock()

# Map ControlType integer → tag HTML
_UIA_TYPE_MAP = {
    50000: "button",    # Button
    50004: "input",     # Edit
    50020: "span",      # Text
    50005: "a",         # Hyperlink
    50006: "img",       # Image
    50002: "input",     # CheckBox  (input[type=checkbox])
    50003: "select",    # ComboBox
    50008: "ul",        # List
    50007: "li",        # ListItem
    50026: "div",       # Group
    50033: "div",       # Pane
    50030: "body",      # Document
    50023: "table",     # Table
    50028: "tr",        # DataItem
    50025: "th",        # Header
    50011: "li",        # MenuItem
    50025: "th",        # HeaderItem
}


def _init_uia():
    """Lazy-init singleton IUIAutomation. Thread-safe."""
    global _uia_obj
    if _uia_obj is not None:
        return _uia_obj
    with _uia_obj_lock:
        if _uia_obj is not None:
            return _uia_obj
        try:
            import comtypes.client, comtypes
            comtypes.client.GetModule(_UIA_DLL)
            from comtypes.gen import UIAutomationClient as _UIA
            _uia_obj = comtypes.client.CreateObject(
                _UIA_CLSID,
                clsctx=comtypes.CLSCTX_INPROC_SERVER,
                interface=_UIA.IUIAutomation,
            )
        except Exception:
            pass
    return _uia_obj


def _get_uia_info(x, y):
    """Ambil info elemen di (x, y) via Windows UI Automation (comtypes).
    Tidak butuh install package — comtypes sudah built-in."""
    try:
        import comtypes
        from comtypes.gen import UIAutomationClient as _UIA
        uia = _init_uia()
        if uia is None:
            return {}
        pt = _UIA.tagPOINT()
        pt.x, pt.y = int(x), int(y)
        el = uia.ElementFromPoint(pt)
        if el is None:
            return {}
        name     = (el.CurrentName or "").strip()
        loc_type = (el.CurrentLocalizedControlType or "").strip()
        ctrl_int = el.CurrentControlType        # integer
        aid      = (el.CurrentAutomationId or "").strip()
        cls      = (el.CurrentClassName or "").strip()
        selector = _build_uia_selector(ctrl_int, loc_type, aid, cls, name)
        return {
            "tagName":      loc_type,
            "text":         name[:80],
            "id":           aid,
            "className":    cls[:80],
            "css_selector": selector,
        }
    except Exception:
        return {}


def _build_uia_selector(ctrl_int, loc_type, aid, cls, name):
    """Bangun CSS selector dari properti UIA."""
    tag = _UIA_TYPE_MAP.get(ctrl_int, "div")
    if aid:
        return "#{}".format(aid)
    if cls:
        parts = cls.strip().split()
        if parts:
            return "{}.{}".format(tag, parts[0])
    if name and ctrl_int in (50000, 50005):   # Button, Hyperlink
        return "{}[aria-label='{}']".format(tag, name[:40])
    return "{} ({})".format(tag, loc_type) if loc_type else tag


# ── FloatingSpyWindow ─────────────────────────────────────────────────────────

class FloatingSpyWindow:
    """AHK-style spy: live coords, window info, color, client coords.
    Press F8 or SAVE to save a named coordinate entry."""

    W = 300
    H = 620

    def __init__(self, parent, browser=None, on_capture=None,
                 on_use_in_macro=None):
        self.on_capture      = on_capture
        self.on_use_in_macro = on_use_in_macro
        self.logger          = get_logger("spy_window")
        self._tracker        = _CDPTracker()

        self._pinned      = False
        self._drag_x      = 0
        self._drag_y      = 0
        self._poll_id     = None
        self._uia_alive   = False
        self._f8_listener = None
        self._saved       = _load_saved()

        self._win = tk.Toplevel(parent)
        self._win.title("Synthex Spy")
        self._win.configure(bg=BG)
        self._win.attributes("-topmost", True)
        self._win.resizable(False, False)
        self._win.overrideredirect(True)

        self._build()

        sw = self._win.winfo_screenwidth()
        self._win.geometry("{}x{}+{}+60".format(self.W, self.H, sw - self.W - 20))
        self._win.update_idletasks()

        self._start_poll()
        self._start_f8()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        win = self._win

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg=ACC, height=30, cursor="fleur")
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  Synthex Spy", bg=ACC, fg="#FFFFFF",
                 font=("Segoe UI", 9, "bold")).pack(side="left", pady=5)
        tk.Button(hdr, text="X", bg=ACC, fg="#FFFFFF",
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=8, cursor="hand2",
                  activebackground=RED, activeforeground="#FFFFFF",
                  command=self.close).pack(side="right", padx=2, pady=3)
        pin_btn = tk.Button(hdr, text="PIN", bg=ACC, fg="#FFFFFF",
                            font=("Segoe UI", 8), relief="flat", bd=0,
                            padx=6, cursor="hand2",
                            command=self._toggle_pin)
        pin_btn.pack(side="right", pady=3)
        self._pin_btn = pin_btn
        self._bind_drag(hdr)

        def _section(label):
            f = tk.Frame(win, bg=CARD, padx=8, pady=5)
            f.pack(fill="x", padx=4, pady=(4, 0))
            tk.Label(f, text=label, bg=CARD, fg=ACC2,
                     font=("Segoe UI", 7, "bold")).pack(anchor="w")
            tk.Frame(f, bg=BORD, height=1).pack(fill="x", pady=(2, 4))
            return f

        def _row(parent, label, var, fg=FG):
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", pady=1)
            tk.Label(row, text="{:<9}".format(label), bg=CARD, fg=MUT,
                     font=("Consolas", 8), width=10, anchor="w").pack(side="left")
            tk.Label(row, textvariable=var, bg=CARD, fg=fg,
                     font=("Consolas", 9), anchor="w",
                     wraplength=190).pack(side="left", fill="x", expand=True)
            return row

        # ── Mouse / Screen ────────────────────────────────────────────────────
        ms = _section("Mouse / Screen")
        self._v_screen  = tk.StringVar(value="0, 0")
        self._v_client  = tk.StringVar(value="-, -")
        self._v_color   = tk.StringVar(value="#??????")
        _row(ms, "Screen", self._v_screen, YEL)
        _row(ms, "Client", self._v_client)
        # Color row with swatch
        crow = tk.Frame(ms, bg=CARD)
        crow.pack(fill="x", pady=1)
        tk.Label(crow, text="{:<9}".format("Color"), bg=CARD, fg=MUT,
                 font=("Consolas", 8), width=10, anchor="w").pack(side="left")
        tk.Label(crow, textvariable=self._v_color, bg=CARD, fg=FG,
                 font=("Consolas", 9), anchor="w").pack(side="left")
        self._color_swatch = tk.Label(crow, text="   ", bg="#000000",
                                      relief="flat", width=3)
        self._color_swatch.pack(side="left", padx=(6, 0))

        # ── Window ────────────────────────────────────────────────────────────
        wf = _section("Window")
        self._v_wtitle = tk.StringVar(value="-")
        self._v_wclass = tk.StringVar(value="-")
        self._v_hwnd   = tk.StringVar(value="-")
        _row(wf, "Title", self._v_wtitle)
        _row(wf, "Class", self._v_wclass)
        _row(wf, "Handle", self._v_hwnd, MUT)

        # ── Element (live UIA hover) ──────────────────────────────────────────
        ef = _section("Element  [live hover • Ctrl+Q simpan]")
        self._v_etag   = tk.StringVar(value="-")
        self._v_etext  = tk.StringVar(value="-")
        self._v_eid    = tk.StringVar(value="-")
        self._v_eclass = tk.StringVar(value="-")
        self._v_ecss   = tk.StringVar(value="-")
        self._v_expath = tk.StringVar(value="-")
        _row(ef, "Tag",   self._v_etag,   GRN)
        _row(ef, "Text",  self._v_etext)
        _row(ef, "ID",    self._v_eid)
        _row(ef, "Class", self._v_eclass, MUT)
        _row(ef, "CSS",   self._v_ecss,   ACC2)
        _row(ef, "XPath", self._v_expath)

        # Tombol copy cepat untuk elemen
        eq = tk.Frame(ef, bg=CARD)
        eq.pack(fill="x", pady=(4, 0))
        tk.Button(eq, text="COPY CSS", bg=CARD2, fg=ACC2,
                  font=("Segoe UI", 7, "bold"), relief="flat", bd=0,
                  padx=6, pady=3, cursor="hand2",
                  command=self._copy_css).pack(side="left", padx=(0, 4))
        tk.Button(eq, text="COPY TEXT", bg=CARD2, fg=FG,
                  font=("Segoe UI", 7, "bold"), relief="flat", bd=0,
                  padx=6, pady=3, cursor="hand2",
                  command=self._copy_text).pack(side="left", padx=(0, 4))
        tk.Button(eq, text="BUAT STEP", bg=ACC, fg="#FFFFFF",
                  font=("Segoe UI", 7, "bold"), relief="flat", bd=0,
                  padx=6, pady=3, cursor="hand2",
                  command=self._copy_as_step).pack(side="left")

        # ── Save coords ───────────────────────────────────────────────────────
        sf = tk.Frame(win, bg=CARD2, padx=8, pady=6)
        sf.pack(fill="x", padx=4, pady=(6, 0))
        tk.Label(sf, text="Save Coordinate", bg=CARD2, fg=ACC2,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w")
        tk.Frame(sf, bg=BORD, height=1).pack(fill="x", pady=(2, 4))

        name_row = tk.Frame(sf, bg=CARD2)
        name_row.pack(fill="x")
        tk.Label(name_row, text="Name:", bg=CARD2, fg=MUT,
                 font=("Consolas", 8)).pack(side="left")
        self._name_var = tk.StringVar()
        name_entry = tk.Entry(name_row, textvariable=self._name_var,
                              bg=CARD, fg=FG, insertbackground=ACC,
                              font=("Consolas", 9), relief="flat",
                              bd=4, highlightthickness=1,
                              highlightbackground=BORD,
                              highlightcolor=ACC)
        name_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        name_entry.bind("<Return>", lambda e: self._save_coord())

        btn_row = tk.Frame(sf, bg=CARD2)
        btn_row.pack(fill="x", pady=(5, 0))
        tk.Button(btn_row, text="SAVE  Ctrl+Q", bg=ACC, fg="#FFFFFF",
                  font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                  padx=8, pady=4, cursor="hand2",
                  activebackground="#8870FF", activeforeground="#FFFFFF",
                  command=self._save_coord).pack(side="left", fill="x",
                                                  expand=True, padx=(0, 3))
        tk.Button(btn_row, text="COPY XY", bg=CARD, fg=FG,
                  font=("Segoe UI", 8), relief="flat", bd=0,
                  padx=8, pady=4, cursor="hand2",
                  command=self._copy_xy).pack(side="left", padx=(0, 3))
        tk.Button(btn_row, text="CLEAR", bg=CARD, fg=RED,
                  font=("Segoe UI", 8), relief="flat", bd=0,
                  padx=8, pady=4, cursor="hand2",
                  command=self._clear_element).pack(side="left")

        # ── Saved list ────────────────────────────────────────────────────────
        lf = tk.Frame(win, bg=CARD, padx=6, pady=5)
        lf.pack(fill="both", expand=True, padx=4, pady=(4, 4))

        list_hdr = tk.Frame(lf, bg=CARD)
        list_hdr.pack(fill="x")
        tk.Label(list_hdr, text="Saved Coordinates", bg=CARD, fg=ACC2,
                 font=("Segoe UI", 7, "bold")).pack(side="left")
        tk.Button(list_hdr, text="DELETE ALL", bg=CARD, fg=RED,
                  font=("Segoe UI", 7), relief="flat", bd=0,
                  cursor="hand2", command=self._delete_all).pack(side="right")
        tk.Frame(lf, bg=BORD, height=1).pack(fill="x", pady=(2, 3))

        # Scrollable list
        list_frame = tk.Frame(lf, bg=CARD)
        list_frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(list_frame, orient="vertical", width=8,
                          bg=CARD, troughcolor=BG, relief="flat")
        sb.pack(side="right", fill="y")

        self._listbox = tk.Listbox(
            list_frame,
            bg=CARD, fg=FG, selectbackground=ACC, selectforeground="#FFFFFF",
            font=("Consolas", 8), relief="flat", bd=0,
            highlightthickness=0, activestyle="none",
            yscrollcommand=sb.set)
        self._listbox.pack(side="left", fill="both", expand=True)
        sb.config(command=self._listbox.yview)
        self._listbox.bind("<Double-Button-1>", self._on_list_dbl)
        self._listbox.bind("<Button-3>",        self._on_list_right)
        self._listbox.bind("<<ListboxSelect>>", self._on_list_sel)

        tk.Label(lf, text="Klik: detail  |  Double: copy CSS/XY  |  Kanan: menu",
                 bg=CARD, fg=MUT, font=("Segoe UI", 7)).pack(pady=(3, 0))

        # ── Detail panel ────────────────────────────────────────────────
        self._detail_frame = tk.Frame(win, bg=CARD2, padx=6, pady=4,
                                      height=82)
        self._detail_frame.pack(fill="x", padx=4, pady=(0, 2))
        self._detail_frame.pack_propagate(False)
        tk.Label(self._detail_frame, text="Klik item untuk lihat detail",
                 bg=CARD2, fg=MUT, font=("Segoe UI", 7)).pack(anchor="w")

        # ── Status ────────────────────────────────────────────────────────────
        self._v_status = tk.StringVar(value="Hover to inspect")
        tk.Label(win, textvariable=self._v_status,
                 bg=BG, fg=MUT, font=("Segoe UI", 7),
                 wraplength=self.W - 10).pack(pady=(2, 4))

        self._refresh_list()

    # ── Drag ─────────────────────────────────────────────────────────────────

    def _bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self._drag_start)
        widget.bind("<B1-Motion>",     self._drag_move)
        for child in widget.winfo_children():
            self._bind_drag(child)

    def _drag_start(self, e):
        self._drag_x = e.x_root - self._win.winfo_x()
        self._drag_y = e.y_root - self._win.winfo_y()

    def _drag_move(self, e):
        self._win.geometry("+{}+{}".format(
            e.x_root - self._drag_x, e.y_root - self._drag_y))

    # ── Poll (100ms) ─────────────────────────────────────────────────────────

    def _poll(self):
        if not self._win.winfo_exists():
            return
        if not self._pinned:
            x, y = _get_cursor_pos()
            self._v_screen.set("{}, {}".format(x, y))

            hex_col, rgb = _get_color_at(x, y)
            self._v_color.set("{} rgb({},{},{})".format(hex_col, *rgb))
            try:
                self._color_swatch.configure(bg=hex_col)
            except Exception:
                pass

            title, cls, hwnd, cx, cy = _get_window_info(x, y)
            self._v_client.set("{}, {}".format(cx, cy))
            self._v_wtitle.set(title[:38])
            self._v_wclass.set(cls[:38])
            self._v_hwnd.set(hwnd)

        self._poll_id = self._win.after(100, self._poll)

    def _start_poll(self):
        self._poll()
        self._start_uia_poll()

    # ── UIA live hover ────────────────────────────────────────────────────────

    def _start_uia_poll(self):
        """Jalankan background thread yang membaca elemen di bawah kursor via UIA."""
        self._uia_alive = True
        t = threading.Thread(target=self._uia_loop, daemon=True)
        t.start()

    def _uia_loop(self):
        import time as _t
        import comtypes
        # COM harus di-init di setiap thread yang menggunakannya
        try:
            comtypes.CoInitialize()
        except Exception:
            pass
        # Pastikan UIA singleton sudah siap sebelum loop mulai
        _init_uia()
        while self._uia_alive:
            try:
                if not self._pinned:
                    try:
                        alive = self._win.winfo_exists()
                    except Exception:
                        break
                    if not alive:
                        break
                    x, y = _get_cursor_pos()
                    info = _get_uia_info(x, y)
                    if info:
                        self._win.after(0, lambda i=info: self._update_element_ui(i))
            except Exception:
                pass
            _t.sleep(0.35)
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass

    def _update_element_ui(self, info):
        """Update baris Element dari hasil UIA (dipanggil di main thread)."""
        try:
            self._v_etag.set(info.get("tagName", "-") or "-")
            text = (info.get("text", "") or "").strip()
            self._v_etext.set(text[:60] if text else "-")
            self._v_eid.set(info.get("id", "-") or "-")
            self._v_eclass.set(info.get("className", "-") or "-")
            self._v_ecss.set(info.get("css_selector", "-") or "-")
        except Exception:
            pass

    # ── Ctrl+Q hotkey ────────────────────────────────────────────────────────

    def _start_f8(self):
        try:
            from pynput import keyboard

            def _on_activate():
                if self._win.winfo_exists():
                    self._win.after(0, self._save_coord)

            self._f8_listener = keyboard.GlobalHotKeys({"<ctrl>+q": _on_activate})
            self._f8_listener.start()
        except Exception as e:
            self.logger.debug("Ctrl+Q hotkey unavailable: {}".format(e))

    # ── PIN ──────────────────────────────────────────────────────────────────

    def _toggle_pin(self):
        self._pinned = not self._pinned
        if self._pinned:
            self._pin_btn.configure(text="UNPIN", bg=YEL, fg=BG)
            self._v_status.set("Pinned - koordinat dibekukan")
        else:
            self._pin_btn.configure(text="PIN", bg=ACC, fg="#FFFFFF")
            self._v_status.set("Hover to inspect")

    # ── SAVE coord ───────────────────────────────────────────────────────────

    def _save_coord(self):
        x, y = _get_cursor_pos()
        title, win_cls, hwnd, cx, cy = _get_window_info(x, y)
        hex_col, rgb = _get_color_at(x, y)

        name = self._name_var.get().strip()
        if not name:
            name = "coord_{}".format(len(self._saved) + 1)

        # Baca data UIA yang sudah live di label (tidak perlu request ulang)
        cur_tag  = self._v_etag.get()
        cur_text = self._v_etext.get()
        cur_id   = self._v_eid.get()
        cur_cls  = self._v_eclass.get()
        cur_css  = self._v_ecss.get()

        def _clean(v):
            return "" if v in ("-", "", None) else v

        entry = {
            "name":     name,
            "x":        x,
            "y":        y,
            "client_x": cx,
            "client_y": cy,
            "color":    hex_col,
            "window":   title[:60],
            "class":    win_cls[:60],
            "hwnd":     hwnd,
            # Data elemen dari UIA live
            "tag":      _clean(cur_tag),
            "text":     _clean(cur_text),
            "id":       _clean(cur_id),
            "css_class":_clean(cur_cls),
            "css":      _clean(cur_css),
        }

        if self.on_capture:
            self.on_capture({
                "name":         name,
                "x":            x,
                "y":            y,
                "tagName":      entry["tag"],
                "css_selector": entry["css"],
                "text":         entry["text"],
                "id":           entry["id"],
            })

        self._saved.append(entry)
        _save_all(self._saved)
        self._refresh_list()
        self._name_var.set("")
        self._v_status.set("Saved: \"{}\" ({}, {})  CSS: {}".format(
            name, x, y, entry["css"] or "-"))

    # ── Copy XY ──────────────────────────────────────────────────────────────

    def _copy_xy(self):
        x, y = _get_cursor_pos()
        text = "{}, {}".format(x, y)
        self._win.clipboard_clear()
        self._win.clipboard_append(text)
        self._v_status.set("Copied: {}".format(text))

    def _copy_as_step(self):
        """Buat step macro dari elemen yang sedang di-hover dan copy ke clipboard."""
        x, y = _get_cursor_pos()
        css  = self._v_ecss.get()
        text = self._v_etext.get()
        tag  = self._v_etag.get()

        # Pilih format step terbaik
        if css and css not in ("-", "div", "body"):
            step = {"type": "click", "selector": css,
                    "hint": text[:40] if text and text != "-" else ""}
        else:
            step = {"type": "click", "x": x, "y": y,
                    "hint": text[:40] if text and text != "-" else ""}

        step_json = json.dumps(step, ensure_ascii=False)
        self._win.clipboard_clear()
        self._win.clipboard_append(step_json)
        self._v_status.set("Step disalin: {}".format(step_json[:55]))

    def _copy_css(self):
        css = self._v_ecss.get()
        if css and css != "-":
            self._win.clipboard_clear()
            self._win.clipboard_append(css)
            self._v_status.set("Copied CSS: {}".format(css[:40]))
        else:
            self._v_status.set("Belum ada CSS selector — arahkan ke elemen browser")

    def _copy_text(self):
        text = self._v_etext.get()
        if text and text != "-":
            self._win.clipboard_clear()
            self._win.clipboard_append(text)
            self._v_status.set("Copied text: {}".format(text[:40]))
        else:
            self._v_status.set("Belum ada teks elemen — arahkan ke elemen browser")

    # ── Clear element fields ─────────────────────────────────────────────────

    def _clear_element(self):
        for v in (self._v_etag, self._v_etext, self._v_eid,
                  self._v_eclass, self._v_ecss, self._v_expath):
            v.set("-")
        self._v_status.set("Element info cleared")

    # ── Saved list ───────────────────────────────────────────────────────────

    def _refresh_list(self):
        self._listbox.delete(0, tk.END)
        for i, e in enumerate(self._saved):
            css  = e.get("css", "") or ""
            hint = " [{}]".format(css[:20]) if css else ""
            line = "{:>2}. {:<16}{}  ({},{})".format(
                i + 1, e.get("name", "")[:16], hint,
                e.get("x", "?"), e.get("y", "?"))
            self._listbox.insert(tk.END, line)

    def _show_entry_detail(self, idx):
        """Tampilkan detail lengkap koordinat tersimpan di panel detail."""
        if idx < 0 or idx >= len(self._saved):
            return
        e = self._saved[idx]
        lines = [
            ("Name",    e.get("name", "-")),
            ("XY",      "{}, {}".format(e.get("x","?"), e.get("y","?"))),
            ("Tag",     e.get("tag", "-") or "-"),
            ("Text",    e.get("text", "-") or "-"),
            ("ID",      e.get("id", "-") or "-"),
            ("Class",   e.get("css_class", "-") or "-"),
            ("CSS",     e.get("css", "-") or "-"),
            ("Window",  e.get("window", "-") or "-"),
        ]
        # Tampilkan di panel detail
        for widget in self._detail_frame.winfo_children():
            widget.destroy()
        for label, val in lines:
            row = tk.Frame(self._detail_frame, bg=CARD2)
            row.pack(fill="x", pady=1)
            tk.Label(row, text="{:<7}".format(label), bg=CARD2, fg=MUT,
                     font=("Consolas", 7), width=8, anchor="w").pack(side="left")
            tk.Label(row, text=str(val)[:36], bg=CARD2, fg=FG,
                     font=("Consolas", 7), anchor="w").pack(side="left", fill="x", expand=True)

    def _on_list_sel(self, event):
        sel = self._listbox.curselection()
        if sel and sel[0] < len(self._saved):
            self._show_entry_detail(sel[0])

    def _on_list_dbl(self, event):
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._saved):
            return
        e = self._saved[idx]
        # Double-click: copy CSS kalau ada, kalau tidak copy XY
        css = e.get("css", "")
        if css:
            self._win.clipboard_clear()
            self._win.clipboard_append(css)
            self._v_status.set("Copied CSS: {}".format(css[:40]))
        else:
            xy = "{}, {}".format(e.get("x"), e.get("y"))
            self._win.clipboard_clear()
            self._win.clipboard_append(xy)
            self._v_status.set("Copied XY: {}".format(xy))

    def _on_list_right(self, event):
        idx = self._listbox.nearest(event.y)
        if idx < 0 or idx >= len(self._saved):
            return
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(idx)
        self._show_entry_detail(idx)
        e    = self._saved[idx]
        name = e.get("name", str(idx))
        css  = e.get("css", "")
        text = e.get("text", "")
        menu = tk.Menu(self._win, tearoff=0, bg=CARD, fg=FG,
                       activebackground=ACC, activeforeground="#FFFFFF",
                       font=("Segoe UI", 9))
        menu.add_command(label="Copy CSS Selector",
                         command=lambda i=idx: self._copy_entry_css(i))
        menu.add_command(label="Copy Text / Nilai",
                         command=lambda i=idx: self._copy_entry_text(i))
        menu.add_command(label="Copy X, Y",
                         command=lambda i=idx: self._copy_entry(i))
        menu.add_command(label="Copy JSON Lengkap",
                         command=lambda i=idx: self._copy_entry_json(i))
        menu.add_separator()
        menu.add_command(label="Delete \"{}\"".format(name),
                         command=lambda i=idx: self._delete_entry(i))
        menu.tk_popup(event.x_root, event.y_root)

    def _copy_entry(self, idx):
        e = self._saved[idx]
        text = "{}, {}".format(e.get("x"), e.get("y"))
        self._win.clipboard_clear()
        self._win.clipboard_append(text)
        self._v_status.set("Copied XY: {}".format(text))

    def _copy_entry_css(self, idx):
        e   = self._saved[idx]
        css = e.get("css", "")
        if css:
            self._win.clipboard_clear()
            self._win.clipboard_append(css)
            self._v_status.set("Copied CSS: {}".format(css[:50]))
        else:
            self._v_status.set("CSS tidak ada untuk \"{}\"".format(e.get("name","")))

    def _copy_entry_text(self, idx):
        e    = self._saved[idx]
        text = e.get("text", "")
        if text:
            self._win.clipboard_clear()
            self._win.clipboard_append(text)
            self._v_status.set("Copied text: {}".format(text[:50]))
        else:
            self._v_status.set("Text tidak ada untuk \"{}\"".format(e.get("name","")))

    def _copy_entry_json(self, idx):
        text = json.dumps(self._saved[idx], ensure_ascii=False, indent=2)
        self._win.clipboard_clear()
        self._win.clipboard_append(text)
        self._v_status.set("Copied JSON: {}".format(self._saved[idx].get("name")))

    def _delete_entry(self, idx):
        name = self._saved[idx].get("name", "")
        del self._saved[idx]
        _save_all(self._saved)
        self._refresh_list()
        self._v_status.set("Deleted: \"{}\"".format(name))

    def _delete_all(self):
        if not self._saved:
            return
        if messagebox.askyesno("Hapus Semua",
                               "Hapus semua {} koordinat tersimpan?".format(len(self._saved)),
                               parent=self._win):
            self._saved.clear()
            _save_all(self._saved)
            self._refresh_list()
            self._v_status.set("Semua koordinat dihapus")

    # ── Public ───────────────────────────────────────────────────────────────

    def close(self):
        self._uia_alive = False
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
