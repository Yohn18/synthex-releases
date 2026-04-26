# -*- coding: utf-8 -*-
"""
Synthex Android Companion App
Connects to Synthex PC via WebSocket, controls HP from UI.
"""

import json
import threading
import time
import urllib.request
import urllib.error
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = get_color_from_hex("#0a0a0f")
CARD    = get_color_from_hex("#111118")
CARD2   = get_color_from_hex("#16162a")
ACC     = get_color_from_hex("#6c4aff")
ACC2    = get_color_from_hex("#9d5cf6")
FG      = get_color_from_hex("#e2e8f0")
MUT     = get_color_from_hex("#64748b")
GRN     = get_color_from_hex("#10b981")
RED     = get_color_from_hex("#f87171")
YEL     = get_color_from_hex("#f59e0b")

Window.clearcolor = BG

_DEFAULT_PORT = 8765


# ── HTTP helpers (no external deps) ──────────────────────────────────────────

def _get(base_url: str, path: str, timeout: int = 5):
    try:
        url = base_url.rstrip("/") + path
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_error": str(e)}


def _post(base_url: str, path: str, data: dict, timeout: int = 8):
    try:
        url   = base_url.rstrip("/") + path
        body  = json.dumps(data).encode()
        req   = urllib.request.Request(url, data=body,
                                       headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "_error": str(e)}


# ── Reusable styled widgets ───────────────────────────────────────────────────

def _btn(text, bg=CARD2, fg=FG, bold=False, **kw):
    b = Button(
        text=text,
        background_color=bg,
        color=fg,
        background_normal="",
        bold=bold,
        font_size="14sp",
        **kw
    )
    return b


def _lbl(text, size="13sp", color=FG, bold=False, halign="left", **kw):
    l = Label(
        text=text, color=color, bold=bold,
        font_size=size, halign=halign,
        text_size=(None, None),
        **kw
    )
    l.bind(size=lambda inst, v: setattr(inst, "text_size", (v[0], None)))
    return l


def _spacer(h=8):
    w = Widget(size_hint_y=None, height=h)
    return w


# ── Main App ──────────────────────────────────────────────────────────────────

class SynthexApp(App):

    def build(self):
        self.title = "Synthex"
        self._base_url  = ""
        self._serial    = ""
        self._connected = False
        self._macros    = []
        self._devices   = []
        self._poll_event = None

        root = BoxLayout(orientation="vertical", spacing=0, padding=0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = BoxLayout(
            orientation="horizontal",
            size_hint_y=None, height="56dp",
            padding=[16, 0, 16, 0], spacing=10)
        hdr.canvas.before.add(
            __import__("kivy.graphics", fromlist=["Color"]).Color(*get_color_from_hex("#111118")))
        from kivy.graphics import Rectangle
        with hdr.canvas.before:
            from kivy.graphics import Color as _C, Rectangle as _R
            _C(*get_color_from_hex("#111118"))
            self._hdr_rect = _R(pos=hdr.pos, size=hdr.size)
        hdr.bind(pos=lambda *a: setattr(self._hdr_rect, "pos",  hdr.pos))
        hdr.bind(size=lambda *a: setattr(self._hdr_rect, "size", hdr.size))

        logo = Label(text="[b]SX[/b]", markup=True,
                     color=FG, font_size="18sp",
                     size_hint=(None, None), size=("40dp", "40dp"))
        hdr.add_widget(logo)
        hdr.add_widget(_lbl("[b]Synthex[/b]", markup=True,
                            size="16sp", color=FG, bold=True))

        self._conn_lbl = _lbl("Belum terhubung", size="11sp", color=MUT,
                              halign="right")
        hdr.add_widget(self._conn_lbl)
        root.add_widget(hdr)

        # Accent line
        acc_line = Widget(size_hint_y=None, height="3dp")
        with acc_line.canvas:
            from kivy.graphics import Color as _C2, Rectangle as _R2
            _C2(*ACC)
            self._acc_rect = _R2(pos=acc_line.pos, size=acc_line.size)
        acc_line.bind(pos=lambda *a: setattr(self._acc_rect, "pos",  acc_line.pos))
        acc_line.bind(size=lambda *a: setattr(self._acc_rect, "size", acc_line.size))
        root.add_widget(acc_line)

        # ── Body (scrollable) ─────────────────────────────────────────────────
        sv = ScrollView(do_scroll_x=False)
        self._body = BoxLayout(
            orientation="vertical",
            size_hint_y=None, spacing=10,
            padding=[14, 10, 14, 20])
        self._body.bind(minimum_height=self._body.setter("height"))
        sv.add_widget(self._body)
        root.add_widget(sv)

        self._build_connect_card()
        return root

    # ── Cards ─────────────────────────────────────────────────────────────────

    def _card(self, title, accent=None):
        wrapper = BoxLayout(
            orientation="vertical",
            size_hint_y=None, spacing=0)
        wrapper.bind(minimum_height=wrapper.setter("height"))
        with wrapper.canvas.before:
            from kivy.graphics import Color as _C, RoundedRectangle as _RR
            _C(*CARD)
            rr = _RR(pos=wrapper.pos, size=wrapper.size, radius=[10])
        wrapper.bind(pos=lambda *a: setattr(rr, "pos",  wrapper.pos))
        wrapper.bind(size=lambda *a: setattr(rr, "size", wrapper.size))

        hdr_col = accent or ACC
        hdr = BoxLayout(size_hint_y=None, height="34dp", padding=[14, 0, 14, 0])
        with hdr.canvas.before:
            from kivy.graphics import Color as _C2, RoundedRectangle as _RR2
            _C2(*hdr_col)
            rr2 = _RR2(pos=hdr.pos, size=hdr.size, radius=[10, 10, 0, 0])
        hdr.bind(pos=lambda *a: setattr(rr2, "pos",  hdr.pos))
        hdr.bind(size=lambda *a: setattr(rr2, "size", hdr.size))
        hdr.add_widget(_lbl(title.upper(), size="11sp", color=FG, bold=True))
        wrapper.add_widget(hdr)

        body = BoxLayout(
            orientation="vertical",
            size_hint_y=None, padding=[14, 10, 14, 14], spacing=8)
        body.bind(minimum_height=body.setter("height"))
        wrapper.add_widget(body)
        return wrapper, body

    def _build_connect_card(self):
        card, body = self._card("Sambungkan ke PC Synthex",
                                get_color_from_hex("#0D2240"))

        body.add_widget(_lbl("Masukkan IP PC kamu:", color=MUT, size="12sp"))

        row = BoxLayout(size_hint_y=None, height="44dp", spacing=8)
        self._ip_input = TextInput(
            hint_text="192.168.1.x",
            multiline=False,
            size_hint_x=0.6,
            background_color=CARD2,
            foreground_color=FG,
            cursor_color=FG,
            font_size="14sp",
            padding=[10, 10, 10, 10])
        port_input = TextInput(
            text=str(_DEFAULT_PORT),
            multiline=False,
            size_hint_x=0.2,
            input_filter="int",
            background_color=CARD2,
            foreground_color=FG,
            cursor_color=FG,
            font_size="14sp",
            padding=[10, 10, 10, 10])
        self._port_input = port_input

        conn_btn = _btn("Hubungkan", bg=ACC, fg=FG, bold=True,
                        size_hint_x=0.2)
        conn_btn.bind(on_release=self._do_connect)
        row.add_widget(self._ip_input)
        row.add_widget(self._port_input)
        row.add_widget(conn_btn)
        body.add_widget(row)

        self._conn_status = _lbl("", size="11sp", color=MUT)
        body.add_widget(self._conn_status)
        self._body.add_widget(card)

    def _build_main_cards(self):
        self._body.clear_widgets()
        self._build_connect_card()
        self._build_control_card()
        self._build_tap_card()
        self._build_text_card()
        self._build_macro_card()
        self._build_device_card()

    def _build_control_card(self):
        card, body = self._card("Kontrol HP")

        # Nav row
        nav = GridLayout(cols=3, size_hint_y=None, height="54dp", spacing=6)
        for txt, fn in [
            ("Back", lambda *_: self._key(4)),
            ("Home", lambda *_: self._key(3)),
            ("Recent", lambda *_: self._key(187)),
        ]:
            b = _btn(txt, bold=True)
            b.bind(on_release=fn)
            nav.add_widget(b)
        body.add_widget(nav)

        # Swipe row
        sw = GridLayout(cols=4, size_hint_y=None, height="54dp", spacing=6)
        for emoji, direction in [("↑ Atas", "up"), ("↓ Bawah", "down"),
                                  ("← Kiri", "left"), ("→ Kanan", "right")]:
            b = _btn(emoji)
            b.bind(on_release=lambda *_, d=direction: self._swipe(d))
            sw.add_widget(b)
        body.add_widget(sw)

        # Power row
        pw = GridLayout(cols=2, size_hint_y=None, height="44dp", spacing=6)
        wake_b = _btn("Wake Up", bg=get_color_from_hex("#1A2040"), fg=YEL, bold=True)
        wake_b.bind(on_release=lambda *_: self._key(224))
        power_b = _btn("Power", bg=get_color_from_hex("#2A1010"), fg=RED)
        power_b.bind(on_release=lambda *_: self._key(26))
        pw.add_widget(wake_b)
        pw.add_widget(power_b)
        body.add_widget(pw)

        self._body.add_widget(card)

    def _build_tap_card(self):
        card, body = self._card("Tap Koordinat",
                                get_color_from_hex("#0D2A1A"))
        row = BoxLayout(size_hint_y=None, height="44dp", spacing=8)
        self._tap_x = TextInput(hint_text="X (540)", multiline=False,
                                input_filter="int",
                                background_color=CARD2, foreground_color=FG,
                                cursor_color=FG, font_size="14sp",
                                padding=[10, 10, 10, 10])
        self._tap_y = TextInput(hint_text="Y (960)", multiline=False,
                                input_filter="int",
                                background_color=CARD2, foreground_color=FG,
                                cursor_color=FG, font_size="14sp",
                                padding=[10, 10, 10, 10])
        tap_b = _btn("Tap", bg=get_color_from_hex("#0EA5E9"), fg=FG, bold=True,
                     size_hint_x=0.3)
        tap_b.bind(on_release=self._do_tap)
        row.add_widget(self._tap_x)
        row.add_widget(self._tap_y)
        row.add_widget(tap_b)
        body.add_widget(row)
        self._tap_status = _lbl("", size="11sp", color=GRN)
        body.add_widget(self._tap_status)
        self._body.add_widget(card)

    def _build_text_card(self):
        card, body = self._card("Kirim Teks",
                                get_color_from_hex("#1A1A0A"))
        row = BoxLayout(size_hint_y=None, height="44dp", spacing=8)
        self._text_input = TextInput(
            hint_text="Ketik teks...", multiline=False,
            background_color=CARD2, foreground_color=FG,
            cursor_color=FG, font_size="14sp",
            padding=[10, 10, 10, 10])
        send_b = _btn("Kirim", bg=ACC, fg=FG, bold=True, size_hint_x=0.3)
        send_b.bind(on_release=self._do_send_text)
        row.add_widget(self._text_input)
        row.add_widget(send_b)
        body.add_widget(row)
        self._body.add_widget(card)

    def _build_macro_card(self):
        card, body = self._card("Macro Aktif",
                                get_color_from_hex("#1A0A30"))
        self._macro_body = body
        self._refresh_macro_ui()
        self._body.add_widget(card)

    def _refresh_macro_ui(self):
        self._macro_body.clear_widgets()
        if not self._macros:
            self._macro_body.add_widget(
                _lbl("Belum ada macro aktif", color=MUT, size="12sp"))
            return
        for i, m in enumerate(self._macros):
            if not m.get("enabled", True):
                continue
            row = BoxLayout(size_hint_y=None, height="42dp", spacing=8)
            delay = m.get("delay_sec", 180)
            label = m.get("label") or m.get("action", "macro")
            mins  = delay // 60
            secs  = delay % 60
            delay_txt = "{}m{}s".format(mins, secs) if mins else "{}d".format(secs)
            row.add_widget(_lbl("[{}]  {}".format(delay_txt, label),
                                color=FG, size="13sp"))
            fire_b = _btn("▶", bg=get_color_from_hex("#1A0840"),
                          fg=ACC, bold=True,
                          size_hint_x=None, width="40dp")
            fire_b.bind(on_release=lambda *_, idx=i: self._fire_macro(idx))
            row.add_widget(fire_b)
            self._macro_body.add_widget(row)

    def _build_device_card(self):
        card, body = self._card("Perangkat", get_color_from_hex("#0A200A"))
        self._device_body = body
        self._refresh_device_ui()
        self._body.add_widget(card)

    def _refresh_device_ui(self):
        self._device_body.clear_widgets()
        if not self._devices:
            self._device_body.add_widget(
                _lbl("Tidak ada perangkat", color=MUT, size="12sp"))
            return
        for d in self._devices:
            icon = "📶" if ":" in d.get("serial", "") else "🔌"
            self._device_body.add_widget(
                _lbl("{} {}  {}".format(
                    icon, d.get("serial", "?"), d.get("state", "")),
                    color=FG, size="12sp"))

    # ── Connection ────────────────────────────────────────────────────────────

    def _do_connect(self, *_):
        ip   = self._ip_input.text.strip()
        port = self._port_input.text.strip() or str(_DEFAULT_PORT)
        if not ip:
            self._conn_status.text = "Masukkan IP PC dulu"
            self._conn_status.color = RED
            return
        self._base_url = "http://{}:{}".format(ip, port)
        self._conn_status.text = "Menghubungkan..."
        self._conn_status.color = YEL

        def _bg():
            resp = _get(self._base_url, "/api/status", timeout=5)
            Clock.schedule_once(lambda dt: self._on_connect_result(resp))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_connect_result(self, resp):
        if "_error" in resp:
            self._conn_status.text = "Gagal: " + resp["_error"]
            self._conn_status.color = RED
            self._conn_lbl.text = "Terputus"
            self._conn_lbl.color = RED
            return

        self._connected = True
        self._conn_status.text = "Terhubung!"
        self._conn_status.color = GRN
        self._conn_lbl.text = "Terhubung"
        self._conn_lbl.color = GRN
        self._process_status(resp)
        self._build_main_cards()

        if self._poll_event:
            self._poll_event.cancel()
        self._poll_event = Clock.schedule_interval(self._poll, 3)

    def _poll(self, dt):
        if not self._base_url:
            return

        def _bg():
            resp = _get(self._base_url, "/api/status", timeout=5)
            Clock.schedule_once(lambda dt: self._on_poll(resp))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_poll(self, resp):
        if "_error" in resp:
            self._conn_lbl.text = "Terputus"
            self._conn_lbl.color = RED
            return
        self._conn_lbl.text = "Terhubung"
        self._conn_lbl.color = GRN
        self._process_status(resp)

    def _process_status(self, resp):
        new_macros  = resp.get("macros", [])
        new_devices = resp.get("devices", [])
        self._serial = resp.get("mirror_serial", "") or (
            new_devices[0]["serial"] if new_devices else "")

        changed_m = new_macros  != self._macros
        changed_d = new_devices != self._devices
        self._macros  = new_macros
        self._devices = new_devices

        if changed_m and hasattr(self, "_macro_body"):
            self._refresh_macro_ui()
        if changed_d and hasattr(self, "_device_body"):
            self._refresh_device_ui()

    # ── ADB Actions ───────────────────────────────────────────────────────────

    def _adb(self, payload: dict, cb=None):
        payload["serial"] = self._serial

        def _bg():
            resp = _post(self._base_url, "/api/adb", payload)
            if cb:
                Clock.schedule_once(lambda dt: cb(resp))

        threading.Thread(target=_bg, daemon=True).start()

    def _key(self, code: int):
        self._adb({"action": "key", "keycode": code})

    def _swipe(self, direction: str):
        presets = {
            "up":    {"x1": 540, "y1": 1200, "x2": 540, "y2": 300,  "ms": 350},
            "down":  {"x1": 540, "y1": 300,  "x2": 540, "y2": 1200, "ms": 350},
            "left":  {"x1": 900, "y1": 960,  "x2": 100, "y2": 960,  "ms": 300},
            "right": {"x1": 100, "y1": 960,  "x2": 900, "y2": 960,  "ms": 300},
        }
        p = presets.get(direction, presets["down"])
        self._adb({"action": "swipe", **p})

    def _do_tap(self, *_):
        try:
            x = int(self._tap_x.text)
            y = int(self._tap_y.text)
        except ValueError:
            self._tap_status.text = "Isi koordinat X dan Y"
            self._tap_status.color = RED
            return

        def _cb(resp):
            self._tap_status.text = "OK tap ({},{})".format(x, y) if resp.get("ok") else "Gagal"
            self._tap_status.color = GRN if resp.get("ok") else RED

        self._adb({"action": "tap", "x": x, "y": y}, cb=_cb)

    def _do_send_text(self, *_):
        txt = self._text_input.text.strip()
        if not txt:
            return
        self._adb({"action": "text", "text": txt},
                  cb=lambda resp: setattr(self._text_input, "text", "")
                  if resp.get("ok") else None)

    def _fire_macro(self, idx: int):
        def _bg():
            _post(self._base_url, "/api/command",
                  {"type": "fire_macro", "index": idx})
        threading.Thread(target=_bg, daemon=True).start()

    def on_stop(self):
        if self._poll_event:
            self._poll_event.cancel()


if __name__ == "__main__":
    SynthexApp().run()
