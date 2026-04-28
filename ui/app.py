# -*- coding: utf-8 -*-
"""ui/app.py - Synthex dashboard by Yohn18."""
import json, logging, os, re, sys, threading, time, tkinter as tk  # noqa: E401
from collections import deque
from datetime import datetime
from tkinter import ttk, scrolledtext
import customtkinter as ctk
import ui.ctk_compat as _ck
import pystray
from PIL import Image, ImageDraw, ImageFilter, ImageTk
from core.config import Config
from core.logger import get_logger

_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _get_data_file():
    if getattr(sys, 'frozen', False):
        _appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        _dir = os.path.join(_appdata, "Synthex", "data")
        os.makedirs(_dir, exist_ok=True)
        return os.path.join(_dir, "user_data.json")
    return os.path.join(_ROOT, "data", "user_data.json")
_DATA_FILE = _get_data_file()

_DARK_PALETTE  = ("#0a0a0f","#111118","#16162a","#0d0d16",
                   "#7c3aed","#06b6d4","#e2e8f0","#64748b",
                   "#10b981","#f87171","#f59e0b","#9d5cf6","#06b6d4")
_LIGHT_PALETTE = ("#F4F4FA","#FFFFFF","#EEEEF6","#E8E8F2",
                  "#6C4AFF","#8880FF","#1A1A30","#8888AA",
                  "#2A8C5C","#D04050","#B07800","#7C3AED","#2A7EDD")

def _get_theme_name() -> str:
    try:
        _cfg = os.path.join(_ROOT, "config.json")
        with open(_cfg, encoding="utf-8") as _f:
            return json.load(_f).get("ui", {}).get("theme", "dark")
    except Exception:
        return "dark"

_pal = _LIGHT_PALETTE if _get_theme_name() == "light" else _DARK_PALETTE
(BG, CARD, CARD2, SIDE, ACC, ACC2, FG, MUT, GRN, RED, YEL, PRP, BLUE) = _pal

# Step type icons (ASCII, no emoji)
_STEP_ICONS = {
    "go_to_url":        "->",
    "click":            "[*]",
    "type":             "[T]",
    "get_text":         "<-T",
    "get_number":       "<-#",
    "wait":             "[~]",
    "wait_for_element": "[W]",
    "screenshot":       "[S]",
    "sheet_read_cell":  "[R]",
    "sheet_write_cell": "[W]",
    "sheet_find_row":   "[F]",
    "sheet_read_row":   "[r]",
    "sheet_append_row": "[+]",
    "if_equals":                    "[=]",
    "if_contains":                  "[?]",
    "if_greater":                   "[>]",
    "notify":                       "[!]",
    "ai_prompt":                    "[AI]",
    "scrape_url":                   "[SC]",
    "sheet_get_pending_rows":       "[P]",
    "web_get_order_list":           "[O]",
    "validate_and_confirm_orders":  "[V]",
}


class _TkLogHandler(logging.Handler):
    """Buffered log handler — batches entries and flushes every 100ms to avoid UI flooding."""

    def __init__(self, w):
        super().__init__()
        self._w = w
        self._buf: list[tuple[str, str]] = []
        self._buf_lock = threading.Lock()
        self._scheduled = False

    def emit(self, record):
        msg = self.format(record) + "\n"
        tag = {logging.DEBUG: "debug", logging.INFO: "info",
               logging.WARNING: "warn"}.get(record.levelno, "error")
        with self._buf_lock:
            self._buf.append((msg, tag))
            if not self._scheduled:
                self._scheduled = True
                self._w.after(100, self._flush)

    def _flush(self):
        with self._buf_lock:
            entries = self._buf[:]
            self._buf.clear()
            self._scheduled = False
        if not entries:
            return
        self._w.configure(state="normal")
        for msg, tag in entries:
            self._w.insert(tk.END, msg, tag)
        self._w.see(tk.END)
        self._w.configure(state="disabled")


class UserData:
    def __init__(self):
        self._lock = threading.Lock()
        self._d = {k: [] for k in
                   ("websites", "recordings", "tasks",
                    "elements", "sheets")}
        self._activity: deque = deque(maxlen=500)
        try:
            with open(_DATA_FILE, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            for k in self._d:
                self._d[k] = saved.get(k, [])
            for entry in saved.get("activity", []):
                self._activity.append(entry)
        except FileNotFoundError:
            pass
        except Exception:
            logging.getLogger("ui").warning("UserData: gagal load %s", _DATA_FILE, exc_info=True)

    def save(self):
        dir_ = os.path.dirname(_DATA_FILE)
        os.makedirs(dir_, exist_ok=True)
        with self._lock:
            import tempfile
            snapshot = {**self._d, "activity": list(self._activity)}
            fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(snapshot, fh, indent=2)
                os.replace(tmp, _DATA_FILE)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    def log(self, task, result, ok=True):
        entry = {
            "time":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "task":   task,
            "result": result,
            "ok":     ok,
        }
        with self._lock:
            self._activity.appendleft(entry)
        self.save()

    @property
    def websites(self):   return self._d["websites"]
    @property
    def recordings(self): return self._d["recordings"]
    @property
    def tasks(self):      return self._d["tasks"]
    @property
    def activity(self):   return self._activity
    @property
    def elements(self):   return self._d["elements"]
    @property
    def sheets(self):     return self._d["sheets"]


# -- Widget helpers --

def _lbl(parent, text, text_color=FG, fg_color="transparent", font=("Segoe UI", 11), **kw):
    return _ck.Label(parent, text=text, text_color=text_color, fg_color=fg_color, font=font, **kw)

_bg_pending: dict = {}

def _deep_bg(widget, color):
    """Set fg_color on widget and all children. Debounced per widget to avoid
    blocking scroll events when hover fires rapidly during fast scrolling."""
    wid = id(widget)
    prev = _bg_pending.get(wid)
    if prev:
        try:
            widget.after_cancel(prev)
        except Exception:
            pass
    def _apply(w=widget, c=color):
        _bg_pending.pop(wid, None)
        try:
            w.configure(fg_color=c)
        except Exception:
            pass
        for child in w.winfo_children():
            try:
                child.configure(fg_color=c)
            except Exception:
                pass
    try:
        _bg_pending[wid] = widget.after(16, _apply)
    except Exception:
        pass

def _card(parent, title=""):
    f = _ck.Frame(parent, fg_color=CARD)
    if title:
        _lbl(f, title, text_color=ACC, fg_color=CARD,
             font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(10, 6))
    return f

def _fmt_duration(seconds: int) -> str:
    """Convert a number of seconds into a compact human-readable string."""
    if seconds < 60:
        return "{}s".format(seconds)
    minutes = seconds // 60
    if minutes < 60:
        return "{}m".format(minutes)
    hours = minutes // 60
    mins  = minutes % 60
    return "{}h {}m".format(hours, mins) if mins else "{}h".format(hours)


def _tree(parent, cols):
    t = ttk.Treeview(parent, columns=[c[0] for c in cols],
                     show="headings", selectmode="browse")
    for cid, head, w in cols:
        t.heading(cid, text=head)
        t.column(cid, width=w, anchor="w")
    t.pack(fill="both", expand=True)
    return t

def _apply_styles(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=FG, font=("Segoe UI", 11))
    s.configure("TFrame",  background=BG)
    s.configure("TLabel",  background=BG, foreground=FG)
    s.configure("TButton", background=CARD, foreground=FG,
                relief="flat", padding=[12, 7], borderwidth=1,
                bordercolor="#1c1c2e")
    s.map("TButton",
          background=[("active", ACC)], foreground=[("active", "#ffffff")])
    s.configure("Accent.TButton", background=ACC, foreground="#ffffff",
                font=("Segoe UI", 11, "bold"), padding=[16, 8])
    s.map("Accent.TButton", background=[("active", "#9d5cf6")])
    s.configure("Danger.TButton", background=CARD, foreground=RED,
                padding=[12, 7])
    s.map("Danger.TButton",
          background=[("active", RED)], foreground=[("active", "#ffffff")])
    s.configure("TEntry", fieldbackground=CARD, foreground=FG,
                insertcolor=FG, borderwidth=1, bordercolor="#1c1c2e",
                padding=[8, 6])
    s.configure("Treeview", background=CARD, foreground=FG,
                fieldbackground=CARD, borderwidth=0, rowheight=30)
    s.map("Treeview",
          background=[("selected", ACC)], foreground=[("selected", "#ffffff")])
    s.configure("Treeview.Heading", background=SIDE, foreground=MUT,
                font=("Segoe UI", 10, "bold"), borderwidth=0)
    s.configure("TScrollbar", background="#1c1c2e", troughcolor=BG,
                borderwidth=0, arrowcolor=MUT, width=4)
    s.configure("TCombobox", fieldbackground=CARD, foreground=FG,
                arrowcolor=FG, background=CARD, bordercolor="#1c1c2e")
    s.map("TCombobox",
          fieldbackground=[("readonly", CARD)], foreground=[("readonly", FG)])
    s.configure("TCheckbutton", background=BG, foreground=FG)
    s.map("TCheckbutton", background=[("active", BG)])


# -- Step type maps --

STEP_TYPES = ["Open URL", "Click", "Type", "Wait", "Extract", "Screenshot"]

_STEP_TO_ENGINE = {
    "Open URL":   "Open URL",
    "Click":      "Click Element",
    "Type":       "Type Text",
    "Wait":       "Wait",
    "Extract":    "Extract Text",
    "Screenshot": "Take Screenshot",
    "Buka URL":   "Open URL",
    "Klik":       "Click Element",
    "Ketik":      "Type Text",
    "Tunggu":     "Wait",
    "Ambil Nilai":"Extract Text",
    "Click Element":   "Click Element",
    "Type Text":       "Type Text",
    "Extract Text":    "Extract Text",
    "Take Screenshot": "Take Screenshot",
}


def _event_to_step(ev):
    t = ev.get("type", "")
    if t in _STEP_TO_ENGINE:
        return {"type": t, "value": ev.get("value", "")}
    if t == "navigate":
        return {"type": "Open URL", "value": ev.get("url", "")}
    if t == "click":
        return {"type": "Click", "value": ev.get("selector", "")}
    if t == "fill":
        return {"type": "Type",
                "value": "{} | {}".format(ev.get("selector",""),
                                          ev.get("value",""))}
    if t:
        return {"type": t, "value": ev.get("value", ev.get("url", ""))}
    return None


def _step_label(step):
    """One-line human description of a smart macro step."""
    t = step.get("type", "")
    if t == "go_to_url":        return "Go to: {}".format(step.get("url",""))
    if t == "click":            return "Click: {}".format(step.get("selector",""))
    if t == "type":             return "Type '{}' in {}".format(
        step.get("text",""), step.get("selector",""))
    if t == "get_text":         return "Get text [{}] -> {}".format(
        step.get("selector",""), step.get("var",""))
    if t == "get_number":       return "Get number [{}] -> {}".format(
        step.get("selector",""), step.get("var",""))
    if t == "wait":             return "Wait {}s".format(step.get("seconds","1"))
    if t == "wait_for_element": return "Wait for: {}".format(
        step.get("selector",""))
    if t == "screenshot":       return "Screenshot: {}".format(
        step.get("filename",""))
    if t == "sheet_read_cell":  return "Read {}!{} -> {}".format(
        step.get("sheet",""), step.get("cell",""), step.get("var",""))
    if t == "sheet_write_cell": return "Write {}!{} = {}".format(
        step.get("sheet",""), step.get("cell",""), step.get("value",""))
    if t == "sheet_find_row":   return "Find '{}' in {}.{} -> {}".format(
        step.get("value",""), step.get("sheet",""), step.get("column",""),
        step.get("var",""))
    if t == "sheet_read_row":   return "Read row {} [{}] -> {}".format(
        step.get("row",""), step.get("sheet",""), step.get("var",""))
    if t == "sheet_append_row": return "Append to {}: {}".format(
        step.get("sheet",""), step.get("values",""))
    if t == "if_equals":        return "If {} == {}".format(
        step.get("value1",""), step.get("value2",""))
    if t == "if_contains":      return "If '{}' contains '{}'".format(
        step.get("text",""), step.get("keyword",""))
    if t == "if_greater":       return "If {} > {}".format(
        step.get("num1",""), step.get("num2",""))
    if t == "notify":           return "Notify: {}".format(
        step.get("message",""))
    if t == "ai_prompt":        return "🤖 AI: {}… → {{{}}}".format(
        step.get("prompt","")[:40], step.get("var","ai_result"))
    if t == "scrape_url":       return "🌐 Scrape: {} → {{{}}}".format(
        step.get("url","")[:40], step.get("var","scraped_text"))
    return t or "(empty step)"


def _load_templates():
    path = os.path.join(_ROOT, "data", "templates.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _greeting():
    h = datetime.now().hour
    if 5 <= h < 12:
        return "Good morning"
    elif 12 <= h < 18:
        return "Good afternoon"
    else:
        return "Good evening"


def _extract_sheet_id(url):
    """Extract Google Spreadsheet ID from URL."""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else ""


def _resolve_icon():
    base = sys._MEIPASS if hasattr(sys, '_MEIPASS') else _ROOT
    for candidate in [
        os.path.join(base, 'assets', 'synthex.ico'),
        os.path.join(base, 'synthex.ico'),
    ]:
        if os.path.exists(candidate):
            return candidate
    return None

# ============================================================
#  Main application class
# ============================================================

class SynthexApp:
    NAV = [
        ("Home",             "home"),
        ("AUTOMASI",         ""),
        ("Web",              "web"),
        ("Spy",              "spy"),
        ("Record",           "record"),
        ("Schedule",         "schedule"),
        ("Templates",        "templates"),
        ("DATA",             ""),
        ("QRIS",             "qris"),
        ("Sheet",            "sheet"),
        ("Rekening",         "rekening"),
        ("Monitor",          "monitor"),
        ("KOMUNITAS",        ""),
        ("Chat",             "chat"),
        ("AI Chat",          "ai_chat"),
        ("Inbox",            "inbox"),
        ("Blog",             "blog"),
        ("DEVICE",           ""),
        ("Remote",           "remote"),
        ("SISTEM",           ""),
        ("History",          "history"),
        ("Logs",             "logs"),
        ("Settings",         "settings"),
        ("MASTER",           ""),
        ("Master Panel",     "master"),
    ]

    MASTER_EMAIL = "yohanesnzzz777@gmail.com"

    def __init__(self, config, engine=None):
        self.config  = config
        self.engine  = engine
        self.logger  = get_logger("ui")
        self._tray   = None
        self._hkl    = None
        self._root   = None
        self._email  = None
        self._token  = None
        self._ud      = UserData()
        self._ud_lock    = threading.Lock()
        self._dm_poll_id = None
        self._pages  = {}
        self._nav    = {}
        self._cur    = ""
        self._toasts : list = []   # active toast windows for stacking

        # Recording state
        self._rec        = False
        self._rbtn       = None
        self._tasks_tree = None
        self._rec_mode        = "simple"   # "simple" or "smart"
        self._simple_recorder = None       # SimpleRecorder instance
        self._rec_toolbar_win = None       # floating mini toolbar window
        self._rec_start_time  = 0.0        # wall time when recording started
        self._rec_timer_id    = None       # after() id for toolbar timer
        self._step_editor_open       = False  # True while smart record editor is open
        self._simple_step_editor_win = None   # ref ke window step editor simple rec
        self._rec_toggle_fn          = None   # set saat toolbar dibuka
        self._rec_pause_fn           = None   # set saat toolbar dibuka
        self._rec_unlimited          = False  # mode unlimited repeat

        # Spy panel state
        self._spy_active        = False
        self._spy_poll_id       = None
        self._spy_current_info  = {}
        self._spy_elements_tree = None
        self._spy_fields        = {}
        self._spy_btn           = None
        self._spy_status_lbl    = None
        self._floating_spy      = None

        # Spy-to-Macro callback: set when a field wants a selector from spy
        self._spy_selector_callback = None

        # Playback state
        self._playback_stop         = threading.Event()
        self._playback_pause        = threading.Event()
        self._playback_running      = False   # True while a playback thread is active
        self._recordings_tree       = None
        self._rec_count_lbl         = None
        self._rec_folder_var        = None
        self._last_selected_rec_idx = None    # tracks last selection for Ctrl+1
        # Barcode remote control
        # Remote control (ADB / scrcpy)
        self._adb             = None   # AdbManager instance
        self._scrcpy          = None   # ScrcpyManager instance
        self._rem_poll_id     = None   # after() id for scrcpy status poll
        self._adb_poll_id     = None   # after() id for ADB device list poll
        self._broadcast_poll_id = None # after() id for broadcast watcher
        # Chat
        self._chat_poll_id    = None
        self._chat_last_key   = None
        self._chat_pres_id    = None
        self._chat_unread     = 0      # unread message counter for badge
        self._dm_unread       = 0      # inbox unread DM counter

        # Macro builder state
        self._mb_steps      = []      # list of step dicts
        self._mb_selected   = -1      # selected step index
        self._mb_name_var   = None
        self._mb_edit_idx   = None    # task index being edited (None = new)
        self._mb_sched_type = None
        self._mb_sched_val  = None
        self._mb_sched_time = None
        self._mb_step_rows  = []      # frame refs for step rows
        self._mb_list_inner = None    # scrollable inner frame for steps
        self._mb_editor_frame = None  # right panel inner frame
        self._mb_field_vars = {}      # current editor field StringVars
        self._mb_type_var   = None    # step type var in editor
        self._mb_list_view  = None    # left schedule list frame
        self._mb_build_view = None    # builder frame

        # Sheet page state
        self._sheet_preview_frame = None
        self._sheet_quick_sheet   = None

        # AI Chat — persists across page navigations
        self._ai_chat_history: list = []

        # Remote macro + companion bridge
        self._macro_engine  = None   # MacroEngine instance
        self._bridge        = None   # SynthexBridge instance
        self._bridge_serial = ""     # serial that bridge tracks

    def set_auth(self, email, token, session_id=None):
        self._email      = email
        self._token      = token
        self._session_id = session_id
        threading.Thread(target=self._session_watcher, daemon=True).start()
        def _mark_online():
            try:
                from modules.chat import update_presence
                update_presence(email, token, online=True)
            except Exception:
                self.logger.debug("mark_online gagal", exc_info=True)
        threading.Thread(target=_mark_online, daemon=True).start()

        # Fetch remote config and cache it
        self._remote_config = {}
        def _fetch_rc():
            try:
                from modules.master_config import get_remote_config
                self._remote_config = get_remote_config(token)
                # Update nav button appearance for disabled features
                if self._root:
                    self._root.after(0, self._apply_remote_config_to_nav)
            except Exception:
                self.logger.debug("fetch_remote_config gagal", exc_info=True)
        threading.Thread(target=_fetch_rc, daemon=True).start()

        # Master: auto-deploy Firebase rules + init rekening URL on login
        if email == self.MASTER_EMAIL:
            def _master_init():
                import time as _t2
                _t2.sleep(3)
                try:
                    from auth.rules_deployer import deploy_rules
                    deploy_rules()
                except Exception:
                    pass
                try:
                    from modules.master_config import get_rekening_url, set_rekening_url
                    from modules.rekening import _BASE_DEFAULT
                    existing = get_rekening_url(token)
                    if existing == _BASE_DEFAULT:
                        set_rekening_url(_BASE_DEFAULT, token)
                except Exception:
                    pass
            threading.Thread(target=_master_init, daemon=True).start()

        # All users: force update, changelog, DM check
        def _post_login_checks():
            import time as _t3
            _t3.sleep(4)
            if self.config.get("app.dev_mode", False):
                return
            try:
                from modules.master_config import (get_min_version, get_changelog)
                local_ver = self.config.get("app.version", "0")

                # 1. Force update check
                min_ver = get_min_version(token)
                def _ver_tuple(v):
                    try: return tuple(int(x) for x in v.lstrip("v").split("."))
                    except Exception: return (0,)
                if _ver_tuple(min_ver) > _ver_tuple(local_ver):
                    def _show_force():
                        self._show_force_update_dialog(min_ver)
                    if self._root:
                        self._root.after(0, _show_force)
                    return

                # 2. Changelog popup (show once per version)
                cl = get_changelog(token)
                if cl:
                    seen_key = "ui._last_changelog_seen"
                    last_seen = self.config.get(seen_key, "")
                    if cl.get("version","") != last_seen and cl.get("version","") != local_ver:
                        def _show_cl(c=cl):
                            self._show_changelog_popup(c)
                            self.config.set(seen_key, c.get("version",""))
                            self.config.save()
                        if self._root:
                            self._root.after(500, _show_cl)

                # 3. Optional update check — paksa update jika versi baru tersedia
                try:
                    from modules.updater import get_latest_release, is_newer
                    rel = get_latest_release()
                    if rel and is_newer(rel["tag"], local_ver):
                        def _show_optional_update(tag=rel["tag"], url=rel["url"]):
                            self._show_force_download_dialog(tag, url)
                        if self._root:
                            self._root.after(0, _show_optional_update)
                        return
                except Exception:
                    pass

                # 4. DM check — set badge, toast if unread
                from modules.master_config import count_unread_dm
                n = count_unread_dm(email, token)
                if self._root:
                    self._root.after(0, lambda c=n: self._set_inbox_badge(c))
                if n > 0:
                    def _toast_dm(cnt=n):
                        self._show_toast(
                            "📬 {} pesan baru dari Admin".format(cnt),
                            duration=5000,
                            action=lambda: self._show("inbox"))
                    if self._root:
                        self._root.after(2000, _toast_dm)
            except Exception:
                pass
        threading.Thread(target=_post_login_checks, daemon=True).start()

        # Poll DM unread count every 90s — runs in background thread to avoid UI freeze
        def _dm_poll():
            if not self._root:
                return
            def _bg():
                try:
                    from auth.firebase_auth import get_valid_token
                    from modules.master_config import count_unread_dm
                    tok = get_valid_token()
                    em  = self._email
                    if tok and em:
                        n = count_unread_dm(em, tok)
                        if self._root:
                            self._root.after(0, lambda c=n: self._set_inbox_badge(c))
                except Exception:
                    pass
            threading.Thread(target=_bg, daemon=True).start()
            if self._root:
                self._dm_poll_id = self._root.after(90000, _dm_poll)
        if self._root:
            self._dm_poll_id = self._root.after(10000, _dm_poll)

    def _session_watcher(self):
        """Background thread: checks every 12s if another device claimed the session."""
        import time as _t
        from auth.firebase_auth import get_remote_session_id, get_valid_token

        # Wait for the main window to be ready
        for _ in range(60):
            if getattr(self, "_root", None):
                break
            _t.sleep(1)

        _t.sleep(5)  # extra grace after window opens

        while True:
            _t.sleep(12)
            try:
                tok = get_valid_token()
                if not tok or not self._email or not self._session_id:
                    continue
                remote_sid = get_remote_session_id(self._email, tok)
                if remote_sid is None:
                    continue  # RTDB unreachable — skip
                if remote_sid != self._session_id:
                    # Another device logged in — force kick
                    if getattr(self, "_root", None):
                        self._root.after(0, self._on_session_kicked)
                    return
            except Exception:
                continue

    def _on_session_kicked(self):
        """Called on main thread when another device has taken over the session."""
        # Clear local token
        from auth.firebase_auth import logout as _clear
        try:
            _clear()
        except Exception:
            pass

        # Show full-screen dark overlay — not dismissable
        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("")
        dlg.attributes("-topmost", True)
        dlg.configure(fg_color="#0A0A0F")

        W, H = 440, 230
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        dlg.geometry("{}x{}+{}+{}".format(W, H, (sw - W) // 2, (sh - H) // 2))

        _ck.Frame(dlg, fg_color=YEL, height=4).place(x=0, y=0, width=W)
        _ck.Label(dlg, text="Sesi Diakhiri", fg_color="#0A0A0F", text_color=YEL,
                 font=("Segoe UI", 15, "bold")).pack(pady=(28, 0))
        _ck.Label(dlg,
                 text="Akun ini login dari perangkat lain.\nKamu telah otomatis logout.", fg_color="#0A0A0F", text_color=FG, font=("Segoe UI", 10),
                 justify="center").pack(pady=(10, 0))
        _ck.Label(dlg, text="Jika bukan kamu, segera ganti password.", fg_color="#0A0A0F", text_color=MUT, font=("Segoe UI", 8)).pack(pady=(6, 0))
        _ck.Frame(dlg, fg_color=CARD, height=1).pack(fill="x", padx=28, pady=(16, 0))
        def _do_close():
            for _attr in ("_dm_poll_id", "_chat_poll_id", "_broadcast_poll_id",
                          "_adb_poll_id", "_spy_poll_id", "_rem_poll_id"):
                _pid = getattr(self, _attr, None)
                if _pid:
                    try: self._root.after_cancel(_pid)
                    except Exception: pass
                    setattr(self, _attr, None)
            try: self._root.destroy()
            except Exception: pass
        _ck.Button(dlg, text="  OK, Tutup  ", fg_color=YEL, text_color="#0A0A0F",
                  relief="flat", font=("Segoe UI", 10, "bold"),
                  cursor="hand2", padx=14, pady=7,
                  command=_do_close).pack(pady=14)

        dlg.update()
        dlg.deiconify()

        dlg.grab_set()
        dlg.focus_force()

    def run(self):
        self._start_tray()
        self._splash()
        self._root.mainloop()

    # -- Splash / loading --

    def _splash(self):
        r = self._root = ctk.CTk()
        _icon_path = _resolve_icon()
        if _icon_path:
            r.iconbitmap(_icon_path)
        r.title("SYNTHEX")
        r.geometry("460x280")
        r.resizable(False, False)
        r.configure(fg_color=BG)
        r.protocol("WM_DELETE_WINDOW", self._quit)  # splash: quit OK
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry("460x280+{}+{}".format((sw-460)//2, (sh-280)//2))
        _lbl(r, "SYNTHEX", text_color=ACC,
             font=("Segoe UI", 30, "bold")).pack(pady=(46, 2))
        _lbl(r, "Automation Platform  by Yohn18", text_color=MUT, font=("Segoe UI", 9)).pack()
        _ck.Frame(r, fg_color=CARD, height=1).pack(fill="x", padx=48, pady=(24, 0))
        self._pc = tk.Canvas(r, width=364, height=4, bg=CARD,
                             highlightthickness=0, bd=0)
        self._pc.pack(padx=48)
        _ck.Frame(r, fg_color=CARD, height=1).pack(fill="x", padx=48, pady=(0, 10))
        self._pv = tk.StringVar(value="Preparing...")
        _ck.Label(r, textvariable=self._pv, text_color=MUT, fg_color=BG,
                 font=("Segoe UI", 9)).pack()
        r.after(200, self._init_mods)

    def _init_mods(self):
        def _run():
            self._setup_hotkey()
            self.engine.init_modules(progress_cb=self._prog_cb)
            self._root.after(0, self._done)
        threading.Thread(target=_run, daemon=True).start()

    def _prog_cb(self, step, total, name):
        self._root.after(0, lambda: (
            self._pc.delete("bar"),
            self._pc.create_rectangle(
                0, 0, int(364 * step / total), 4,
                fill=ACC, outline="", tags="bar"),
            self._pv.set("Loading: {}...".format(name))))

    def _done(self):
        self._pc.create_rectangle(0, 0, 364, 4, fill=ACC, outline="", tags="bar")
        self._pv.set("All systems active.")
        self._root.after(400, self._dashboard)

    # ── Dashboard fade helper ──────────────────────────────────────────────────
    def _fade_in_dashboard(self, step=0):
        total = 20
        alpha = min(0.97, step / total * 0.97)
        try:
            self._root.attributes("-alpha", alpha)
        except Exception:
            pass
        if step < total:
            self._root.after(16, self._fade_in_dashboard, step + 1)

    # -- Dashboard shell --

    def _dashboard(self):
        for w in self._root.winfo_children():
            w.destroy()
        r = self._root
        r.title("SYNTHEX")
        r.geometry("1180x720")
        r.minsize(920, 600)
        r.resizable(True, True)
        r.configure(fg_color=BG)
        r.protocol("WM_DELETE_WINDOW", self._quit)
        _apply_styles(r)
        # Re-apply window icon (gets lost when window is reconfigured after splash)
        _ico = _resolve_icon()
        if _ico:
            try:
                r.iconbitmap(_ico)
            except Exception:
                pass
        # Set Windows taskbar AppUserModelID so taskbar shows synthex.ico correctly
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Yohn18.Synthex")
        except Exception:
            pass
        # Center on screen then fade in
        sw = r.winfo_screenwidth()
        sh = r.winfo_screenheight()
        r.geometry("1180x720+{}+{}".format((sw - 1180) // 2, (sh - 720) // 2))
        try:
            r.attributes("-alpha", 0.0)
        except Exception:
            pass
        r.after(50, self._fade_in_dashboard)

        # ── HEADER ────────────────────────────────────────────────────────────
        HDR_H = 54
        top = _ck.Frame(r, fg_color=SIDE, height=HDR_H)
        top.pack(fill="x")
        top.pack_propagate(False)

        # Canvas overlay for gradient bottom border
        _hdr_canvas = tk.Canvas(top, height=HDR_H, bg=SIDE,
                                 highlightthickness=0)
        _hdr_canvas.place(x=0, y=0, relwidth=1.0, height=HDR_H)

        def _draw_hdr_border(event=None):
            _hdr_canvas.delete("border")
            W = _hdr_canvas.winfo_width() or 1180
            # gradient bottom line: ACC → BLUE
            steps = 60
            for i in range(steps):
                t  = i / steps
                r_ = int(0x6C + (0x4A - 0x6C) * t)
                g_ = int(0x4A + (0x9E - 0x4A) * t)
                b_ = int(0xFF + (0xFF - 0xFF) * t)
                col = "#{:02x}{:02x}{:02x}".format(
                    max(0, min(255, r_)), max(0, min(255, g_)), max(0, min(255, b_)))
                x0 = int(W * i / steps)
                x1 = int(W * (i + 1) / steps)
                _hdr_canvas.create_rectangle(x0, HDR_H - 2, x1, HDR_H,
                                             fill=col, outline="", tags="border")
        _hdr_canvas.bind("<Configure>", _draw_hdr_border)
        top.after(100, _draw_hdr_border)

        # Animated left accent stripe
        _acc_bar = _ck.Frame(top, fg_color=ACC, width=4)
        _acc_bar.pack(side="left", fill="y")

        def _pulse_acc(step=0):
            widths = [4, 5, 6, 6, 5, 4, 3, 4]
            try:
                _acc_bar.configure(width=widths[step % len(widths)])
                top.after(120, _pulse_acc, step + 1)
            except Exception:
                pass
        top.after(500, _pulse_acc)

        # Logo
        _ck.Label(top, text="⚡", fg_color=SIDE, text_color=ACC,
                 font=("Segoe UI", 16)).pack(side="left", padx=(12, 4), pady=14)
        _ck.Label(top, text="SYNTHEX", fg_color=SIDE, text_color=ACC,
                 font=("Segoe UI", 16, "bold")).pack(side="left")

        # Page name indicator (updates on nav)
        self._page_lbl = _ck.Label(top, text="", fg_color=SIDE, text_color="#64748b",
                                   font=("Segoe UI", 8))
        self._page_lbl.pack(side="left", padx=(18, 0), pady=(18, 0))

        # Right side
        _exit_btn = _ck.Button(top, text=" ⏻  Exit ", fg_color="#1E0A0A", text_color=RED,
                               activebackground=RED, activeforeground="white",
                               font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                               padx=12, pady=5, cursor="hand2",
                               command=self._logout)
        _exit_btn.pack(side="right", padx=12, pady=13)
        _exit_btn.bind("<Enter>", lambda e: _exit_btn.configure(fg_color=RED, text_color="white"))
        _exit_btn.bind("<Leave>", lambda e: _exit_btn.configure(fg_color="#1E0A0A", text_color=RED))

        _help_btn = _ck.Button(top, text=" ? ", fg_color=CARD, text_color=ACC,
                               activebackground=ACC, activeforeground=BG,
                               font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                               padx=8, pady=5, cursor="hand2",
                               command=self._show_help)
        _help_btn.pack(side="right", pady=13)
        _help_btn.bind("<Enter>", lambda e: _help_btn.configure(fg_color=ACC, text_color=BG))
        _help_btn.bind("<Leave>", lambda e: _help_btn.configure(fg_color=CARD, text_color=ACC))

        # Search hint button → command palette
        _srch_btn = _ck.Button(top, text="  🔍  Cari fitur...  Ctrl+K ", fg_color=CARD2, text_color=MUT, relief="flat", bd=0,
                               font=("Segoe UI", 8), padx=10, pady=5,
                               cursor="hand2", anchor="w",
                               command=self._show_command_palette)
        _srch_btn.pack(side="right", padx=(0, 8), pady=13)
        _srch_btn.bind("<Enter>", lambda e: _srch_btn.configure(text_color=FG))
        _srch_btn.bind("<Leave>", lambda e: _srch_btn.configure(text_color=MUT))

        if self._email:
            _ck.Label(top, text="● " + self._email, fg_color=SIDE, text_color=GRN,
                     font=("Segoe UI", 8)).pack(side="right", padx=10)

        # ── ANNOUNCEMENT BAR (hidden by default, shown when active) ──────────
        self._ann_bar = _ck.Frame(r, fg_color="#B45309", padx=12, pady=5)
        self._ann_lbl = _ck.Label(self._ann_bar, text="", fg_color="#B45309", text_color="white", font=("Segoe UI", 9, "bold"),
                                 wraplength=900, justify="left")
        self._ann_lbl.pack(side="left", fill="x", expand=True)
        _ck.Button(self._ann_bar, text="✕", fg_color="#B45309", text_color="white",
                  relief="flat", bd=0, font=("Segoe UI", 9), cursor="hand2",
                  command=lambda: self._ann_bar.pack_forget()).pack(side="right")

        def _check_announcement():
            import threading as _t2
            def _bg():
                try:
                    from modules.master_config import get_announcement
                    from auth.firebase_auth import get_valid_token
                    tok = get_valid_token()
                    if not tok:
                        return
                    ann = get_announcement(tok)
                    if ann and ann.get("enabled") and ann.get("text"):
                        clr = ann.get("color", "#B45309")
                        txt = ann.get("text", "")
                        def _show():
                            self._ann_bar.configure(fg_color=clr)
                            self._ann_lbl.configure(text=txt, fg_color=clr)
                            self._ann_bar.pack(fill="x", after=top)
                    else:
                        _show = self._ann_bar.pack_forget
                    if self._root:
                        self._root.after(0, _show)
                except Exception:
                    pass
                if self._root:
                    self._root.after(60000, _check_announcement)
            _t2.Thread(target=_bg, daemon=True).start()

        self._root.after(2000, _check_announcement)
        r.bind_all("<Control-k>", lambda e: self._show_command_palette())

        # ── BODY ──────────────────────────────────────────────────────────────
        body = _ck.Frame(r, fg_color=BG)
        body.pack(fill="both", expand=True)

        # ── Generate PIL nav icons ─────────────────────────────────────────────
        from ui.icons import generate_all_icons, generate_all_icons_glow
        _acc_rgb   = (108, 74, 255)
        _muted_rgb = (80, 80, 112)
        _nav_keys  = [k for _, k in self.NAV if k]
        _raw_icons     = generate_all_icons(20, _acc_rgb,   keys=_nav_keys)
        _raw_icons_dim = generate_all_icons(20, _muted_rgb, keys=_nav_keys)
        # Convert to ImageTk.PhotoImage — store on self to prevent GC
        self._nav_photo     = {k: ImageTk.PhotoImage(v) for k, v in _raw_icons.items()}
        self._nav_photo_dim = {k: ImageTk.PhotoImage(v) for k, v in _raw_icons_dim.items()}
        # Glow icons generated lazily on first hover to avoid GaussianBlur at startup
        self._nav_photo_glow = {}
        def _build_glow_bg():
            glow = generate_all_icons_glow(20, _acc_rgb)
            photos = {k: ImageTk.PhotoImage(v) for k, v in glow.items()}
            if self._root:
                self._root.after(0, lambda p=photos: self._nav_photo_glow.update(p))
        threading.Thread(target=_build_glow_bg, daemon=True).start()

        # ── SIDEBAR ───────────────────────────────────────────────────────────
        SIDE_W = 220
        side = _ck.Frame(body, fg_color=SIDE, width=SIDE_W)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        # Sidebar right glow border (2px gradient look)
        _ck.Frame(body, fg_color="#1c1c2e", width=1).pack(side="left", fill="y")
        _ck.Frame(body, fg_color="#111118", width=1).pack(side="left", fill="y")

        # Sidebar top: mini branding
        _sb_top = _ck.Frame(side, fg_color="#0a0a0f", height=40)
        _sb_top.pack(fill="x")
        _sb_top.pack_propagate(False)
        _ck.Frame(_sb_top, fg_color=ACC, width=3).pack(side="left", fill="y")
        _ck.Label(_sb_top, text="⚡ Menu", fg_color="#0a0a0f", text_color="#64748b",
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=10)
        _ck.Frame(side, fg_color="#1c1c2e", height=1).pack(fill="x")

        # Bottom status bar
        self._sv = tk.StringVar(value="")
        _sb_bottom = _ck.Frame(side, fg_color=SIDE)
        _sb_bottom.pack(side="bottom", fill="x")
        _ck.Frame(_sb_bottom, fg_color="#1c1c2e", height=1).pack(fill="x")
        _ck.Label(_sb_bottom, textvariable=self._sv, fg_color=SIDE, text_color=MUT,
                 font=("Segoe UI", 8), wraplength=SIDE_W - 20,
                 justify="left").pack(anchor="w", padx=14, pady=(6, 8))

        # Scrollable nav area
        _side_sb = _ck.Scrollbar(side, orient="vertical")
        _side_sb.pack(side="right", fill="y")
        _side_cv = tk.Canvas(side, bg=SIDE, highlightthickness=0,
                             yscrollcommand=_side_sb.set, width=SIDE_W - 14)
        _side_cv.pack(side="left", fill="both", expand=True)
        _side_sb.config(command=_side_cv.yview)
        _side_inner = _ck.Frame(_side_cv, fg_color=SIDE)
        _side_win = _side_cv.create_window((0, 0), window=_side_inner, anchor="nw")
        _side_inner.bind("<Configure>", lambda e: _side_cv.configure(
            scrollregion=_side_cv.bbox("all")))
        _side_cv.bind("<Configure>", lambda e: _side_cv.itemconfig(_side_win, width=e.width))
        _side_cv.bind("<MouseWheel>", lambda e: _side_cv.yview_scroll(
            int(-1*(e.delta/120)), "units"))

        _is_master = (self._email == self.MASTER_EMAIL)
        self._nav       = {}
        self._nav_bars  = {}
        self._nav_icons = {}   # key -> icon Label widget (for swapping image)

        for label, key in self.NAV:
            if key == "master" and not _is_master:
                continue
            if key == "" and label == "MASTER" and not _is_master:
                continue

            if key == "":
                # Category separator
                sep_f = _ck.Frame(_side_inner, fg_color=SIDE)
                sep_f.pack(fill="x", padx=12, pady=(8, 2))
                _ck.Frame(sep_f, fg_color="#1c1c2e", height=1).pack(fill="x", pady=(0, 4))
                _sep_clr = ACC if label == "MASTER" else MUT
                _ck.Label(sep_f, text=label.lower(), fg_color=SIDE, text_color=_sep_clr,
                         font=("Segoe UI", 7, "bold"), anchor="w", pady=0).pack(anchor="w")
                continue

            # Nav row — fixed height for consistent compact look
            row = _ck.Frame(_side_inner, fg_color=SIDE, height=36)
            row.pack(fill="x")
            row.pack_propagate(False)
            row.bind("<MouseWheel>", lambda e: _side_cv.yview_scroll(
                int(-1*(e.delta/120)), "units"))

            # Active bar (left edge glow) — always packed, color changes instead of pack/forget
            bar = _ck.Frame(row, fg_color=SIDE, width=3)
            bar.pack(side="left", fill="y")
            self._nav_bars[key] = bar

            # Row inner container (for hover bg)
            row_inner = _ck.Frame(row, fg_color=SIDE)
            row_inner.pack(fill="both", side="left", expand=True)
            row_inner.bind("<MouseWheel>", lambda e: _side_cv.yview_scroll(
                int(-1*(e.delta/120)), "units"))

            # Icon label (PIL image)
            dim_photo = self._nav_photo_dim.get(key)
            icon_lbl = _ck.Label(row_inner, image=dim_photo, fg_color=SIDE,
                                padx=10, pady=0, cursor="hand2")
            icon_lbl.pack(side="left", pady=0)
            icon_lbl.bind("<MouseWheel>", lambda e: _side_cv.yview_scroll(
                int(-1*(e.delta/120)), "units"))
            self._nav_icons[key] = icon_lbl

            # Text label
            _NAV_FG = "#94a3b8"
            text_lbl = _ck.Label(row_inner, text=label, fg_color=SIDE, text_color=_NAV_FG,
                                font=("Segoe UI", 10), anchor="w", cursor="hand2",
                                padx=4, pady=0)
            text_lbl.pack(side="left", fill="x", expand=True)
            text_lbl.bind("<MouseWheel>", lambda e: _side_cv.yview_scroll(
                int(-1*(e.delta/120)), "units"))

            # Bind click on all row widgets directly (no invisible overlay button)
            _cmd = lambda k=key: self._show(k)
            for w in [row_inner, icon_lbl, text_lbl]:
                w.bind("<Button-1>", lambda e, c=_cmd: c())

            self._nav[key] = text_lbl

            def _nav_enter(e, ri=row_inner, k=key, il=icon_lbl, tl=text_lbl):
                if self._cur != k:
                    ri.configure(fg_color=CARD2)
                    for ch in ri.winfo_children():
                        try: ch.configure(fg_color=CARD2)
                        except Exception: pass
                    ph = self._nav_photo.get(k)
                    if ph:
                        il.configure(image=ph, fg_color=CARD2)
                    tl.configure(text_color=FG, fg_color=CARD2)
                    bar_w = self._nav_bars.get(k)
                    if bar_w:
                        bar_w.configure(fg_color=ACC2)

            def _nav_leave(e, ri=row_inner, k=key, il=icon_lbl, tl=text_lbl):
                if self._cur != k:
                    ri.configure(fg_color=SIDE)
                    for ch in ri.winfo_children():
                        try: ch.configure(fg_color=SIDE)
                        except Exception: pass
                    ph = self._nav_photo_dim.get(k)
                    if ph:
                        il.configure(image=ph, fg_color=SIDE)
                    tl.configure(text_color=_NAV_FG, fg_color=SIDE)
                    bar_w = self._nav_bars.get(k)
                    if bar_w and bar_w.cget("fg_color") != ACC:
                        bar_w.configure(fg_color=SIDE)

            for w in [row_inner, icon_lbl, text_lbl]:
                w.bind("<Enter>", _nav_enter)
                w.bind("<Leave>", _nav_leave)

        # ── CONTENT ───────────────────────────────────────────────────────────
        self._content = _ck.Frame(body, fg_color=BG)
        self._content.pack(side="left", fill="both", expand=True)

        # ── CLOCK (right side of header) ──────────────────────────────────────
        self._cl = _ck.Label(top, text="", text_color=MUT, fg_color=SIDE, font=("Segoe UI", 8))
        self._cl.pack(side="right", padx=6)
        self._tick()

        self._page_builders = {
            "home":      self._pg_home,
            "web":       self._pg_web,
            "spy":       self._pg_spy,
            "record":    self._pg_record,
            "schedule":  self._pg_schedule,
            "templates": self._pg_templates,
            "qris":      self._pg_qris,
            "sheet":     self._pg_sheet,
            "rekening":  self._pg_rekening,
            "monitor":   self._pg_monitor,
            "remote":    self._pg_remote,
            "chat":      self._pg_chat,
            "ai_chat":   self._pg_ai_chat,
            "blog":      self._pg_blog,
            "inbox":     self._pg_inbox,
            "history":   self._pg_history,
            "logs":      self._pg_logs,
            "settings":  self._pg_settings,
            "master":    self._pg_master,
        }

        self._show("home")
        self._root.after(400, self._maybe_show_onboarding)

    def _set_chat_badge(self, count: int):
        """Update unread badge on Chat nav button."""
        self._chat_unread = max(0, count)
        btn = self._nav.get("chat")
        if not btn:
            return
        if self._chat_unread > 0:
            btn.configure(
                text="  \U0001f4ac  Chat  \u2022{}".format(self._chat_unread), text_color="#7C3AED")
        else:
            btn.configure(text="  \U0001f4ac  Chat", text_color=MUT)

    def _set_inbox_badge(self, count: int):
        """Update unread badge on Inbox nav button."""
        self._dm_unread = max(0, count)
        btn = self._nav.get("inbox")
        if not btn:
            return
        if self._dm_unread > 0:
            btn.configure(
                text="  \U0001f4ec  Inbox  \u2022{}".format(self._dm_unread), text_color="#E11D48")
        else:
            btn.configure(text="  \U0001f4ec  Inbox", text_color=MUT)

    # (old _show_toast removed — see new implementation below)

    _RC_FEATURE_MAP = {
        "rekening": "rekening_enabled",
        "chat":     "chat_enabled",
        "blog":     "blog_enabled",
        "remote":   "remote_enabled",
        "monitor":  "monitor_enabled",
        "spy":      "spy_enabled",
    }

    def _show(self, key):
        # Remote config: block disabled features (non-master)
        if (self._email != self.MASTER_EMAIL and
                key in self._RC_FEATURE_MAP and
                hasattr(self, "_remote_config")):
            rc_key = self._RC_FEATURE_MAP[key]
            if not self._remote_config.get(rc_key, True):
                self._show_alert("Fitur Nonaktif",
                    "Fitur ini sedang dinonaktifkan oleh admin.\n"
                    "Coba lagi nanti.", kind="warning")
                return

        if self._cur in self._pages:
            self._pages[self._cur].pack_forget()
        _NAV_FG_INACTIVE = "#94a3b8"
        for k, lbl in self._nav.items():
            try:
                lbl.configure(text_color=_NAV_FG_INACTIVE)
                parent = lbl.master
                parent.configure(fg_color=SIDE)
                for ch in parent.winfo_children():
                    try: ch.configure(fg_color=SIDE)
                    except Exception: pass
                # restore dim icon
                ph_dim = self._nav_photo_dim.get(k)
                il = self._nav_icons.get(k)
                if il and ph_dim:
                    il.configure(image=ph_dim, fg_color=SIDE)
            except Exception:
                pass
            bar_w = self._nav_bars.get(k)
            if bar_w:
                bar_w.configure(fg_color=SIDE)
        if key in self._nav:
            lbl = self._nav[key]
            try:
                lbl.configure(text_color=FG)
                parent = lbl.master
                _deep_bg(parent, "#1a0a3e")
                # glow icon for active
                ph_glow = self._nav_photo_glow.get(key)
                il = self._nav_icons.get(key)
                if il and ph_glow:
                    il.configure(image=ph_glow, fg_color="#1a0a3e")
            except Exception:
                pass
            bar_w = self._nav_bars.get(key)
            if bar_w:
                bar_w.configure(fg_color=ACC)
                self._animate_nav_bar(key)
        # AI Chat always rebuilds so provider/model/key reflect current settings
        if key == "ai_chat" and key in self._pages:
            try: self._pages[key].destroy()
            except Exception: pass
            del self._pages[key]

        if key not in self._pages:
            # Show skeleton placeholder while page builds
            _skel = _ck.Frame(self._content, fg_color=BG)
            _skel.pack(fill="both", expand=True)
            _skel_lbl = _ck.Label(_skel, text="", fg_color=BG, text_color=MUT,
                                  font=("Segoe UI", 9))
            _skel_lbl.pack(pady=60)
            _shimmer_colors = [CARD, CARD2, CARD]
            _skel_bars = []
            for _bw, _by in [(340, 80), (260, 104), (200, 128)]:
                _b = _ck.Frame(_skel, fg_color=CARD, height=10, width=_bw)
                _b.place(x=20, y=_by)
                _skel_bars.append(_b)

            def _shimmer(step=0):
                if not _skel.winfo_exists(): return
                col = _shimmer_colors[step % len(_shimmer_colors)]
                for _b in _skel_bars:
                    try: _b.configure(fg_color=col)
                    except Exception: pass
                if step < 6:
                    _skel.after(80, _shimmer, step + 1)

            _skel.after(10, _shimmer)
            self._root.update_idletasks()

            # Build actual page then replace skeleton
            self._pages[key] = self._page_builders[key]()
            try: _skel.destroy()
            except Exception: pass

        self._pages[key].pack(fill="both", expand=True)
        self._cur = key
        if key == "chat":
            self._set_chat_badge(0)
        # Page name indicator in header
        try:
            _names = {k: lbl for lbl, k in self.NAV if k}
            display = _names.get(key, key).upper()
            self._page_lbl.configure(text="/ " + display)
        except Exception:
            pass
        # Sweep line animation
        self._page_sweep()

    def _animate_nav_bar(self, key, step=0):
        """Pulse the active nav bar width on activation."""
        bar_w = self._nav_bars.get(key)
        if not bar_w:
            return
        widths = [1, 2, 4, 5, 4, 3]
        if step < len(widths):
            try:
                bar_w.configure(width=widths[step])
                self._root.after(35, self._animate_nav_bar, key, step + 1)
            except Exception:
                pass

    def _page_sweep(self):
        """Accent sweep line across content area top on page change."""
        try:
            sweep = _ck.Frame(self._content, fg_color=ACC, height=2)
            sweep.place(x=0, y=0, width=0)

            def _grow(step=0, total=14):
                try:
                    cw = self._content.winfo_width() or 900
                    w  = int(cw * step / total)
                    sweep.place(x=0, y=0, width=w)
                    if step < total:
                        self._root.after(18, _grow, step + 1, total)
                    else:
                        self._root.after(80, sweep.destroy)
                except Exception:
                    pass
            _grow()
        except Exception:
            pass

    def _apply_remote_config_to_nav(self):
        """Dim nav buttons for features disabled by master remote config."""
        if self._email == self.MASTER_EMAIL:
            return
        rc = getattr(self, "_remote_config", {})
        for page_key, rc_key in self._RC_FEATURE_MAP.items():
            btn = self._nav.get(page_key)
            if not btn:
                continue
            enabled = rc.get(rc_key, True)
            btn.configure(text_color=MUT if not enabled else (
                FG if self._cur == page_key else MUT))
            if not enabled:
                btn.configure(text_color="#333355")

    def _navigate(self, key):
        """Navigate to a page, rebuilding it if already cached."""
        if key in self._pages:
            self._pages[key].destroy()
            del self._pages[key]
        self._show(key)

    # ---------------------------------------------------------------- onboarding

    def _maybe_show_onboarding(self):
        """Show the onboarding wizard if the user hasn't completed it yet."""
        try:
            from ui.onboarding import onboarding_needed
            if onboarding_needed():
                self._launch_onboarding()
        except Exception as e:
            self.logger.warning("Onboarding check failed: {}".format(e))

    def _launch_onboarding(self):
        """Open the first-time setup wizard."""
        try:
            from ui.onboarding import OnboardingWizard
            wizard = OnboardingWizard(
                parent=self._root,
                engine=self.engine,
                user_data=self._ud,
                config=self.config,
                on_complete=lambda: self._navigate("home"),
                open_template=self._mb_open_with_template,
            )
            wizard.show()
        except Exception as e:
            self.logger.error("Failed to launch onboarding: {}".format(e))

    def _mb_open_with_template(self, template):
        """Navigate to macro builder and pre-load a template."""
        self._navigate("schedule")
        self._root.after(150, lambda: self._mb_load_template(template))

    def _mb_load_template(self, template):
        """Load template data into the macro builder (must be called after page is built)."""
        try:
            if self._mb_name_var and not self._mb_name_var.get():
                self._mb_name_var.set(template.get("name", ""))
            self._mb_steps = list(template.get("steps", []))
            self._mb_refresh_list()
            if self._mb_steps:
                self._mb_select_step(0)
        except Exception as e:
            self.logger.warning("_mb_load_template error: {}".format(e))

    def _tick(self):
        try:
            self._cl.configure(text=datetime.now().strftime("%d %b %Y  %H:%M:%S"))
            self._root.after(1000, self._tick)
        except Exception:
            pass

    def _hdr(self, f, title, sub=""):
        hdr_f = _ck.Frame(f, fg_color=BG)
        hdr_f.pack(fill="x", padx=24, pady=(20, 0))
        _ck.Frame(hdr_f, fg_color=ACC, width=3, height=22).pack(side="left", padx=(0, 12))
        hdr_inner = _ck.Frame(hdr_f, fg_color=BG)
        hdr_inner.pack(side="left")
        _lbl(hdr_inner, title, font=("Segoe UI", 15, "bold")).pack(anchor="w")
        if sub:
            _lbl(hdr_inner, sub, text_color=MUT, font=("Segoe UI", 10)).pack(
                anchor="w", pady=(2, 0))
        _ck.Frame(f, fg_color="#1c1c2e", height=1).pack(fill="x", padx=24, pady=(10, 12))

    # ================================================================
    #  HOME PAGE
    # ================================================================

    def _pg_home(self):
        f = _ck.Frame(self._content, fg_color=BG)

        # ── Scrollable body ──────────────────────────────────────────────────
        sb = _ck.Scrollbar(f, orient="vertical")
        sb.pack(side="right", fill="y")
        cv = tk.Canvas(f, bg=BG, highlightthickness=0, yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.config(command=cv.yview)
        body = _ck.Frame(cv, fg_color=BG)
        _wid = cv.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfig(_wid, width=e.width))
        def _home_scroll(e, _cv=cv):
            try:
                if _cv.winfo_exists() and _cv.winfo_ismapped():
                    _cv.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass
        cv.bind_all("<MouseWheel>", _home_scroll)

        # ── helper: hover card effect ────────────────────────────────────────
        def _card_hover(widget, children, bg_on, bg_off, border_on=None,
                        border_widget=None):
            def _on(e=None):
                _deep_bg(widget, bg_on)
                if border_widget and border_on:
                    try: border_widget.configure(fg_color=border_on)
                    except Exception: pass
            def _off(e=None):
                _deep_bg(widget, bg_off)
                if border_widget and border_on:
                    try: border_widget.configure(fg_color=border_on)
                    except Exception: pass
            for w in [widget] + list(children):
                try:
                    w.bind("<Enter>", lambda e, fn=_on: fn())
                    w.bind("<Leave>", lambda e, fn=_off: fn())
                except Exception:
                    pass

        name  = self._email.split("@")[0].capitalize() if self._email else "User"
        today = datetime.now().strftime("%A, %d %B %Y")

        # ── Hero banner ──────────────────────────────────────────────────────
        hero_wrap = _ck.Frame(body, fg_color=BG)
        hero_wrap.pack(fill="x", padx=16, pady=(12, 0))
        hero = _ck.Frame(hero_wrap, fg_color="#0d0520")
        hero.pack(fill="x")
        # Animated bottom accent line
        hero_line = tk.Canvas(hero_wrap, height=2, bg=BG, highlightthickness=0)
        hero_line.pack(fill="x")

        def _draw_hero_line(event=None):
            hero_line.delete("all")
            W = hero_line.winfo_width() or 900
            steps = 40
            for i in range(steps):
                t  = i / steps
                r_ = int(0x6C + (0x4A - 0x6C) * t)
                g_ = int(0x4A + (0x9E - 0x4A) * t)
                b_ = 0xFF
                col = "#{:02x}{:02x}{:02x}".format(
                    max(0, min(255, r_)), max(0, min(255, g_)), min(255, b_))
                x0 = int(W * i / steps)
                x1 = int(W * (i + 1) / steps)
                hero_line.create_rectangle(x0, 0, x1, 2, fill=col, outline="")
        hero_line.bind("<Configure>", _draw_hero_line)
        hero_wrap.after(80, _draw_hero_line)

        _ck.Frame(hero, fg_color=ACC, width=4).pack(side="left", fill="y", padx=(0, 14))
        hero_text = _ck.Frame(hero, fg_color="#0d0520")
        hero_text.pack(side="left", fill="both", expand=True, pady=12)
        _ck.Label(hero_text,
                 text="{}, {}!".format(_greeting(), name), fg_color="#0d0520", text_color="#e2e8f0",
                 font=("Segoe UI", 18, "bold"), pady=0).pack(anchor="w")
        _ck.Label(hero_text, text=today, fg_color="#0d0520", text_color=MUT,
                 font=("Segoe UI", 10), pady=0).pack(anchor="w", pady=(2, 0))
        ver = self.config.get("app.version", "")
        ver_lbl = _ck.Label(hero, text="v{}".format(ver), fg_color="#0d0520", text_color="#3a3a5a",
                           font=("Segoe UI", 8), pady=0)
        ver_lbl.pack(side="right", anchor="ne", padx=10, pady=6)

        # ── Stat chips ───────────────────────────────────────────────────────
        browser_ok = bool(self.engine and self.engine.browser and
                          getattr(self.engine.browser, "_ready", False))
        sheet_count  = len(self._ud.sheets)
        active_count = sum(1 for t in self._ud.tasks
                           if t.get("enabled", True) and
                           t.get("schedule_type", "manual") != "manual")

        # Generate home-page icons (26px, colored per chip)
        from ui.icons import generate_all_icons as _gen_icons
        if not hasattr(self, "_home_chip_photos"):
            self._home_chip_photos = {}
        _chip_icon_keys = ["web", "sheet", "schedule", "record"]
        _chip_icon_colors = [
            (0, 212, 170) if browser_ok else (240, 192, 96),
            (0, 212, 170) if sheet_count else (80, 80, 112),
            (108, 74, 255),
            (200, 200, 232),
        ]
        for _icon_k, _cc in zip(_chip_icon_keys, _chip_icon_colors):
            _ckey = "{}_{}".format(_icon_k, _cc)
            if _ckey not in self._home_chip_photos:
                _raw = _gen_icons(26, _cc, keys=[_icon_k])
                self._home_chip_photos[_ckey] = ImageTk.PhotoImage(_raw[_icon_k])

        chips_row = _ck.Frame(body, fg_color=BG)
        chips_row.pack(fill="x", padx=16, pady=(8, 0))
        for (lbl, val, clr), icon_key, icon_color in zip(
            [
                ("Chrome",  "Connected" if browser_ok else "Standby",
                 GRN if browser_ok else YEL),
                ("Sheets",  "{} connected".format(sheet_count), GRN if sheet_count else MUT),
                ("Tasks",   "{} aktif".format(active_count),    ACC),
                ("Macros",  "{} tersimpan".format(len(self._ud.tasks)), FG),
            ],
            _chip_icon_keys,
            _chip_icon_colors,
        ):
            chip = _ck.Frame(chips_row, fg_color=CARD)
            chip.pack(side="left", fill="both", expand=True, padx=(0, 6))
            # Top accent line
            _ck.Frame(chip, fg_color=clr, height=2).pack(fill="x")
            # Inner padding frame
            chip_inner = _ck.Frame(chip, fg_color=CARD)
            chip_inner.pack(fill="both", padx=12, pady=8)
            # Icon + label row
            icon_row = _ck.Frame(chip_inner, fg_color=CARD)
            icon_row.pack(anchor="w", pady=(0, 2))
            _ckey = "{}_{}".format(icon_key, icon_color)
            _ph = self._home_chip_photos.get(_ckey)
            if _ph:
                _ck.Label(icon_row, image=_ph, fg_color=CARD, pady=0).pack(side="left", padx=(0, 6))
            _ck.Label(icon_row, text=lbl, fg_color=CARD, text_color=MUT,
                     font=("Segoe UI", 8, "bold"), pady=0).pack(side="left", anchor="w")
            _ck.Label(chip_inner, text=val, fg_color=CARD, text_color=clr,
                     font=("Segoe UI", 12, "bold"), pady=0).pack(anchor="w")
            # Hover glow
            def _chip_enter(e, c=chip):
                _deep_bg(c, CARD2)
            def _chip_leave(e, c=chip):
                _deep_bg(c, CARD)
            chip.bind("<Enter>", _chip_enter)
            chip.bind("<Leave>", _chip_leave)
            for w in chip.winfo_children():
                w.bind("<Enter>", _chip_enter)
                w.bind("<Leave>", _chip_leave)

        # ── Quick actions ────────────────────────────────────────────────────
        # Generate 16px icons for quick action buttons
        if not hasattr(self, "_home_qa_photos"):
            self._home_qa_photos = {}
        _qa_defs = [
            ("schedule",  "+ Macro Baru",  lambda: self._show("schedule"), ACC,  (108, 74, 255)),
            ("record",    "Rekam Macro",   self._start_simple_rec,          GRN,  (0, 212, 170)),
            ("spy",       "Buka Spy",      self._open_floating_spy,         BLUE, (74, 158, 255)),
            ("templates", "Templates",     lambda: self._show("templates"), PRP,  (157, 92, 246)),
            ("logs",      "Lihat Log",     lambda: self._show("logs"),      MUT,  (100, 100, 140)),
        ]
        for _ik, _, __, ___, _rgb in _qa_defs:
            if _ik not in self._home_qa_photos:
                _raw = _gen_icons(14, _rgb, keys=[_ik])
                self._home_qa_photos[_ik] = ImageTk.PhotoImage(_raw[_ik])

        qa_wrap = _ck.Frame(body, fg_color=BG)
        qa_wrap.pack(fill="x", padx=16, pady=(8, 0))
        _ck.Label(qa_wrap, text="aksi cepat", fg_color=BG, text_color=MUT,
                 font=("Segoe UI", 7, "bold"), pady=0).pack(anchor="w", pady=(0, 5))
        qa = _ck.Frame(qa_wrap, fg_color=BG)
        qa.pack(fill="x")

        for icon_key, qa_lbl, qa_cmd, qa_clr, qa_rgb in _qa_defs:
            _ph = self._home_qa_photos.get(icon_key)
            # Use a Frame as button (icon + text side by side)
            qf = _ck.Frame(qa, fg_color=qa_clr, cursor="hand2")
            qf.pack(side="left", padx=(0, 8))
            qf.bind("<Button-1>", lambda e, c=qa_cmd: c())

            inner = _ck.Frame(qf, fg_color=qa_clr)
            inner.pack(padx=8, pady=4)
            inner.bind("<Button-1>", lambda e, c=qa_cmd: c())

            if _ph:
                il = _ck.Label(inner, image=_ph, fg_color=qa_clr)
                il.pack(side="left", padx=(0, 5))
                il.bind("<Button-1>", lambda e, c=qa_cmd: c())

            tl = _ck.Label(inner, text=qa_lbl, fg_color=qa_clr, text_color=BG,
                          font=("Segoe UI", 8, "bold"))
            tl.pack(side="left")
            tl.bind("<Button-1>", lambda e, c=qa_cmd: c())

            def _qb_enter(e, f=qf, i=inner, col=qa_clr):
                try:
                    r_ = min(255, int(col[1:3], 16) + 28)
                    g_ = min(255, int(col[3:5], 16) + 28)
                    b_ = min(255, int(col[5:7], 16) + 28)
                    hl = "#{:02x}{:02x}{:02x}".format(r_, g_, b_)
                    _deep_bg(f, hl)
                except Exception:
                    pass
            def _qb_leave(e, f=qf, col=qa_clr):
                _deep_bg(f, col)
            for w in [qf, inner] + list(inner.winfo_children()):
                w.bind("<Enter>", _qb_enter)
                w.bind("<Leave>", _qb_leave)

        # ── My Tasks ─────────────────────────────────────────────────────────
        my_tasks = list(enumerate(self._ud.tasks[:5]))
        if my_tasks:
            _ck.Label(body, text="my tasks", fg_color=BG, text_color=MUT,
                     font=("Segoe UI", 8, "bold"), pady=0).pack(
                anchor="w", padx=18, pady=(10, 4))
            mt_card = _ck.Frame(body, fg_color=CARD)
            mt_card.pack(fill="x", padx=16, pady=(0, 4))
            for task_idx, t in my_tasks:
                enabled = t.get("enabled", True)
                status  = t.get("last_status", "—")
                sc_type = t.get("schedule_type", "manual")
                sc_label = {"interval": "⏱ Interval",
                            "cron":     "📅 Cron",
                            "manual":   "▶ Manual"}.get(sc_type, sc_type)
                status_clr = {
                    "ok":      GRN, "success": GRN,
                    "fail":    RED, "error":   RED,
                    "running": YEL,
                }.get(str(status).lower(), MUT)

                row = _ck.Frame(mt_card, fg_color=CARD, padx=14, pady=7, cursor="hand2")
                row.pack(fill="x")
                _ck.Frame(mt_card, fg_color="#1c1c2e", height=1).pack(fill="x", padx=14)
                row.bind("<Enter>", lambda e, rw=row: _deep_bg(rw, CARD2))
                row.bind("<Leave>", lambda e, rw=row: _deep_bg(rw, CARD))

                # Status dot
                _ck.Label(row, text="●", fg_color=CARD, text_color=GRN if enabled else "#64748b",
                         font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))
                _ck.Label(row, text=t.get("name", "Tanpa Nama")[:32], fg_color=CARD, text_color=FG,
                         font=("Segoe UI", 9, "bold")).pack(side="left")
                _ck.Label(row, text=sc_label, fg_color=CARD, text_color=MUT,
                         font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))
                _ck.Label(row, text=str(status).upper(), fg_color=CARD, text_color=status_clr,
                         font=("Segoe UI", 8, "bold")).pack(side="right", padx=(0, 8))
                _ck.Button(row, text="▶ Run", fg_color=ACC, text_color="white",
                          font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                          padx=8, pady=2, cursor="hand2",
                          command=lambda idx=task_idx: (
                              self._show("schedule"),
                              self._root.after(200, lambda i=idx: self._run_task_by_idx(i))
                          )).pack(side="right")
            if len(self._ud.tasks) > len(my_tasks):
                _ck.Label(mt_card,
                         text="+ {} task lainnya — buka Schedule".format(
                             len(self._ud.tasks) - len(my_tasks)), fg_color=CARD, text_color=MUT, font=("Segoe UI", 8),
                         padx=14, pady=6).pack(anchor="w")

        # ── Feature grid (Tailwind-inspired cards) ─────────────────────────
        def _hex_blend(hex_a, hex_b, t):
            ar,ag,ab = int(hex_a[1:3],16), int(hex_a[3:5],16), int(hex_a[5:7],16)
            br,bg2,bb = int(hex_b[1:3],16), int(hex_b[3:5],16), int(hex_b[5:7],16)
            return "#{:02x}{:02x}{:02x}".format(
                int(ar+(br-ar)*t), int(ag+(bg2-ag)*t), int(ab+(bb-ab)*t))

        _CARD_HEX = CARD

        def _section_hdr(parent, title):
            row = _ck.Frame(parent, fg_color=BG)
            row.pack(fill="x", padx=20, pady=(24, 12))
            _ck.Frame(row, fg_color=ACC, width=3, height=20).pack(side="left", padx=(0, 12))
            _ck.Label(row, text=title, fg_color=BG, text_color=FG,
                     font=("Segoe UI", 12, "bold")).pack(side="left")

        def _feat_card(parent, key, icon, title, desc, accent):
            badge_bg  = _hex_blend(_CARD_HEX, accent, 0.22)
            hover_bg  = _hex_blend(_CARD_HEX, accent, 0.10)
            badge_hov = _hex_blend(_CARD_HEX, accent, 0.35)
            ar,ag,ab = int(accent[1:3],16), int(accent[3:5],16), int(accent[5:7],16)
            cr,cg,cb = int(_CARD_HEX[1:3],16), int(_CARD_HEX[3:5],16), int(_CARD_HEX[5:7],16)

            cell = _ck.Frame(parent, fg_color=_CARD_HEX, cursor="hand2")

            # Top gradient bar
            grad_cv = tk.Canvas(cell, height=4, highlightthickness=0, bd=0, bg=_CARD_HEX)
            grad_cv.pack(fill="x")

            def _draw_grad(e=None, cv=grad_cv,
                           _ar=ar,_ag=ag,_ab=ab,_cr=cr,_cg=cg,_cb=cb):
                cv.delete("all")
                W = cv.winfo_width() or 240
                steps = 30
                for i in range(steps):
                    t = (i / steps) ** 1.5
                    r_ = int(_ar*(1-t) + _cr*t)
                    g_ = int(_ag*(1-t) + _cg*t)
                    b_ = int(_ab*(1-t) + _cb*t)
                    col = "#{:02x}{:02x}{:02x}".format(
                        max(0,min(255,r_)), max(0,min(255,g_)), max(0,min(255,b_)))
                    x0 = int(W*i/steps); x1 = int(W*(i+1)/steps)
                    cv.create_rectangle(x0, 0, x1, 4, fill=col, outline="")

            grad_cv.bind("<Configure>", _draw_grad)
            cell.after(60, _draw_grad)

            inner = _ck.Frame(cell, fg_color=_CARD_HEX, padx=18, pady=16)
            inner.pack(fill="both", expand=True)

            # Icon badge
            badge = _ck.Frame(inner, fg_color=badge_bg, padx=12, pady=10)
            badge.pack(anchor="w", pady=(0, 12))
            badge_icon = _ck.Label(badge, text=icon, fg_color=badge_bg,
                                  font=("Segoe UI", 22))
            badge_icon.pack()

            # Title
            title_lbl = _ck.Label(inner, text=title, fg_color=_CARD_HEX, text_color="#e2e8f0",
                                  font=("Segoe UI", 12, "bold"))
            title_lbl.pack(anchor="w", pady=(0, 5))

            # Description
            desc_lbl = _ck.Label(inner, text=desc, fg_color=_CARD_HEX, text_color=MUT,
                                 font=("Segoe UI", 10), wraplength=180,
                                 justify="left")
            desc_lbl.pack(anchor="w", pady=(0, 14))

            # Full-width button (Canvas)
            btn_cv = tk.Canvas(inner, height=36, highlightthickness=0,
                               bd=0, bg=_CARD_HEX, cursor="hand2")
            btn_cv.pack(fill="x")

            def _draw_btn(e=None, cv=btn_cv, ac=accent):
                cv.delete("all")
                W = cv.winfo_width() or 200
                cv.create_rectangle(0, 0, W, 36, fill=ac, outline="")
                cv.create_text(W//2, 18, text="Buka  →",
                               fill="white", font=("Segoe UI", 10, "bold"))

            btn_cv.bind("<Configure>", _draw_btn)
            inner.after(80, _draw_btn)

            # Hover
            def _hover_on(e=None):
                cell.configure(fg_color=hover_bg)
                inner.configure(fg_color=hover_bg)
                grad_cv.configure(bg=hover_bg)
                badge.configure(fg_color=badge_hov)
                badge_icon.configure(fg_color=badge_hov)
                title_lbl.configure(fg_color=hover_bg)
                desc_lbl.configure(fg_color=hover_bg)
                btn_cv.configure(bg=hover_bg)

            def _hover_off(e=None):
                cell.configure(fg_color=_CARD_HEX)
                inner.configure(fg_color=_CARD_HEX)
                grad_cv.configure(bg=_CARD_HEX)
                badge.configure(fg_color=badge_bg)
                badge_icon.configure(fg_color=badge_bg)
                title_lbl.configure(fg_color=_CARD_HEX)
                desc_lbl.configure(fg_color=_CARD_HEX)
                btn_cv.configure(bg=_CARD_HEX)

            for w in [cell, grad_cv, inner, badge, badge_icon,
                      title_lbl, desc_lbl, btn_cv]:
                try:
                    w.bind("<Enter>",    lambda e, f=_hover_on:  f())
                    w.bind("<Leave>",    lambda e, f=_hover_off: f())
                    w.bind("<Button-1>", lambda e, k=key: self._show(k))
                except Exception:
                    pass
            return cell

        GROUPS = [
            ("⚡ AUTOMASI", [
                ("web",       "\U0001f310", "Web Scraping",  "Otomasi browser & scraping data",    "#7C3AED"),
                ("spy",       "\U0001f441", "Spy Vision",    "Deteksi elemen layar real-time",     "#0EA5E9"),
                ("record",    "⏺",     "Record Macro",  "Rekam & putar ulang aksi mouse/KB",  "#10B981"),
                ("schedule",  "\U0001f4c5", "Scheduler",     "Jadwal & otomasi tugas terjadwal",   "#F59E0B"),
                ("templates", "\U0001f4da", "Templates",     "Library template siap pakai",        "#8B5CF6"),
            ]),
            ("\U0001f4ca DATA", [
                ("qris",     "⚡",     "QRIS Dinamis",  "Konversi QRIS statis ke dinamis",    "#F59E0B"),
                ("sheet",    "\U0001f4c8", "Google Sheet",  "Sinkronisasi & baca spreadsheet",    "#06B6D4"),
                ("rekening", "\U0001f3e6", "Rekening",       "Validasi nomor rekening bank",       "#84CC16"),
                ("monitor",  "\U0001f4b9", "Monitor",        "Dashboard angka auto-update",        "#F97316"),
            ]),
            ("\U0001f4ac KOMUNITAS", [
                ("chat", "\U0001f4ac", "Chat",   "Ngobrol dengan user Synthex online",  "#EC4899"),
                ("blog", "\U0001f4f0", "Blog",   "Baca & tulis artikel komunitas",      "#6366F1"),
            ]),
            ("\U0001f5a5 DEVICE & SISTEM", [
                ("remote",   "\U0001f4f1", "Mirror HP",   "Mirror & kontrol perangkat Android", "#A855F7"),
                ("history",  "\U0001f4cb", "History",     "Riwayat semua aktivitas task",       "#64748B"),
                ("logs",     "\U0001f5d2", "Logs",        "Log sistem & error real-time",       "#4A9EFF"),
                ("settings", "⚙️", "Settings", "Konfigurasi & preferensi app",       "#6B7280"),
            ]),
        ]

        GCOLS = 3
        for group_title, features in GROUPS:
            _section_hdr(body, group_title)
            grid = _ck.Frame(body, fg_color=BG)
            grid.pack(fill="x", padx=20)
            for ci in range(GCOLS):
                grid.columnconfigure(ci, weight=1)
            for fi, (key, icon, title, desc, accent) in enumerate(features):
                r, c = divmod(fi, GCOLS)
                card = _feat_card(grid, key, icon, title, desc, accent)
                card.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")

        # ── Recent Activity ──────────────────────────────────────────────────
        _section_hdr(body, "🕐 AKTIVITAS TERAKHIR")
        ac = _ck.Frame(body, fg_color=CARD)
        ac.pack(fill="x", padx=20, pady=(0, 24))
        acts = list(self._ud.activity)[:6]
        if acts:
            for act in acts:
                ok = act.get("ok")
                arow = _ck.Frame(ac, fg_color=CARD, padx=14, pady=6)
                arow.pack(fill="x")
                _ck.Frame(ac, fg_color="#1c1c2e", height=1).pack(fill="x", padx=14)
                _ck.Label(arow, text="●", text_color=GRN if ok else RED, fg_color=CARD, font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))
                _ck.Label(arow, text=act.get("time", ""), text_color=MUT, fg_color=CARD,
                         font=("Segoe UI", 8), width=18, anchor="w").pack(side="left")
                _ck.Label(arow, text=act.get("task", "")[:36], fg_color=CARD, text_color=FG,
                         font=("Segoe UI", 9)).pack(side="left", padx=8)
                _ck.Label(arow, text="✓ OK" if ok else "✗ FAIL", text_color=GRN if ok else RED, fg_color=CARD, font=("Segoe UI", 8, "bold")).pack(side="right")
                arow.bind("<Enter>", lambda e, rw=arow: _deep_bg(rw, "#16162a"))
                arow.bind("<Leave>", lambda e, rw=arow: _deep_bg(rw, CARD))
        else:
            _ck.Label(ac, text="Belum ada aktivitas.", text_color=MUT, fg_color=CARD,
                     font=("Segoe UI", 9), padx=14, pady=12).pack(anchor="w")

        return f

    # ================================================================
    #  WEB PAGE
    # ================================================================

    def _pg_web(self):
        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Web Browser", "Navigate to websites in Chrome.")
        c = _card(f, "Open URL")
        c.pack(fill="x", padx=20)
        row = _ck.Frame(c, fg_color=CARD)
        row.pack(fill="x")
        self._url = tk.StringVar()
        _ck.Entry(row, textvariable=self._url,
                  font=("Segoe UI", 10)).pack(
            side="left", fill="x", expand=True, padx=(0, 8))
        _ck.Button(row, text="Open",
                   command=self._open_url).pack(side="left")
        sc = _card(f, "Saved Sites")
        sc.pack(fill="both", expand=True, padx=20, pady=(12, 20))
        t = _tree(sc, [("name", "Name", 140), ("url", "URL", 300),
                       ("cat", "Category", 100)])
        for s in self._ud.websites:
            t.insert("", "end", values=(
                s.get("name",""), s.get("url",""), s.get("category","")))
        return f

    # ================================================================
    #  SPY PAGE
    # ================================================================

    def _pg_spy(self):
        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Spy Mode", "Inspect Chrome elements in real-time.")

        main = _ck.Frame(f, fg_color=BG)
        main.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        left = _ck.Frame(main, fg_color=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        ctrl = _card(left, "Spy Controls")
        ctrl.pack(fill="x", pady=(0, 8))
        self._spy_btn = _ck.Button(
            ctrl, text="ENABLE SPY", fg_color=ACC, text_color=BG,
            font=("Segoe UI", 11, "bold"), relief="flat", bd=0,
            padx=16, pady=8, cursor="hand2", command=self._toggle_spy)
        self._spy_btn.pack(side="left", padx=(0, 8))
        _ck.Button(ctrl, text="Open Floating Spy",
                   command=self._open_floating_spy).pack(side="left",
                                                          padx=(0, 8))
        self._spy_status_lbl = _lbl(
            ctrl, "Inactive", text_color=MUT, fg_color=CARD, font=("Segoe UI", 9))
        self._spy_status_lbl.pack(side="left")

        guide = _card(left, "Usage Guide")
        guide.pack(fill="x", pady=(0, 8))
        for line in [
            "Step 1: Click \"Open Floating Spy\" button",
            "Step 2: Hover over any element in Chrome",
            "Step 3: Element info appears in spy window",
            "Step 4: Click CAPTURE to save element",
            "Step 5: Click USE IN MACRO to send selector to builder",
        ]:
            _lbl(guide, line, text_color=MUT, fg_color=CARD,
                 font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=1)

        info = _card(left, "Element Info")
        info.pack(fill="x", pady=(0, 8))
        self._spy_fields = {}
        for label, key in [
            ("Element Type", "type"),
            ("Text",         "text"),
            ("ID",           "id"),
            ("CSS Selector", "css_selector"),
            ("XPath",        "xpath"),
            ("Value",        "value"),
            ("Position",     "position"),
        ]:
            row = _ck.Frame(info, fg_color=CARD)
            row.pack(fill="x", pady=2)
            _lbl(row, "{}:".format(label), text_color=MUT, fg_color=CARD,
                 font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
            var = tk.StringVar(value="-")
            _ck.Label(row, textvariable=var, text_color=FG, fg_color=CARD,
                     font=("Segoe UI", 9), anchor="w").pack(
                side="left", fill="x", expand=True)
            self._spy_fields[key] = var
        _ck.Button(info, text="Save Element",
                   command=self._save_spy_element).pack(
            anchor="w", pady=(10, 0))

        saved = _card(left, "Saved Elements")
        saved.pack(fill="both", expand=True)
        self._spy_elements_tree = _tree(saved, [
            ("name",     "Name",     100),
            ("type",     "Type",      65),
            ("selector", "Selector", 195),
        ])
        btn_row = _ck.Frame(saved, fg_color=CARD)
        btn_row.pack(fill="x", pady=(6, 0))
        _ck.Button(btn_row, text="Fetch Value",
                   command=self._fetch_spy_element_value).pack(
            side="left", padx=(0, 4))
        _ck.Button(btn_row, text="Copy Selector",
                   command=self._copy_spy_selector).pack(
            side="left", padx=(0, 4))
        _ck.Button(btn_row, text="Scrape ke Sheet",
                   command=self._scrape_spy_to_sheet).pack(
            side="left", padx=(0, 4))
        _ck.Button(btn_row, text="Delete",
                   command=self._delete_spy_element).pack(side="right")
        self._refresh_spy_elements_tree()
        return f

    # ================================================================
    #  RECORD PAGE
    # ================================================================

    def _pg_record(self):
        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Action Recording",
                  "Rekam & putar ulang aksi secara otomatis.")

        # How-to strip
        how = _ck.Frame(f, fg_color="#0D1A0D", padx=14, pady=8)
        how.pack(fill="x", padx=20, pady=(0, 10))
        _ck.Label(how, text="Cara pakai:", fg_color="#0D1A0D", text_color=GRN, font=("Segoe UI", 8, "bold")).pack(
            side="left", padx=(0, 6))
        _ck.Label(how,
                 text="Simple Record = rekam gerakan mouse & ketikan  |  "
                      "Smart Record = buat langkah otomasi manual (URL, klik, ketik, dll)", fg_color="#0D1A0D", text_color=FG, font=("Segoe UI", 8)).pack(
            side="left", fill="x", expand=True)

        # Two mode cards
        cards = _ck.Frame(f, fg_color=BG)
        cards.pack(fill="x", padx=20, pady=(0, 12))

        # Simple Record card
        sc = _ck.Frame(cards, fg_color=CARD, padx=16, pady=14)
        sc.pack(side="left", fill="both", expand=True, padx=(0, 8))
        _lbl(sc, "SIMPLE RECORD", fg_color=CARD, text_color=ACC,
             font=("Segoe UI", 11, "bold")).pack(anchor="w")
        _lbl(sc,
             "Rekam semua klik mouse\ndan ketikan keyboard\nsecara otomatis.\n\n"
             "Cocok untuk tugas\nberulang di aplikasi\nmanapun (desktop/game).\n\n"
             "Shortcut: Ctrl+3", fg_color=CARD, text_color=MUT,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 10))
        _ck.Button(sc, text="Buka Recorder", fg_color=ACC, text_color=BG, font=("Segoe UI", 10, "bold"),
                  relief="flat", bd=0, padx=12, pady=8, cursor="hand2",
                  command=self._start_simple_rec).pack(fill="x")

        # Smart Record card
        ac = _ck.Frame(cards, fg_color=CARD, padx=16, pady=14)
        ac.pack(side="left", fill="both", expand=True)
        _lbl(ac, "SMART RECORD", fg_color=CARD, text_color=GRN,
             font=("Segoe UI", 11, "bold")).pack(anchor="w")
        _lbl(ac,
             "Buat langkah otomasi\nsatu per satu secara\nmanual: buka URL,\n"
             "klik elemen, ketik\nteks, tunggu, ambil\nteks, screenshot, dll.\n\n"
             "Hasil bisa dijalankan\nberkali-kali.", fg_color=CARD, text_color=MUT,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 10))
        _ck.Button(ac, text="Buat Langkah Baru", fg_color=GRN, text_color=BG, font=("Segoe UI", 10, "bold"),
                  relief="flat", bd=0, padx=12, pady=8, cursor="hand2",
                  command=self._start_smart_rec).pack(fill="x")

        # ── Daftar Rekaman Tersimpan ──────────────────────────────────────────
        lc = _ck.Frame(f, fg_color=CARD, padx=0, pady=0)
        lc.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Card header row (title + counter badge)
        lc_hdr = _ck.Frame(lc, fg_color=CARD, padx=14, pady=10)
        lc_hdr.pack(fill="x")
        _ck.Label(lc_hdr, text="Daftar Rekaman Tersimpan", fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        self._rec_count_lbl = _ck.Label(lc_hdr, text="", fg_color=ACC, text_color="white",
                 font=("Segoe UI", 8, "bold"),
                 padx=7, pady=1)
        self._rec_count_lbl.pack(side="left", padx=(8, 0))

        # Treeview inside a padded inner frame
        tree_frame = _ck.Frame(lc, fg_color=CARD, padx=14, pady=0)
        tree_frame.pack(fill="both", expand=True)

        self._recordings_tree = _tree(tree_frame, [
            ("name",     "Nama Rekaman",  200),
            ("type",     "Tipe",           70),
            ("steps",    "Langkah",        64),
            ("last",     "Terakhir Run",  148),
            ("duration", "Durasi",         72),
        ])
        self._recordings_tree.tag_configure("simple_tag", foreground=ACC)
        self._recordings_tree.tag_configure("smart_tag",  foreground=GRN)
        self._recordings_tree.bind(
            "<Double-1>", lambda e: self._edit_selected_recording())
        self._recordings_tree.bind(
            "<<TreeviewSelect>>", lambda e: self._on_rec_tree_select())

        # Right-click context menu
        _ctx = tk.Menu(self._recordings_tree, tearoff=0, bg=CARD2, fg=FG, activebackground=ACC,
                       activeforeground="white", relief="flat", bd=0)
        _ctx.add_command(label="Play",        command=self._play_selected_recording)
        _ctx.add_command(label="Edit Steps",  command=self._edit_selected_recording)
        _ctx.add_separator()
        _ctx.add_command(label="Naik",        command=self._move_rec_up)
        _ctx.add_command(label="Turun",       command=self._move_rec_down)
        _ctx.add_separator()
        _ctx.add_command(label="Hapus",       command=self._delete_selected_recording)

        def _show_ctx(e):
            row = self._recordings_tree.identify_row(e.y)
            if row:
                self._recordings_tree.selection_set(row)
                try:
                    _ctx.tk_popup(e.x_root, e.y_root)
                finally:
                    _ctx.grab_release()

        self._recordings_tree.bind("<Button-3>", _show_ctx)

        # Action button row
        act_row = _ck.Frame(lc, fg_color="#14141E", padx=14, pady=8)
        act_row.pack(fill="x")

        _BTN = dict(font=("Segoe UI", 9), relief="flat", bd=0,
                    padx=14, pady=6, cursor="hand2")
        _ck.Button(act_row, text="  Play", fg_color=GRN, text_color="white",
                  command=self._play_selected_recording, **_BTN).pack(
            side="left", padx=(0, 4))
        _ck.Button(act_row, text="  Edit", fg_color=ACC, text_color="white",
                  command=self._edit_selected_recording, **_BTN).pack(
            side="left", padx=(0, 4))
        _ck.Button(act_row, text="  Hapus", fg_color=RED, text_color="white",
                  command=self._delete_selected_recording, **_BTN).pack(
            side="left", padx=(0, 4))
        # divider
        _ck.Frame(act_row, fg_color=MUT, width=1, height=22).pack(
            side="left", padx=(6, 10))
        _ck.Button(act_row, text="Naik", fg_color=CARD2, text_color=FG,
                  command=self._move_rec_up, **_BTN).pack(
            side="left", padx=(0, 4))
        _ck.Button(act_row, text="Turun", fg_color=CARD2, text_color=FG,
                  command=self._move_rec_down, **_BTN).pack(side="left")

        self._rec_folder_var = tk.StringVar(value="General")
        self._refresh_recordings_tree()
        return f

    # ================================================================
    #  SCHEDULE PAGE  (Macro Builder)
    # ================================================================

    def _pg_schedule(self):
        """Schedule page: toggles between list view and builder view."""
        f = _ck.Frame(self._content, fg_color=BG)

        # -- List view --
        self._mb_list_view = _ck.Frame(f, fg_color=BG)
        self._mb_list_view.pack(fill="both", expand=True)

        self._hdr(self._mb_list_view, "Smart Macros",
                  "Automate tasks: browser + Google Sheets + notifications.")

        top_bar = _card(self._mb_list_view)
        top_bar.pack(fill="x", padx=20, pady=(0, 8))
        _ck.Button(top_bar, text="+ Create New Macro", fg_color=ACC, text_color=BG, font=("Segoe UI", 11, "bold"),
                  relief="flat", bd=0, padx=18, pady=9, cursor="hand2",
                  command=lambda: self._mb_open(parent=f)).pack(side="left")
        _ck.Button(top_bar, text="Run Now",
                   command=self._run_selected_task).pack(
            side="left", padx=(8, 0))
        _ck.Button(top_bar, text="Edit",
                   command=lambda: self._mb_open(
                       parent=f, edit_idx=self._selected_task_idx()
                   )).pack(side="left", padx=(4, 0))
        _ck.Button(top_bar, text="Toggle ON/OFF",
                   command=self._toggle_task_enabled).pack(
            side="left", padx=(4, 0))
        _ck.Button(top_bar, text="Delete",
                   command=self._delete_selected_task).pack(
            side="left", padx=(4, 0))

        lc = _card(self._mb_list_view, "Saved Macros")
        lc.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self._tasks_tree = _tree(lc, [
            ("name",     "Macro Name",  190),
            ("steps",    "Steps",        45),
            ("schedule", "Schedule",    110),
            ("next_run", "Next Run",    120),
            ("last_run", "Last Run",    135),
            ("status",   "Status",       65),
            ("active",   "Active",       45),
        ])
        # Row color tags: green=OK, red=failed, gray=paused, yellow=running
        self._tasks_tree.tag_configure("status_ok",      foreground=GRN)
        self._tasks_tree.tag_configure("status_fail",    foreground=RED)
        self._tasks_tree.tag_configure("status_paused",  foreground=MUT)
        self._tasks_tree.tag_configure("status_running", foreground=YEL)
        self._tasks_tree.bind("<Double-1>", lambda e: self._run_selected_task())
        self._tasks_tree.bind("<Button-3>", self._tasks_tree_right_click)

        # ── Drag-and-drop reorder ─────────────────────────────────────
        _dnd = {"item": None, "start_y": 0}

        def _dnd_start(e):
            item = self._tasks_tree.identify_row(e.y)
            if item:
                _dnd["item"] = item
                _dnd["start_y"] = e.y
                self._tasks_tree.configure(cursor="fleur")

        def _dnd_motion(e):
            if not _dnd["item"]:
                return
            target = self._tasks_tree.identify_row(e.y)
            if target and target != _dnd["item"]:
                self._tasks_tree.selection_set(target)

        def _dnd_release(e):
            src = _dnd["item"]
            _dnd["item"] = None
            self._tasks_tree.configure(cursor="")
            if not src:
                return
            target = self._tasks_tree.identify_row(e.y)
            if not target or target == src:
                self._tasks_tree.selection_set(src)
                return
            src_idx = self._tasks_tree.index(src)
            tgt_idx = self._tasks_tree.index(target)
            with self._ud_lock:
                tasks = self._ud.tasks
                if src_idx < len(tasks) and tgt_idx < len(tasks):
                    task_moved = tasks.pop(src_idx)
                    tasks.insert(tgt_idx, task_moved)
            self._ud.save()
            self._refresh_tasks_tree()
            self._show_toast("Urutan macro diperbarui", kind="success")

        self._tasks_tree.bind("<ButtonPress-1>",  _dnd_start,   add="+")
        self._tasks_tree.bind("<B1-Motion>",       _dnd_motion)
        self._tasks_tree.bind("<ButtonRelease-1>", _dnd_release, add="+")

        self._refresh_tasks_tree()
        self._start_countdown_refresh()

        # -- Builder view (hidden initially) --
        self._mb_build_view = _ck.Frame(f, fg_color=BG)
        # Built on demand when _mb_open() is called

        return f

    def _mb_open(self, parent=None, edit_idx=None):
        """Switch schedule page to macro builder."""
        self._mb_list_view.pack_forget()

        # Reset builder state
        self._mb_edit_idx = edit_idx
        existing = (self._ud.tasks[edit_idx]
                    if edit_idx is not None and
                    0 <= edit_idx < len(self._ud.tasks) else None)

        self._mb_steps    = list(existing.get("steps", []) if existing else [])
        self._mb_selected = -1

        # Rebuild builder view
        for w in self._mb_build_view.winfo_children():
            w.destroy()
        self._mb_build_view.pack(fill="both", expand=True)
        self._mb_build_inner(existing)

    def _mb_back(self):
        """Return to macro list."""
        self._mb_build_view.pack_forget()
        self._mb_list_view.pack(fill="both", expand=True)
        self._refresh_tasks_tree()

    def _mb_build_inner(self, existing=None):
        """Build the macro builder UI inside _mb_build_view."""
        f = self._mb_build_view

        # -- Top bar --
        top = _ck.Frame(f, fg_color=SIDE, height=52)
        top.pack(fill="x")
        top.pack_propagate(False)
        _ck.Button(top, text="< Back", fg_color=SIDE, text_color=MUT,
                  font=("Segoe UI", 10), relief="flat", bd=0,
                  padx=12, pady=8, cursor="hand2",
                  command=self._mb_back).pack(side="left", padx=4, pady=8)
        _ck.Frame(top, fg_color=MUT, width=1).pack(side="left", fill="y",
                                              padx=4, pady=8)
        _lbl(top, "Macro Name:", text_color=MUT, fg_color=SIDE,
             font=("Segoe UI", 9)).pack(side="left", padx=(8, 4), pady=14)
        self._mb_name_var = tk.StringVar(
            value=existing.get("name","") if existing else "")
        name_entry = _ck.Entry(top, textvariable=self._mb_name_var, fg_color=CARD, text_color=FG, insertbackground=FG,
                              font=("Segoe UI", 11), relief="flat",
                              bd=0, width=28)
        name_entry.pack(side="left", padx=(0, 12), ipady=6)

        # Schedule quick-set
        self._mb_sched_type = tk.StringVar(
            value=existing.get("schedule_type","manual") if existing else "manual")
        self._mb_sched_val  = tk.StringVar(
            value=existing.get("schedule_value","") if existing else "")
        self._mb_sched_time = tk.StringVar(
            value=existing.get("schedule_time","09:00") if existing else "09:00")
        sched_cb = _ck.Combobox(
            top, textvariable=self._mb_sched_type,
            values=["manual", "interval", "daily", "hourly"],
            state="readonly", width=9)
        sched_cb.pack(side="left", padx=(0, 4), pady=14)
        _ck.Entry(top, textvariable=self._mb_sched_val,
                  width=5).pack(side="left", padx=(0, 2), pady=14)
        _lbl(top, "min / time:", text_color=MUT, fg_color=SIDE,
             font=("Segoe UI", 8)).pack(side="left")
        _ck.Entry(top, textvariable=self._mb_sched_time,
                  width=7).pack(side="left", padx=(2, 8), pady=14)

        _ck.Button(top, text="Save Macro", fg_color=GRN, text_color=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=14, pady=7, cursor="hand2",
                  command=self._mb_save).pack(side="right", padx=12, pady=8)
        _ck.Button(top, text="Test Run", fg_color=YEL, text_color=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=14, pady=7, cursor="hand2",
                  command=self._mb_dry_run).pack(side="right", padx=(0, 2), pady=8)

        # -- Body: left panel + right panel --
        body = _ck.Frame(f, fg_color=BG)
        body.pack(fill="both", expand=True)

        # Left panel - step list (270px)
        left_outer = _ck.Frame(body, fg_color=SIDE, width=270)
        left_outer.pack(side="left", fill="y")
        left_outer.pack_propagate(False)

        _lbl(left_outer, "STEPS", text_color=MUT, fg_color=SIDE,
             font=("Segoe UI", 8, "bold")).pack(
            anchor="w", padx=12, pady=(10, 4))

        # Scrollable step list
        list_canvas = tk.Canvas(left_outer, bg=SIDE,
                                highlightthickness=0)
        list_sb = _ck.Scrollbar(left_outer, orient="vertical",
                                command=list_canvas.yview)
        list_sb.pack(side="right", fill="y")
        list_canvas.pack(side="left", fill="both", expand=True)
        list_canvas.configure(yscrollcommand=list_sb.set)

        self._mb_list_inner = _ck.Frame(list_canvas, fg_color=SIDE)
        list_canvas.create_window((0, 0), window=self._mb_list_inner,
                                  anchor="nw", tags="inner")

        def _on_resize(e):
            list_canvas.configure(scrollregion=list_canvas.bbox("all"))
            list_canvas.itemconfig("inner", width=e.width)
        list_canvas.bind("<Configure>", _on_resize)
        self._mb_list_inner.bind(
            "<Configure>",
            lambda e: list_canvas.configure(
                scrollregion=list_canvas.bbox("all")))

        # Add Step button at bottom
        add_btn_frame = _ck.Frame(left_outer, fg_color=SIDE, pady=6)
        add_btn_frame.pack(fill="x", side="bottom")
        _ck.Button(add_btn_frame, text="+ Add Step", fg_color=ACC, text_color=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                  command=lambda: self._mb_add_step()).pack(fill="x",
                                                             padx=10)

        # Right panel - step editor
        right_outer = _ck.Frame(body, fg_color=BG)
        right_outer.pack(side="left", fill="both", expand=True)

        self._mb_editor_frame = _ck.Frame(right_outer, fg_color=BG)
        self._mb_editor_frame.pack(fill="both", expand=True)

        # Render steps or templates
        self._mb_refresh_list()
        if not self._mb_steps:
            self._mb_show_templates()
        else:
            self._mb_select_step(0)

    def _mb_refresh_list(self):
        """Redraw step list in left panel."""
        if not self._mb_list_inner:
            return
        for w in self._mb_list_inner.winfo_children():
            w.destroy()
        self._mb_step_rows = []

        for i, step in enumerate(self._mb_steps):
            icon = _STEP_ICONS.get(step.get("type",""), "[?]")
            desc = _step_label(step)[:32]
            is_sel = (i == self._mb_selected)

            bg_row = ACC if is_sel else SIDE
            fg_row = BG if is_sel else FG

            row = _ck.Frame(self._mb_list_inner, fg_color=bg_row,
                           cursor="hand2")
            row.pack(fill="x", padx=4, pady=1)

            _ck.Label(row, text="{:2}.".format(i + 1), fg_color=bg_row, text_color=fg_row,
                     font=("Consolas", 9), width=3, anchor="e").pack(
                side="left", padx=(4, 2))
            _ck.Label(row, text=icon, fg_color=bg_row, text_color=YEL if is_sel else YEL,
                     font=("Consolas", 9), width=4).pack(side="left")
            _ck.Label(row, text=desc, fg_color=bg_row, text_color=fg_row,
                     font=("Segoe UI", 9), anchor="w").pack(
                side="left", fill="x", expand=True, padx=(0, 4))

            # Test button
            def _make_test(idx=i):
                def _do():
                    self._mb_test_single_step(idx)
                return _do
            _ck.Button(row, text="Test", fg_color=YEL, text_color=BG,
                      font=("Segoe UI", 7, "bold"), relief="flat", bd=0,
                      padx=4, cursor="hand2",
                      command=_make_test()).pack(side="right", padx=1, pady=3)

            # Delete button
            def _make_del(idx=i):
                def _do():
                    self._mb_delete_step(idx)
                return _do
            _ck.Button(row, text="x", fg_color=bg_row, text_color=RED if not is_sel else BG,
                      font=("Segoe UI", 8), relief="flat", bd=0,
                      padx=4, cursor="hand2",
                      command=_make_del()).pack(side="right", padx=2, pady=3)

            # Up/down
            def _make_up(idx=i):
                def _do():
                    if idx > 0:
                        self._mb_steps[idx-1], self._mb_steps[idx] = \
                            self._mb_steps[idx], self._mb_steps[idx-1]
                        self._mb_selected = idx - 1
                        self._mb_refresh_list()
                        self._mb_select_step(idx - 1, rebuild=False)
                return _do
            def _make_dn(idx=i):
                def _do():
                    if idx < len(self._mb_steps) - 1:
                        self._mb_steps[idx+1], self._mb_steps[idx] = \
                            self._mb_steps[idx], self._mb_steps[idx+1]
                        self._mb_selected = idx + 1
                        self._mb_refresh_list()
                        self._mb_select_step(idx + 1, rebuild=False)
                return _do
            _ck.Button(row, text="^", fg_color=bg_row, text_color=MUT if not is_sel else BG,
                      font=("Segoe UI", 7), relief="flat", bd=0, padx=3,
                      cursor="hand2",
                      command=_make_up()).pack(side="right", pady=3)
            _ck.Button(row, text="v", fg_color=bg_row, text_color=MUT if not is_sel else BG,
                      font=("Segoe UI", 7), relief="flat", bd=0, padx=3,
                      cursor="hand2",
                      command=_make_dn()).pack(side="right", pady=3)

            def _make_sel(idx=i):
                def _do():
                    self._mb_select_step(idx)
                return _do
            row.bind("<Button-1>", lambda e, s=_make_sel(): s())
            for child in row.winfo_children():
                if child.cget("cursor") != "hand2":
                    child.bind("<Button-1>", lambda e, s=_make_sel(): s())

            self._mb_step_rows.append(row)

    def _mb_select_step(self, idx, rebuild=True):
        """Select a step and show its editor on the right."""
        if idx < 0 or idx >= len(self._mb_steps):
            return
        self._mb_selected = idx
        if rebuild:
            self._mb_refresh_list()
        step = self._mb_steps[idx]
        self._mb_build_editor(step.get("type","go_to_url"),
                              existing=step, step_idx=idx)

    def _mb_delete_step(self, idx):
        if 0 <= idx < len(self._mb_steps):
            del self._mb_steps[idx]
            if self._mb_selected >= len(self._mb_steps):
                self._mb_selected = len(self._mb_steps) - 1
            self._mb_refresh_list()
            if self._mb_steps:
                self._mb_select_step(
                    max(0, self._mb_selected), rebuild=False)
            else:
                self._mb_show_templates()

    def _mb_add_step(self, step_type="go_to_url", after_idx=None):
        """Add a new empty step and select it for editing."""
        new_step = {"type": step_type}
        if after_idx is not None and 0 <= after_idx < len(self._mb_steps):
            self._mb_steps.insert(after_idx + 1, new_step)
            self._mb_selected = after_idx + 1
        else:
            self._mb_steps.append(new_step)
            self._mb_selected = len(self._mb_steps) - 1
        self._mb_refresh_list()
        self._mb_select_step(self._mb_selected, rebuild=False)

    def _mb_show_templates(self):
        """Show 4 template cards in the right panel (empty state)."""
        for w in self._mb_editor_frame.winfo_children():
            w.destroy()

        _lbl(self._mb_editor_frame,
             "Choose a template to get started quickly:", text_color=MUT, fg_color=BG, font=("Segoe UI", 10)).pack(
            anchor="w", padx=24, pady=(20, 12))

        templates = _load_templates()
        row1 = _ck.Frame(self._mb_editor_frame, fg_color=BG)
        row1.pack(fill="x", padx=20, pady=(0, 8))
        row2 = _ck.Frame(self._mb_editor_frame, fg_color=BG)
        row2.pack(fill="x", padx=20)

        tmpl_icons = ["->", "[?]", "[~]", "<-T"]
        tmpl_clrs  = [ACC, GRN, YEL, PRP]

        for i, tmpl in enumerate(templates[:4]):
            parent_row = row1 if i < 2 else row2
            clr = tmpl_clrs[i % len(tmpl_clrs)]
            ic  = tmpl_icons[i % len(tmpl_icons)]

            def _use_tmpl(t=tmpl):
                self._mb_steps = list(t.get("steps", []))
                if not self._mb_name_var.get():
                    self._mb_name_var.set(t["name"])
                self._mb_refresh_list()
                if self._mb_steps:
                    self._mb_select_step(0)

            tc = _ck.Frame(parent_row, fg_color=CARD, padx=16, pady=14,
                          cursor="hand2")
            tc.pack(side="left", fill="both", expand=True, padx=(0, 8))

            hrow = _ck.Frame(tc, fg_color=CARD)
            hrow.pack(fill="x", pady=(0, 6))
            _ck.Label(hrow, text=ic, fg_color=CARD, text_color=clr,
                     font=("Consolas", 14, "bold")).pack(side="left",
                                                          padx=(0, 10))
            _lbl(hrow, tmpl["name"], text_color=clr, fg_color=CARD,
                 font=("Segoe UI", 10, "bold")).pack(side="left")

            _lbl(tc, tmpl.get("description",""), text_color=MUT, fg_color=CARD,
                 font=("Segoe UI", 8), wraplength=220,
                 justify="left").pack(anchor="w", pady=(0, 8))

            steps = tmpl.get("steps", [])
            for s in steps[:4]:
                step_ic = _STEP_ICONS.get(s.get("type",""), "[?]")
                _lbl(tc, "{}  {}".format(step_ic, _step_label(s)[:28]), text_color=MUT, fg_color=CARD,
                     font=("Consolas", 8)).pack(anchor="w")
            if len(steps) > 4:
                _lbl(tc, "  ... +{} more steps".format(len(steps)-4), text_color=MUT, fg_color=CARD, font=("Segoe UI", 8)).pack(anchor="w")

            _ck.Button(tc, text="Use This Template", fg_color=clr, text_color=BG,
                      font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                      padx=10, pady=5, cursor="hand2",
                      command=_use_tmpl).pack(anchor="w", pady=(10, 0))

        # OR start blank
        blank = _ck.Frame(self._mb_editor_frame, fg_color=CARD, padx=16,
                         pady=14, cursor="hand2")
        blank.pack(fill="x", padx=20, pady=(12, 0))
        brow = _ck.Frame(blank, fg_color=CARD)
        brow.pack(fill="x", pady=(0, 6))
        _ck.Label(brow, text="[+]", fg_color=CARD, text_color=FG,
                 font=("Consolas", 14, "bold")).pack(side="left",
                                                      padx=(0, 10))
        _lbl(brow, "Start from scratch", text_color=FG, fg_color=CARD,
             font=("Segoe UI", 10, "bold")).pack(side="left")
        _lbl(blank, "Build your own macro step by step with any combination "
             "of actions.", text_color=MUT, fg_color=CARD, font=("Segoe UI", 8),
             wraplength=400, justify="left").pack(anchor="w", pady=(0, 8))
        _ck.Button(blank, text="+ Add First Step", fg_color=FG, text_color=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                  command=self._mb_add_step).pack(anchor="w")

    def _mb_build_editor(self, step_type, existing=None, step_idx=None):
        """Build the step editor in the right panel."""
        for w in self._mb_editor_frame.winfo_children():
            w.destroy()
        self._mb_field_vars = {}
        self._mb_type_var   = tk.StringVar(value=step_type)

        # -- Step type selector --
        type_frame = _ck.Frame(self._mb_editor_frame, fg_color=BG)
        type_frame.pack(fill="x", padx=20, pady=(16, 8))
        _lbl(type_frame, "Step Type:", text_color=MUT, fg_color=BG,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 4))

        TYPE_OPTIONS = [
            ("go_to_url",        "Go to URL"),
            ("click",            "Click Element"),
            ("type",             "Type Text"),
            ("get_text",         "Get Value (text)"),
            ("get_number",       "Get Value (number)"),
            ("wait",             "Wait"),
            ("sheet_read_cell",  "Read Sheet"),
            ("sheet_write_cell", "Write Sheet"),
            ("if_equals",        "If Condition"),
            ("if_contains",      "If Contains"),
            ("notify",           "Notify"),
            ("ai_prompt",        "🤖 AI Prompt"),
            ("scrape_url",       "🌐 Scrape URL"),
        ]
        display_names = [d for _, d in TYPE_OPTIONS]
        type_to_key   = {d: k for k, d in TYPE_OPTIONS}
        key_to_disp   = {k: d for k, d in TYPE_OPTIONS}

        curr_disp = key_to_disp.get(step_type, display_names[0])
        disp_var  = tk.StringVar(value=curr_disp)

        type_cb = _ck.Combobox(type_frame, textvariable=disp_var,
                               values=display_names, state="readonly",
                               width=28, font=("Segoe UI", 10))
        type_cb.pack(anchor="w")

        # -- Fields area --
        fields_outer = _ck.Frame(self._mb_editor_frame, fg_color=BG)
        fields_outer.pack(fill="both", expand=True, padx=20, pady=(4, 0))

        # Scroll for fields
        fc = tk.Canvas(fields_outer, bg=BG, highlightthickness=0)
        fsb = _ck.Scrollbar(fields_outer, orient="vertical",
                            command=fc.yview)
        fsb.pack(side="right", fill="y")
        fc.pack(side="left", fill="both", expand=True)
        fc.configure(yscrollcommand=fsb.set)
        fields_inner = _ck.Frame(fc, fg_color=BG)
        fc.create_window((0, 0), window=fields_inner, anchor="nw",
                         tags="fi")

        def _fc_resize(e):
            fc.configure(scrollregion=fc.bbox("all"))
            fc.itemconfig("fi", width=e.width)
        fc.bind("<Configure>", _fc_resize)
        fields_inner.bind(
            "<Configure>",
            lambda e: fc.configure(scrollregion=fc.bbox("all")))

        def _rebuild_fields(*_):
            for w in fields_inner.winfo_children():
                w.destroy()
            self._mb_field_vars = {}
            stype = type_to_key.get(disp_var.get(), "go_to_url")
            self._mb_type_var.set(stype)
            # Update actual step type if we have a step index
            if step_idx is not None and 0 <= step_idx < len(self._mb_steps):
                self._mb_steps[step_idx]["type"] = stype
            self._mb_build_fields(fields_inner, stype, existing or {})
            # Add/Update button
            self._mb_build_editor_actions(fields_inner, step_idx)

        type_cb.bind("<<ComboboxSelected>>", _rebuild_fields)
        _rebuild_fields()

    def _mb_build_fields(self, parent, step_type, existing):
        """Build dynamic fields for a given step type."""
        def _field(label, key, default="", helper="",
                   multiline=False, height=3):
            f = _ck.Frame(parent, fg_color=BG)
            f.pack(fill="x", pady=(0, 10))
            _lbl(f, label, text_color=FG, fg_color=BG,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 2))
            val = tk.StringVar(value=existing.get(key, default))
            if multiline:
                txt = _ck.Text(f, fg_color=CARD, text_color=FG, insertbackground=FG,
                              font=("Segoe UI", 10), relief="flat",
                              height=height, wrap="word")
                txt.insert("1.0", existing.get(key, default))
                txt.pack(fill="x")
                self._mb_field_vars[key] = txt
            else:
                entry = _ck.Entry(f, textvariable=val, fg_color=CARD, text_color=FG,
                                 insertbackground=FG, font=("Segoe UI", 10),
                                 relief="flat")
                entry.pack(fill="x", ipady=6)
                self._mb_field_vars[key] = val
            if helper:
                _lbl(f, helper, text_color=MUT, fg_color=BG,
                     font=("Segoe UI", 8)).pack(anchor="w")
            return val

        def _spy_button(selector_key):
            """Add a 'USE SPY TO PICK' button that fills selector_key."""
            row = _ck.Frame(parent, fg_color=BG)
            row.pack(fill="x", pady=(0, 10))

            def _do_spy_pick():
                target_var = self._mb_field_vars.get(selector_key)
                if target_var is None:
                    return
                def _on_sel(sel, xpath, text):
                    if isinstance(target_var, tk.StringVar):
                        target_var.set(sel)
                self._spy_selector_callback = _on_sel
                self._open_floating_spy_for_macro(_on_sel)
                self._sv.set(
                    "Spy open. Hover over element, click USE IN MACRO.")

            _ck.Button(row, text="USE SPY TO PICK", fg_color=PRP, text_color=BG, font=("Segoe UI", 9, "bold"),
                      relief="flat", bd=0, padx=12, pady=6,
                      cursor="hand2", command=_do_spy_pick).pack(
                side="left")
            _lbl(row, "Hover over element in Chrome, click USE IN MACRO", text_color=MUT, fg_color=BG, font=("Segoe UI", 8)).pack(
                side="left", padx=8)

        # -- Per step type fields --
        if step_type == "go_to_url":
            _field("Website URL", "url", "https://",
                   helper="Tip: Copy the exact URL from your browser address bar")
            row = _ck.Frame(parent, fg_color=BG)
            row.pack(fill="x", pady=(0, 10))
            def _open_test():
                import webbrowser as _wb
                url_var = self._mb_field_vars.get("url")
                if url_var and isinstance(url_var, tk.StringVar):
                    u = url_var.get().strip()
                    if u:
                        if not u.startswith(("http://", "https://")):
                            u = "https://" + u
                        _wb.open(u)
            _ck.Button(row, text="Open in Browser", fg_color=CARD, text_color=FG, font=("Segoe UI", 9),
                      relief="flat", bd=0, padx=10, pady=5,
                      cursor="hand2", command=_open_test).pack(side="left")

        elif step_type == "click":
            _field("CSS Selector", "selector", "",
                   helper="Example: button#submit, .confirm-btn")
            _spy_button("selector")
            prev_var = self._mb_field_vars.get("selector")
            if prev_var and isinstance(prev_var, tk.StringVar):
                def _upd_prev(*_):
                    pass  # label updated dynamically
                prev_var.trace_add("write", _upd_prev)
            _lbl(parent, "Will click: [selector shown above]", text_color=MUT, fg_color=BG, font=("Segoe UI", 8)).pack(anchor="w",
                                                             pady=(0, 8))

        elif step_type == "type":
            _field("Where to type (CSS Selector)", "selector", "",
                   helper="Click field in Chrome, then use Spy to get selector")
            _spy_button("selector")
            _field("What to type", "text", "",
                   helper="Tip: Use {variable_name} to insert values from previous steps")

        elif step_type in ("get_text", "get_number"):
            label = ("Get text value" if step_type == "get_text"
                     else "Get number value")
            _field(label + " - CSS Selector", "selector", "",
                   helper="The element containing the value you want to read")
            _spy_button("selector")
            _field("Save as variable name", "var", "",
                   helper='Example: price, stock_amount, order_status  ->  Use as {price}')

        elif step_type == "wait":
            _field("Wait seconds", "seconds", "2",
                   helper="How many seconds to pause before the next step")

        elif step_type == "wait_for_element":
            _field("CSS Selector", "selector", "",
                   helper="Wait until this element appears on the page")
            _spy_button("selector")
            _field("Timeout (seconds)", "timeout", "10")

        elif step_type == "sheet_read_cell":
            sheets = [s.get("name","") for s in self._ud.sheets]
            _field("Sheet Name", "sheet",
                   existing.get("sheet", sheets[0] if sheets else "Sheet1"),
                   helper="The Google Sheet name as shown in your connected sheets")
            _field("Cell address", "cell", "A1",
                   helper="Examples: B2, Sheet1!C5, D{row}")
            _field("Save as variable", "var", "",
                   helper='This value becomes available as {variable_name} in later steps')

        elif step_type == "sheet_write_cell":
            sheets = [s.get("name","") for s in self._ud.sheets]
            _field("Sheet Name", "sheet",
                   existing.get("sheet", sheets[0] if sheets else "Sheet1"),
                   helper="The Google Sheet name as shown in your connected sheets")
            _field("Cell address", "cell", "A1",
                   helper="Examples: B2, Sheet1!C5, D{row}")
            _field("Value to write", "value", "",
                   helper="Supports {variables} and {current_time} {current_date}")
            _lbl(parent, 'Example: Write {price} to cell B2', text_color=MUT, fg_color=BG, font=("Segoe UI", 8)).pack(
                anchor="w", pady=(0, 8))

        elif step_type == "if_equals":
            _field("Variable or value", "value1", "",
                   helper='Use {variable_name} or literal text')
            _field("Equals what?", "value2", "",
                   helper="Leave empty to check if variable is blank")
            f_cond = _ck.Frame(parent, fg_color=BG)
            f_cond.pack(fill="x", pady=(0, 10))
            _lbl(f_cond, "If FALSE, then:", text_color=MUT, fg_color=BG,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))
            act_var = tk.StringVar(
                value=existing.get("action_false", "stop"))
            self._mb_field_vars["action_false"] = act_var
            for val, label in [("stop", "Stop macro"),
                                ("skip", "Skip next step"),
                                ("continue", "Continue anyway")]:
                _ck.Radiobutton(f_cond, text=label, variable=act_var,
                               value=val, fg_color=BG, text_color=FG,
                               selectcolor=CARD, activebackground=BG,
                               activeforeground=ACC,
                               font=("Segoe UI", 9)).pack(anchor="w")

        elif step_type == "if_contains":
            _field("Text or variable", "text", "",
                   helper='Use {variable_name} to check a captured value')
            _field("Contains what?", "keyword", "",
                   helper='Example: Habis, Out of Stock, Error')
            f_true = _ck.Frame(parent, fg_color=BG)
            f_true.pack(fill="x", pady=(0, 6))
            _lbl(f_true, "If TRUE, then:", text_color=MUT, fg_color=BG,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))
            act_true = tk.StringVar(
                value=existing.get("action_true", "notify"))
            self._mb_field_vars["action_true"] = act_true
            for val, lbl in [("notify", "Send notification"),
                              ("skip",   "Skip next step"),
                              ("stop",   "Stop macro")]:
                _ck.Radiobutton(f_true, text=lbl, variable=act_true,
                               value=val, fg_color=BG, text_color=FG, selectcolor=CARD,
                               activebackground=BG, activeforeground=ACC,
                               font=("Segoe UI", 9)).pack(anchor="w")
            _field("Notification message", "notify_message", "",
                   helper="Shown when condition is true. Supports {variables}")

        elif step_type == "notify":
            _field("Message", "message", "",
                   helper="Supports {variables}. Example: Price updated: {price}")
            f_type = _ck.Frame(parent, fg_color=BG)
            f_type.pack(fill="x", pady=(0, 10))
            _lbl(f_type, "Notification type:", text_color=MUT, fg_color=BG,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))
            ntype = tk.StringVar(value=existing.get("notify_type", "popup"))
            self._mb_field_vars["notify_type"] = ntype
            for val, lbl in [("popup", "Popup message"),
                              ("sound", "Sound only"),
                              ("both",  "Popup + Sound")]:
                _ck.Radiobutton(f_type, text=lbl, variable=ntype,
                               value=val, fg_color=BG, text_color=FG, selectcolor=CARD,
                               activebackground=BG, activeforeground=ACC,
                               font=("Segoe UI", 9)).pack(anchor="w")

        elif step_type == "ai_prompt":
            # Info strip
            _ai_cfg_prov = self.config.get("ai.provider", "openai")
            _ai_cfg_model = self.config.get("ai.model", "") or "default"
            _ai_has_key = bool(self.config.get("ai.api_key", "").strip())
            info_fr = _ck.Frame(parent, fg_color="#0A1A0A" if _ai_has_key else "#1A0A0A",
                               padx=10, pady=6)
            info_fr.pack(fill="x", pady=(0, 10))
            status_txt = ("✓ AI dikonfigurasi: {} ({})".format(
                _ai_cfg_prov.upper(), _ai_cfg_model)
                if _ai_has_key else
                "⚠ API key belum diset. Buka Settings → AI Integration dulu.")
            _ck.Label(info_fr, text=status_txt, fg_color=info_fr["bg"], text_color=GRN if _ai_has_key else YEL,
                     font=("Segoe UI", 8)).pack(anchor="w")

            # Prompt (user message)
            _field("Prompt untuk AI", "prompt", existing.get("prompt", ""),
                   multiline=True, height=4,
                   helper="Dukung {variabel} dari step sebelumnya. "
                          "Contoh: Ringkas teks ini: {page_text}")

            # System prompt override (optional)
            f_sys = _ck.Frame(parent, fg_color=BG)
            f_sys.pack(fill="x", pady=(0, 10))
            _lbl(f_sys, "System Prompt (opsional — override default):", text_color=MUT, fg_color=BG, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))
            sys_txt_w = _ck.Text(f_sys, fg_color=CARD, text_color=FG, insertbackground=FG,
                                font=("Segoe UI", 9), relief="flat",
                                height=2, wrap="word")
            sys_txt_w.insert("1.0", existing.get("system", ""))
            sys_txt_w.pack(fill="x")
            self._mb_field_vars["system"] = sys_txt_w

            # Save-as variable + max tokens row
            sv_row = _ck.Frame(parent, fg_color=BG)
            sv_row.pack(fill="x", pady=(0, 10))
            _lbl(sv_row, "Simpan hasil sebagai:", text_color=MUT, fg_color=BG,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
            sv_var = tk.StringVar(value=existing.get("var", "ai_result"))
            sv_entry = _ck.Entry(sv_row, textvariable=sv_var, fg_color=CARD, text_color=FG,
                                insertbackground=FG, relief="flat",
                                font=("Segoe UI", 9), width=16)
            sv_entry.pack(side="left")
            self._mb_field_vars["var"] = sv_var
            _lbl(sv_row, "  Max tokens:", text_color=MUT, fg_color=BG,
                 font=("Segoe UI", 9)).pack(side="left", padx=(12, 4))
            mt_var = tk.StringVar(value=str(existing.get("max_tokens",
                                            self.config.get("ai.max_tokens", 800))))
            _ck.Entry(sv_row, textvariable=mt_var, fg_color=CARD, text_color=FG,
                     insertbackground=FG, relief="flat",
                     font=("Segoe UI", 9), width=6).pack(side="left")
            self._mb_field_vars["max_tokens"] = mt_var

            _lbl(parent,
                 "Hasil AI tersimpan di {ai_result} (atau nama variabel di atas) "
                 "dan bisa dipakai di step berikutnya.", text_color=MUT, fg_color=BG, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 8))

        elif step_type == "scrape_url":
            info_fr = _ck.Frame(parent, fg_color="#0A100A", padx=10, pady=6)
            info_fr.pack(fill="x", pady=(0, 10))
            _ck.Label(info_fr,
                     text="Ambil teks dari halaman web — tidak butuh browser/Playwright.", fg_color="#0A100A", text_color=GRN,
                     font=("Segoe UI", 8)).pack(anchor="w")

            _field("URL halaman", "url", existing.get("url", "https://"),
                   helper="Dukung {variabel} dari step sebelumnya")

            _field("Filter keyword (opsional)", "keyword",
                   existing.get("keyword", ""),
                   helper="Jika diisi, hanya ambil baris yang mengandung kata ini. "
                          "Contoh: harga, stok, price")

            sv_row = _ck.Frame(parent, fg_color=BG)
            sv_row.pack(fill="x", pady=(0, 10))
            _lbl(sv_row, "Simpan sebagai variabel:", text_color=MUT, fg_color=BG,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
            sv_var = tk.StringVar(value=existing.get("var", "scraped_text"))
            _ck.Entry(sv_row, textvariable=sv_var, fg_color=CARD, text_color=FG,
                     insertbackground=FG, relief="flat",
                     font=("Segoe UI", 9), width=18).pack(side="left")
            self._mb_field_vars["var"] = sv_var

            _lbl(parent,
                 "Hasil tersimpan di {scraped_text} — bisa dipakai di step AI Prompt, "
                 "Write Sheet, atau If Contains berikutnya.", text_color=MUT, fg_color=BG, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 8))

        else:
            _field("Value / Selector", "value", existing.get("value",""))

    def _mb_build_editor_actions(self, parent, step_idx):
        """Add Apply / Insert Below buttons at bottom of editor."""
        row = _ck.Frame(parent, fg_color=BG)
        row.pack(fill="x", pady=(16, 0))

        def _apply():
            if step_idx is None or step_idx >= len(self._mb_steps):
                return
            step = dict(type=self._mb_type_var.get()
                        if self._mb_type_var else "go_to_url")
            for key, var in self._mb_field_vars.items():
                if isinstance(var, tk.StringVar):
                    step[key] = var.get()
                elif isinstance(var, tk.Text):
                    step[key] = var.get("1.0", "end").strip()
            self._mb_steps[step_idx] = step
            self._mb_refresh_list()
            self._sv.set("Step {} updated.".format(step_idx + 1))

        def _insert_below():
            _apply()
            self._mb_add_step(after_idx=step_idx)

        _ck.Button(row, text="Apply Changes", fg_color=GRN, text_color=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=14, pady=7, cursor="hand2",
                  command=_apply).pack(side="left", padx=(0, 8))
        _ck.Button(row, text="+ Insert Step Below", fg_color=CARD, text_color=FG, font=("Segoe UI", 9),
                  relief="flat", bd=0, padx=10, pady=7, cursor="hand2",
                  command=_insert_below).pack(side="left")

    def _mb_save(self):
        """Save macro and return to list."""
        name = self._mb_name_var.get().strip() if self._mb_name_var else ""
        if not name:
            self._show_alert("Macro Name", "Please enter a macro name.", "warning")
            return
        stype = self._mb_sched_type.get() if self._mb_sched_type else "manual"
        sval  = self._mb_sched_val.get()  if self._mb_sched_val  else ""
        stime = self._mb_sched_time.get() if self._mb_sched_time else "09:00"

        task_data = {
            "id":             str(time.time()),
            "name":           name,
            "description":    "",
            "steps":          list(self._mb_steps),
            "schedule_type":  stype,
            "schedule_value": sval,
            "schedule_time":  stime,
            "enabled":        True,
            "last_run":       "-",
            "last_status":    "-",
        }
        with self._ud_lock:
            if (self._mb_edit_idx is not None and
                    0 <= self._mb_edit_idx < len(self._ud.tasks)):
                self._ud.tasks[self._mb_edit_idx] = task_data
            else:
                self._ud.tasks.append(task_data)

        self._ud.save()
        if self.engine:
            self.engine.register_task(task_data)
        self._mb_back()
        self._sv.set("Macro '{}' saved ({} steps).".format(
            name, len(self._mb_steps)))

    # ================================================================
    #  DRY RUN / STEP TESTER
    # ================================================================

    def _mb_dry_run(self):
        """Run the current macro in dry-run mode with per-step confirmation."""
        if not self._mb_steps:
            self._show_alert("Test Run", "No steps to run.")
            return
        if not self.engine:
            self._show_alert("Test Run",
                             "Engine not connected. Browser/Sheets "
                             "steps will fail, but logic steps will work.",
                             "warning")

        task = {"name": self._mb_name_var.get() or "Dry Run",
                "steps": list(self._mb_steps)}
        stop_ev = threading.Event()

        # -- Dry run panel (extends progress panel) --
        panel = self._show_run_progress_panel(task, stop_ev)
        w = panel["window"]
        w.title("Dry Run: {}".format(task["name"]))

        # Extra info banner
        info = _ck.Label(w, text="DRY RUN  -  Sheet writes are simulated", fg_color=YEL, text_color=BG, font=("Segoe UI", 9, "bold"),
                        padx=10, pady=4)
        info.pack(fill="x", before=panel["step_lbl"])

        # Per-step confirm controls
        ctrl = _ck.Frame(w, fg_color=BG)
        ctrl.pack(fill="x", padx=16, pady=(0, 4))
        confirm_var = tk.StringVar(value="waiting")

        next_btn = _ck.Button(ctrl, text="Execute Step", fg_color=GRN, text_color=BG,
                             font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                             padx=10, pady=4, cursor="hand2",
                             command=lambda: confirm_var.set("yes"),
                             state="disabled")
        next_btn.pack(side="left", padx=(0, 6))
        skip_btn = _ck.Button(ctrl, text="Skip", fg_color=CARD, text_color=FG,
                             font=("Segoe UI", 9), relief="flat", bd=0,
                             padx=10, pady=4, cursor="hand2",
                             command=lambda: confirm_var.set("skip"),
                             state="disabled")
        skip_btn.pack(side="left")

        confirm_event = threading.Event()
        confirm_result = [None]

        def _enable_confirm():
            next_btn.configure(state="normal")
            skip_btn.configure(state="normal")

        def _disable_confirm():
            next_btn.configure(state="disabled")
            skip_btn.configure(state="disabled")

        def _watch_confirm():
            val = confirm_var.get()
            if val in ("yes", "skip"):
                confirm_result[0] = val
                confirm_var.set("waiting")
                _disable_confirm()
                confirm_event.set()
            else:
                w.after(100, _watch_confirm)

        def _dry_run_thread():
            import queue as _queue

            def _ui(fn):
                """Schedule fn on main thread; no-op if root already destroyed."""
                root = getattr(self, "_root", None)
                if root:
                    try:
                        root.after(0, fn)
                    except Exception:
                        pass

            variables = {
                "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "current_date": datetime.now().strftime("%Y-%m-%d"),
            }
            ok_count = 0

            from modules.macro.smart_macro import SmartMacro
            macro = SmartMacro(
                engine=self.engine if self.engine else None,
                notify_callback=None)

            for i, step in enumerate(self._mb_steps):
                if stop_ev.is_set():
                    break

                step_type = step.get("type", "")
                step_desc = _step_label(step)

                # Highlight current step in list
                _ui(lambda idx=i: self._mb_highlight_step(idx))

                # Update panel label and wait for confirm
                lbl = "Step {}/{}: {}  -  OK to execute?".format(
                    i + 1, len(self._mb_steps), step_desc[:40])
                _ui(lambda t=lbl: panel["step_lbl"].configure(text=t))
                _ui(_enable_confirm)
                _ui(_watch_confirm)

                confirm_event.clear()
                confirm_event.wait()

                if confirm_result[0] == "skip":
                    msg = "Step {}: [SKIPPED]\n".format(i + 1)
                    _ui(lambda m=msg: [
                        panel["log_box"].configure(state="normal"),
                        panel["log_box"].insert(tk.END, m, "info"),
                        panel["log_box"].see(tk.END),
                        panel["log_box"].configure(state="disabled"),
                    ])
                    continue

                # Execute step (dry_run mode for writes)
                result = macro.run_single_step(step, variables)
                ok = result["ok"]
                if ok:
                    ok_count += 1
                tag = "ok" if ok else "fail"
                msg = "Step {}: {}\n".format(i + 1, result["result"])
                _ui(lambda m=msg, t=tag: [
                    panel["log_box"].configure(state="normal"),
                    panel["log_box"].insert(tk.END, m, t),
                    panel["log_box"].see(tk.END),
                    panel["log_box"].configure(state="disabled"),
                ])
                _ui(lambda v=i + 1: panel["progress_var"].set(v))

                # Auto-screenshot after each step
                if self.engine and hasattr(self.engine, "browser") and self.engine.browser:
                    try:
                        macro.take_screenshot("dryrun_step_{}.png".format(i + 1))
                    except Exception:
                        pass

            total_steps = len(self._mb_steps)
            fail_count = total_steps - ok_count
            summary = "Dry run done: {} succeeded, {} failed/skipped.".format(
                ok_count, total_steps - ok_count)
            _ui(lambda s=summary: [
                panel["step_lbl"].configure(text=s),
                self._toast_success(s) if fail_count == 0 else self._toast_warning(s),
                self._mb_highlight_step(-1),
            ])
            _ui(lambda: panel["stop_btn"].configure(state="disabled", text="Done"))

        threading.Thread(target=_dry_run_thread, daemon=True).start()

    def _mb_highlight_step(self, idx: int):
        """Highlight the given step row in the step list (for dry run tracking)."""
        if not hasattr(self, "_mb_step_rows"):
            return
        for i, row in enumerate(self._mb_step_rows):
            try:
                is_active = (i == idx)
                bg = YEL if is_active else (ACC if i == self._mb_selected else SIDE)
                fg = BG if is_active else (BG if i == self._mb_selected else FG)
                row.configure(fg_color=bg)
                for child in row.winfo_children():
                    try:
                        child.configure(fg_color=bg)
                    except Exception:
                        pass
            except Exception:
                pass

    def _mb_test_single_step(self, step_idx: int):
        """Run a single step and show the result in a small popup."""
        if step_idx < 0 or step_idx >= len(self._mb_steps):
            return
        step = self._mb_steps[step_idx]

        # Show result window
        w = ctk.CTkToplevel(self._root)
        w.withdraw()
        w.title("Step Test: {}".format(_step_label(step)[:40]))
        w.configure(fg_color=BG)
        w.geometry("400x180")
        w.attributes("-topmost", True)
        w.resizable(False, False)

        _ck.Label(w, text="Testing: {}".format(_step_label(step)[:50]), fg_color=BG, text_color=FG, font=("Segoe UI", 10, "bold"),
                 padx=16, pady=10, anchor="w").pack(fill="x")
        status_lbl = _ck.Label(w, text="Running...", fg_color=BG, text_color=MUT, font=("Segoe UI", 9),
                              padx=16, anchor="w")
        status_lbl.pack(fill="x")
        result_lbl = _ck.Label(w, text="", fg_color=CARD, text_color=FG, font=("Consolas", 9),
                              padx=12, pady=8, anchor="w", wraplength=370,
                              justify="left")
        result_lbl.pack(fill="x", padx=16, pady=(6, 0))
        _ck.Button(w, text="Close", command=w.destroy).pack(pady=10)
        w.update()
        w.deiconify()

        def _run():
            from modules.macro.smart_macro import SmartMacro
            macro = SmartMacro(
                engine=self.engine if self.engine else None)
            res = macro.run_single_step(step)
            ok = res["ok"]
            result_text = res["result"]

            def _show():
                try:
                    status_lbl.configure(
                        text="OK" if ok else "FAILED", text_color=GRN if ok else RED,
                        font=("Segoe UI", 10, "bold"))
                    result_lbl.configure(text=result_text)
                except Exception:
                    pass
            self._root.after(0, _show)

        threading.Thread(target=_run, daemon=True).start()

    # ================================================================
    #  SHEET PAGE  (Connected Sheets)
    # ================================================================
    #  QRIS PAGE  (Konversi QRIS Statis → Dinamis)
    # ================================================================

    def _pg_qris(self):
        import threading as _thr
        from io import BytesIO

        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "QRIS Dinamis",
                  "Ubah QRIS statis menjadi QRIS dinamis dengan nominal & biaya layanan")

        # ── Layout utama: kiri (form) | kanan (preview QR) ────────────────
        body = _ck.Frame(f, fg_color=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # Kiri — form input
        left = _ck.Frame(body, fg_color=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 14))

        # Kanan — preview QR
        right = _ck.Frame(body, fg_color=CARD, width=280)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        _ck.Frame(right, fg_color=ACC, height=4).pack(fill="x")

        # ── Preview QR area ───────────────────────────────────────────────
        qr_lbl = _ck.Label(right, text="QR akan muncul di sini",
                           fg_color=CARD, text_color=MUT,
                           font=("Segoe UI", 10), wraplength=220, justify="center")
        qr_lbl.pack(expand=True, pady=30)

        qr_photo_ref = [None]   # simpan referensi agar tidak di-GC

        merchant_lbl = _ck.Label(right, text="", fg_color=CARD, text_color=FG,
                                 font=("Segoe UI", 9, "bold"), wraplength=240, justify="center")
        merchant_lbl.pack(pady=(0, 4))

        city_lbl = _ck.Label(right, text="", fg_color=CARD, text_color=MUT,
                             font=("Segoe UI", 8), wraplength=240, justify="center")
        city_lbl.pack()

        nominal_preview = _ck.Label(right, text="", fg_color=CARD, text_color=GRN,
                                    font=("Segoe UI", 11, "bold"))
        nominal_preview.pack(pady=(4, 0))

        # Tombol Copy & Save di bawah preview
        btn_row_r = _ck.Frame(right, fg_color=CARD)
        btn_row_r.pack(fill="x", padx=16, pady=12)

        qris_result = [None]   # simpan string QRIS hasil konversi

        def _copy_qris():
            if not qris_result[0]:
                return
            self._root.clipboard_clear()
            self._root.clipboard_append(qris_result[0])
            self._sv.set("QRIS string disalin ke clipboard!")

        def _save_qr():
            if not qris_result[0]:
                return
            from tkinter import filedialog as _fd
            from modules.qris.converter import generate_qr_image
            path = _fd.asksaveasfilename(
                parent=self._root, defaultextension=".png",
                filetypes=[("PNG Image", "*.png")],
                initialfile="qris_dinamis.png")
            if not path:
                return
            try:
                img = generate_qr_image(qris_result[0], box_size=8, border=4)
                img.save(path)
                self._sv.set("QR disimpan: {}".format(path))
            except Exception as e:
                self._show_alert("Gagal Simpan", str(e), "error")

        copy_btn = _ck.Button(btn_row_r, text="📋 Salin QRIS", fg_color=ACC, text_color="white",
                              font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                              padx=12, pady=6, cursor="hand2", state="disabled",
                              command=_copy_qris)
        copy_btn.pack(fill="x", pady=(0, 6))

        save_btn = _ck.Button(btn_row_r, text="💾 Simpan Gambar QR", fg_color=CARD2, text_color=FG,
                              font=("Segoe UI", 9), relief="flat", bd=0,
                              padx=12, pady=6, cursor="hand2", state="disabled",
                              command=_save_qr)
        save_btn.pack(fill="x")

        # ── Form kiri ─────────────────────────────────────────────────────
        def _section(title):
            _ck.Label(left, text=title, fg_color=BG, text_color=MUT,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(12, 2))

        # QRIS String input
        _section("STRING QRIS STATIS")
        qris_hint = _ck.Label(left,
            text="Tempel string QRIS dari QR code statis (dimulai dengan 000201...)",
            fg_color=BG, text_color="#4A4A6A", font=("Segoe UI", 8))
        qris_hint.pack(anchor="w", pady=(0, 4))

        qris_input = _ck.Text(left, fg_color=CARD2, text_color=FG,
                              font=("Consolas", 8), height=100, wrap="word")
        qris_input.pack(fill="x")

        # Tombol Paste + Clear
        paste_row = _ck.Frame(left, fg_color=BG)
        paste_row.pack(anchor="e", pady=(4, 0))

        def _paste_qris():
            try:
                txt = self._root.clipboard_get()
                qris_input.delete("1.0", "end")
                qris_input.insert("1.0", txt.strip())
            except Exception:
                pass

        def _clear_form():
            qris_input.delete("1.0", "end")
            nominal_var.set("")
            fee_amt_var.set("")
            status_lbl.configure(text="", text_color=MUT)
            qr_lbl.configure(image="", text="QR akan muncul di sini")
            qr_photo_ref[0] = None
            merchant_lbl.configure(text="")
            city_lbl.configure(text="")
            nominal_preview.configure(text="")
            qris_result[0] = None
            copy_btn.configure(state="disabled")
            save_btn.configure(state="disabled")

        def _upload_qr_image():
            from tkinter import filedialog as _fd
            path = _fd.askopenfilename(
                parent=self._root,
                title="Pilih Gambar QR Code",
                filetypes=[
                    ("Gambar", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                    ("Semua file", "*.*"),
                ])
            if not path:
                return
            try:
                from PIL import Image as _PILImage
                try:
                    from pyzbar.pyzbar import decode as _pyzbar_decode
                except ImportError:
                    _set_status(
                        "⚠ Library pyzbar belum terinstall. "
                        "Jalankan: pip install pyzbar", YEL)
                    return
                img = _PILImage.open(path).convert("RGB")
                decoded = _pyzbar_decode(img)
                if not decoded:
                    _set_status("❌ QR code tidak terdeteksi di gambar ini.", RED)
                    return
                qris_str = decoded[0].data.decode("utf-8", errors="replace").strip()
                qris_input.delete("1.0", "end")
                qris_input.insert("1.0", qris_str)
                _set_status("✅ QR berhasil dibaca dari gambar.", GRN)
            except Exception as _e:
                _set_status("❌ Gagal baca gambar: {}".format(str(_e)[:60]), RED)

        _ck.Button(paste_row, text="📋 Paste", fg_color=CARD2, text_color=FG,
                   font=("Segoe UI", 8), relief="flat", bd=0,
                   padx=10, pady=4, cursor="hand2",
                   command=_paste_qris).pack(side="left", padx=(0, 6))
        _ck.Button(paste_row, text="📷 Upload Gambar QR", fg_color=CARD2, text_color=ACC2,
                   font=("Segoe UI", 8), relief="flat", bd=0,
                   padx=10, pady=4, cursor="hand2",
                   command=_upload_qr_image).pack(side="left", padx=(0, 6))
        _ck.Button(paste_row, text="Bersihkan", fg_color=CARD2, text_color=MUT,
                   font=("Segoe UI", 8), relief="flat", bd=0,
                   padx=10, pady=4, cursor="hand2",
                   command=_clear_form).pack(side="left")

        # Nominal
        _section("NOMINAL TRANSAKSI (Rp)")
        nominal_var = tk.StringVar()
        nom_frame = _ck.Frame(left, fg_color=BG)
        nom_frame.pack(fill="x")
        _ck.Label(nom_frame, text="Rp", fg_color=BG, text_color=MUT,
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 6))
        nom_entry = _ck.Entry(nom_frame, textvariable=nominal_var, fg_color=CARD2, text_color=FG,
                              font=("Segoe UI", 13, "bold"), placeholder_text="Contoh: 50000")
        nom_entry.pack(side="left", fill="x", expand=True)

        # Format angka otomatis
        def _fmt_nominal(*_):
            raw = nominal_var.get().replace(".", "").replace(",", "")
            digits = "".join(c for c in raw if c.isdigit())
            if digits:
                formatted = "{:,}".format(int(digits)).replace(",", ".")
                nominal_var.set(formatted)
            else:
                nominal_var.set("")
        nom_entry.bind("<FocusOut>", _fmt_nominal)

        # Biaya layanan
        _section("BIAYA LAYANAN (Opsional)")
        fee_type_var = tk.StringVar(value="none")
        fee_row = _ck.Frame(left, fg_color=BG)
        fee_row.pack(fill="x")

        for label, val in [("Tidak Ada", "none"), ("Nominal Tetap", "fixed"), ("Persentase (%)", "percent")]:
            _ck.Radiobutton(fee_row, text=label, variable=fee_type_var, value=val,
                            fg_color=BG, text_color=FG,
                            font=("Segoe UI", 9)).pack(side="left", padx=(0, 16))

        fee_amt_var = tk.StringVar()
        fee_entry_frame = _ck.Frame(left, fg_color=BG)
        fee_entry_frame.pack(fill="x", pady=(6, 0))
        fee_prefix_lbl = _ck.Label(fee_entry_frame, text="Rp", fg_color=BG, text_color=MUT,
                                   font=("Segoe UI", 9, "bold"))
        fee_prefix_lbl.pack(side="left", padx=(0, 6))
        fee_entry = _ck.Entry(fee_entry_frame, textvariable=fee_amt_var, fg_color=CARD2,
                              text_color=FG, font=("Segoe UI", 10),
                              placeholder_text="Kosongkan jika tidak pakai biaya")
        fee_entry.pack(side="left", fill="x", expand=True)

        def _on_fee_type(*_):
            ft = fee_type_var.get()
            if ft == "none":
                fee_prefix_lbl.configure(text="")
                fee_entry.configure(placeholder_text="—", state="disabled")
                fee_amt_var.set("")
            elif ft == "fixed":
                fee_prefix_lbl.configure(text="Rp")
                fee_entry.configure(placeholder_text="Contoh: 2500", state="normal")
            else:
                fee_prefix_lbl.configure(text="%")
                fee_entry.configure(placeholder_text="Contoh: 2", state="normal")

        fee_type_var.trace_add("write", _on_fee_type)
        _on_fee_type()

        # Status & tombol generate
        _ck.Frame(left, fg_color=SIDE, height=1).pack(fill="x", pady=(16, 8))

        status_lbl = _ck.Label(left, text="", fg_color=BG, text_color=MUT,
                               font=("Segoe UI", 9), wraplength=380, justify="left")
        status_lbl.pack(anchor="w", pady=(0, 8))

        def _set_status(msg, color=MUT):
            if self._root:
                self._root.after(0, lambda: status_lbl.configure(text=msg, text_color=color))

        def _do_generate():
            from modules.qris.converter import QRISConverter, QRISError, generate_qr_image
            from PIL import ImageTk

            raw = qris_input.get("1.0", "end").strip()
            if not raw:
                _set_status("⚠ Masukkan string QRIS terlebih dahulu.", YEL)
                return

            # Validasi QRIS
            conv = QRISConverter()
            valid, err = conv.validate(raw)
            if not valid:
                _set_status("❌ " + err, RED)
                return

            # Parse nominal
            nom_raw = nominal_var.get().replace(".", "").replace(",", "").strip()
            if not nom_raw.isdigit() or int(nom_raw) <= 0:
                _set_status("⚠ Masukkan nominal yang valid (angka > 0).", YEL)
                return
            amount = int(nom_raw)

            # Parse biaya
            ft = fee_type_var.get()
            fee_type = None
            fee_val = 0
            if ft != "none":
                fee_raw = fee_amt_var.get().replace(",", ".").strip()
                if fee_raw:
                    try:
                        fee_parsed = float(fee_raw)
                        if fee_parsed <= 0:
                            raise ValueError
                        if ft == "fixed":
                            fee_val = int(fee_parsed)
                        else:
                            fee_val = fee_parsed
                        fee_type = ft
                    except ValueError:
                        _set_status("⚠ Biaya layanan tidak valid. Masukkan angka seperti 2500 atau 1.5", YEL)
                        gen_btn.configure(state="normal", text="⚡ Generate QRIS Dinamis")
                        return

            gen_btn.configure(state="disabled", text="Memproses...")
            _set_status("Mengkonversi QRIS...", MUT)

            def _bg():
                try:
                    result_str = conv.to_dynamic(raw, amount, fee_type, fee_val)
                    info = conv.parse_info(result_str)

                    # Generate QR image
                    pil_img = generate_qr_image(result_str, box_size=6, border=3)

                    # Scale ke 220x220
                    pil_img = pil_img.resize((220, 220))
                    photo = ImageTk.PhotoImage(pil_img)

                    def _update_ui():
                        qris_result[0] = result_str
                        qr_photo_ref[0] = photo
                        qr_lbl.configure(image=photo, text="")
                        merchant_lbl.configure(text=info.get("merchant_name", ""))
                        city_lbl.configure(text=info.get("merchant_city", ""))
                        nominal_preview.configure(
                            text="Rp {:,}".format(amount).replace(",", "."))
                        copy_btn.configure(state="normal")
                        save_btn.configure(state="normal")
                        gen_btn.configure(state="normal", text="⚡ Generate QRIS Dinamis")
                        _set_status(
                            "✅ QRIS dinamis berhasil dibuat! Scan QR di kanan untuk bayar.",
                            GRN)

                    if self._root:
                        self._root.after(0, _update_ui)

                except QRISError as e:
                    if self._root:
                        self._root.after(0, lambda: [
                            _set_status("❌ " + str(e), RED),
                            gen_btn.configure(state="normal",
                                              text="⚡ Generate QRIS Dinamis")
                        ])
                except Exception as e:
                    if self._root:
                        self._root.after(0, lambda: [
                            _set_status("❌ Error: " + str(e), RED),
                            gen_btn.configure(state="normal",
                                              text="⚡ Generate QRIS Dinamis")
                        ])

            _thr.Thread(target=_bg, daemon=True).start()

        gen_btn = _ck.Button(left, text="⚡ Generate QRIS Dinamis",
                             fg_color=ACC, text_color="white",
                             font=("Segoe UI", 11, "bold"), relief="flat", bd=0,
                             padx=20, pady=10, cursor="hand2",
                             command=_do_generate)
        gen_btn.pack(fill="x")

        # ── Panduan singkat ────────────────────────────────────────────────
        guide = _ck.Frame(left, fg_color=CARD, padx=14, pady=10)
        guide.pack(fill="x", pady=(16, 0))
        _ck.Frame(guide, fg_color=ACC, width=3).pack(side="left", fill="y")
        guide_inner = _ck.Frame(guide, fg_color=CARD, padx=10)
        guide_inner.pack(side="left", fill="x", expand=True)
        _ck.Label(guide_inner, text="Cara Pakai:", fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        for step in [
            "1. Cara A: Paste string QRIS langsung ke kolom atas.",
            "   Cara B: Klik 📷 Upload Gambar QR → pilih foto/screenshot QR.",
            "2. Masukkan nominal pembayaran.",
            "3. (Opsional) tambahkan biaya layanan fixed atau persentase (bisa desimal, misal 1.5%).",
            "4. Klik Generate → QR baru muncul di kanan, scan untuk bayar.",
        ]:
            _ck.Label(guide_inner, text=step, fg_color=CARD, text_color=MUT,
                     font=("Segoe UI", 8), wraplength=370, justify="left").pack(
                anchor="w", pady=(2, 0))

        return f

    # ================================================================

    def _pg_sheet(self):
        from modules.sheets import connector as _sc
        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Google Sheets",
                  "Connect sheets, preview data, and write values.")

        scroll_canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        scrollbar = _ck.Scrollbar(f, orient="vertical",
                                  command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)
        inner = _ck.Frame(scroll_canvas, fg_color=BG)
        inner_id = scroll_canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_resize(e):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
            scroll_canvas.itemconfig(inner_id, width=scroll_canvas.winfo_width())
        inner.bind("<Configure>", _on_inner_resize)
        scroll_canvas.bind("<Configure>",
                           lambda e: scroll_canvas.itemconfig(
                               inner_id, width=e.width))

        # --- Credentials check ---
        if not _sc.credentials_exist():
            self._build_sheet_setup_guide(inner)
            return f

        # --- No sheets yet ---
        if not self._ud.sheets:
            self._build_sheet_empty_state(inner)
            return f

        # --- Full manager ---
        self._build_sheet_manager(inner)
        return f

    def _build_sheet_setup_guide(self, parent):
        """Show credentials setup when credentials.json is missing."""
        from modules.sheets.credentials_helper import CredentialsSetupPanel

        warn_card = _card(parent, "Google Sheets is not set up yet")
        warn_card.pack(fill="x", padx=20, pady=(0, 8))
        _lbl(warn_card,
             "To connect Google Sheets, Synthex needs a service account key file\n"
             "(credentials.json). Follow the steps below to get one for free.", text_color=MUT, fg_color=CARD, font=("Segoe UI", 9), justify="left").pack(
            anchor="w", pady=(0, 12))

        def _on_creds_done():
            from modules.sheets import connector as _sc
            _sc.reset_client()
            self._navigate("sheet")

        panel = CredentialsSetupPanel(on_done=_on_creds_done)
        panel.build(warn_card)

    def _build_sheet_empty_state(self, parent):
        """Show a prompt to connect the first sheet."""
        empty_card = _card(parent, "No Sheets Connected Yet")
        empty_card.pack(fill="x", padx=20, pady=(0, 8))
        _lbl(empty_card,
             "Click the button below to connect your first Google Sheet.\n"
             "The wizard will guide you through every step.", text_color=MUT, fg_color=CARD, font=("Segoe UI", 9), justify="left").pack(
            anchor="w", pady=(0, 16))
        _ck.Button(
            empty_card, text="+ Connect First Sheet", fg_color=ACC, text_color=BG, font=("Segoe UI", 11, "bold"),
            relief="flat", bd=0, padx=20, pady=10, cursor="hand2",
            command=self._sheet_launch_wizard,
        ).pack(anchor="w")

    def _build_sheet_manager(self, parent):
        """Render the full sheets manager (table + preview + quick actions)."""
        # -- Connected sheets table --
        conn_card = _card(parent, "Connected Sheets")
        conn_card.pack(fill="x", padx=20, pady=(0, 8))

        self._sheets_tree = _tree(conn_card, [
            ("name",    "Name",        140),
            ("ws",      "Worksheet",    90),
            ("rows",    "Rows",         50),
            ("synced",  "Last Synced", 130),
            ("status",  "Status",       70),
        ])
        self._sheets_tree.configure(height=4)

        btn_row = _ck.Frame(conn_card, fg_color=CARD)
        btn_row.pack(fill="x", pady=(6, 0))
        _ck.Button(btn_row, text="Preview",
                   command=self._sheet_btn_preview).pack(side="left", padx=(0, 4))
        _ck.Button(btn_row, text="Test",
                   command=self._sheet_test).pack(side="left", padx=(0, 4))
        _ck.Button(btn_row, text="Remove",
                   command=self._sheet_remove).pack(side="left")
        _ck.Button(btn_row, text="+ Add Sheet", fg_color=ACC, text_color=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=4, cursor="hand2",
                  command=self._sheet_launch_wizard).pack(side="right")
        self._refresh_sheets_tree()

        # -- Data Preview --
        prev_card = _card(parent, "Data Preview")
        prev_card.pack(fill="x", padx=20, pady=(0, 8))

        prev_ctrl = _ck.Frame(prev_card, fg_color=CARD)
        prev_ctrl.pack(fill="x", pady=(0, 8))
        _lbl(prev_ctrl, "Sheet:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._prev_sheet_var = tk.StringVar()
        self._prev_sheet_cb  = _ck.Combobox(
            prev_ctrl, textvariable=self._prev_sheet_var,
            values=[s.get("name","") for s in self._ud.sheets],
            state="readonly", width=18)
        self._prev_sheet_cb.pack(side="left", padx=(4, 16))

        _lbl(prev_ctrl, "Tab:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._prev_ws_var = tk.StringVar()
        self._prev_ws_cb  = _ck.Combobox(
            prev_ctrl, textvariable=self._prev_ws_var,
            state="readonly", width=14)
        self._prev_ws_cb.pack(side="left", padx=(4, 16))
        self._prev_sheet_cb.bind(
            "<<ComboboxSelected>>", self._on_prev_sheet_change)

        _ck.Button(prev_ctrl, text="Refresh",
                   command=self._sheet_preview_refresh).pack(side="left")

        self._sheet_preview_frame = _ck.Frame(prev_card, fg_color=CARD)
        self._sheet_preview_frame.pack(fill="x")
        _lbl(self._sheet_preview_frame,
             "Select a connected sheet and click Refresh to preview data.", text_color=MUT, fg_color=CARD, font=("Segoe UI", 9)).pack(anchor="w")

        # Cell reader row
        cell_row = _ck.Frame(prev_card, fg_color=CARD)
        cell_row.pack(fill="x", pady=(10, 0))
        _lbl(cell_row, "Read cell:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._prev_cell_var = tk.StringVar(value="A1")
        _ck.Entry(cell_row, textvariable=self._prev_cell_var,
                  width=6).pack(side="left", padx=(4, 8))
        _ck.Button(cell_row, text="Read",
                   command=self._sheet_read_cell).pack(side="left")
        self._cell_result_lbl = _lbl(cell_row, "", text_color=GRN, fg_color=CARD,
                                     font=("Segoe UI", 9))
        self._cell_result_lbl.pack(side="left", padx=(10, 0))

        # -- Quick Actions --
        qa_card = _card(parent, "Quick Actions")
        qa_card.pack(fill="x", padx=20, pady=(0, 8))

        # Read cell row
        _lbl(qa_card, "Read Cell", text_color=ACC, fg_color=CARD,
             font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        rc_row = _ck.Frame(qa_card, fg_color=CARD)
        rc_row.pack(fill="x", pady=(0, 10))
        _lbl(rc_row, "Sheet:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._rc_sheet_var = tk.StringVar()
        _ck.Combobox(rc_row, textvariable=self._rc_sheet_var,
                     values=[s.get("name","") for s in self._ud.sheets],
                     state="readonly", width=16).pack(side="left", padx=(4, 10))
        _lbl(rc_row, "Cell:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._rc_cell_var = tk.StringVar(value="A1")
        _ck.Entry(rc_row, textvariable=self._rc_cell_var,
                  width=6).pack(side="left", padx=(4, 8))
        _ck.Button(rc_row, text="Read",
                   command=self._sheet_qa_read).pack(side="left")
        self._rc_result_lbl = _lbl(rc_row, "", text_color=GRN, fg_color=CARD,
                                   font=("Segoe UI", 9))
        self._rc_result_lbl.pack(side="left", padx=(10, 0))

        # Write cell row
        _lbl(qa_card, "Write Cell", text_color=ACC, fg_color=CARD,
             font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        wc_row1 = _ck.Frame(qa_card, fg_color=CARD)
        wc_row1.pack(fill="x", pady=(0, 4))
        _lbl(wc_row1, "Sheet:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._wc_sheet_var = tk.StringVar()
        _ck.Combobox(wc_row1, textvariable=self._wc_sheet_var,
                     values=[s.get("name","") for s in self._ud.sheets],
                     state="readonly", width=16).pack(side="left", padx=(4, 10))
        _lbl(wc_row1, "Cell:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._wc_cell_var = tk.StringVar(value="A1")
        _ck.Entry(wc_row1, textvariable=self._wc_cell_var,
                  width=6).pack(side="left", padx=(4, 0))
        wc_row2 = _ck.Frame(qa_card, fg_color=CARD)
        wc_row2.pack(fill="x", pady=(0, 10))
        _lbl(wc_row2, "Value:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._wc_val_var = tk.StringVar()
        _ck.Entry(wc_row2, textvariable=self._wc_val_var,
                  font=("Segoe UI", 9)).pack(
            side="left", fill="x", expand=True, padx=(4, 8))
        _ck.Button(wc_row2, text="Write Now", fg_color=GRN, text_color=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=4, cursor="hand2",
                  command=self._sheet_qa_write).pack(side="left")

        # Append row
        _lbl(qa_card, "Append Row", text_color=ACC, fg_color=CARD,
             font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        ar_row1 = _ck.Frame(qa_card, fg_color=CARD)
        ar_row1.pack(fill="x", pady=(0, 4))
        _lbl(ar_row1, "Sheet:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._ar_sheet_var = tk.StringVar()
        _ck.Combobox(ar_row1, textvariable=self._ar_sheet_var,
                     values=[s.get("name","") for s in self._ud.sheets],
                     state="readonly", width=16).pack(side="left", padx=(4, 0))
        ar_row2 = _ck.Frame(qa_card, fg_color=CARD)
        ar_row2.pack(fill="x", pady=(0, 4))
        _lbl(ar_row2, "Values (comma-separated):", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._ar_vals_var = tk.StringVar()
        _ck.Entry(ar_row2, textvariable=self._ar_vals_var,
                  font=("Segoe UI", 9)).pack(
            side="left", fill="x", expand=True, padx=(8, 8))
        _ck.Button(ar_row2, text="Append", fg_color=ACC, text_color=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=4, cursor="hand2",
                  command=self._sheet_qa_append).pack(side="left")

    # ----------------------------------------------------------------
    #  Sheet helpers
    # ----------------------------------------------------------------

    def _sheet_launch_wizard(self):
        from modules.sheets.auth_wizard import SheetsAuthWizard

        def _done(entry):
            for s in self._ud.sheets:
                if s.get("spreadsheet_id") == entry.get("spreadsheet_id"):
                    self._show_alert("Already Connected", "This sheet is already connected.")
                    return
            self._ud.sheets.append(entry)
            self._ud.save()
            self._navigate("sheet")

        wiz = SheetsAuthWizard(self._root, on_done=_done)
        wiz.start_wizard()

    def _refresh_sheets_tree(self):
        if not hasattr(self, "_sheets_tree") or not self._sheets_tree:
            return
        for row in self._sheets_tree.get_children():
            self._sheets_tree.delete(row)
        for s in self._ud.sheets:
            self._sheets_tree.insert("", "end", values=(
                s.get("name",""),
                s.get("worksheet",""),
                s.get("rows", "-"),
                s.get("last_synced","-"),
                s.get("status", "OK"),
            ))

    def _sheet_btn_preview(self):
        """Sync selection from table to preview panel sheet combobox."""
        if not hasattr(self, "_sheets_tree"):
            return
        sel = self._sheets_tree.selection()
        if not sel:
            self._show_alert("Preview", "Select a sheet first.")
            return
        idx = self._sheets_tree.index(sel[0])
        if idx >= len(self._ud.sheets):
            return
        name = self._ud.sheets[idx].get("name","")
        if hasattr(self, "_prev_sheet_var"):
            self._prev_sheet_var.set(name)
        self._sheet_preview_refresh()

    def _on_prev_sheet_change(self, *_):
        """Load worksheet tabs for the selected preview sheet."""
        name = self._prev_sheet_var.get()
        entry = next((s for s in self._ud.sheets if s.get("name") == name), None)
        if not entry:
            return
        sid = entry.get("spreadsheet_id","")
        if not hasattr(self, "_prev_ws_cb"):
            return

        def _load():
            from modules.sheets import connector as _sc
            names, _ = _sc.get_worksheets(sid)
            self._root.after(0, lambda: self._prev_ws_cb.configure(values=names))
            cur = entry.get("worksheet","Sheet1")
            if names:
                ws = cur if cur in names else names[0]
                self._root.after(0, lambda: self._prev_ws_var.set(ws))
        threading.Thread(target=_load, daemon=True).start()

    def _sheet_remove(self):
        if not hasattr(self, "_sheets_tree"):
            return
        sel = self._sheets_tree.selection()
        if not sel:
            return
        idx = self._sheets_tree.index(sel[0])
        if idx >= len(self._ud.sheets):
            return
        name = self._ud.sheets[idx].get("name","")
        if self._confirm_dialog(
                "Hapus Sheet?",
                "Hapus '{}'?\nData di Google Sheets tidak akan terhapus.".format(name),
                confirm_text="Ya, Hapus", accent=RED):
            del self._ud.sheets[idx]
            self._ud.save()
            self._navigate("sheet")

    def _sheet_test(self):
        if not hasattr(self, "_sheets_tree"):
            return
        sel = self._sheets_tree.selection()
        if not sel:
            self._show_alert("Test", "Select a sheet first.")
            return
        idx = self._sheets_tree.index(sel[0])
        if idx >= len(self._ud.sheets):
            return
        sheet = self._ud.sheets[idx]
        name  = sheet.get("name","")

        def _do():
            from modules.sheets import connector as _sc
            val, err = _sc.read_cell(self._ud.sheets, name, "A1")
            if err:
                self._root.after(0, lambda e=err: self._toast_error(e))
            else:
                self._root.after(0, lambda: self._toast_success(
                    "Sheet '{}' is connected! Cell A1: {}".format(
                        name, val or "(empty)")))
        threading.Thread(target=_do, daemon=True).start()

    def _sheet_read_cell(self):
        """Read cell button in the preview panel."""
        if not hasattr(self, "_prev_sheet_var"):
            return
        name = self._prev_sheet_var.get()
        cell = self._prev_cell_var.get().strip() or "A1"
        if not name:
            self._show_alert("Read Cell", "Select a sheet first.")
            return
        self._cell_result_lbl.configure(text="Reading...", text_color=MUT)

        def _do():
            from modules.sheets import connector as _sc
            val, err = _sc.read_cell(self._ud.sheets, name, cell)
            if err:
                self._root.after(0, lambda: self._cell_result_lbl.configure(
                    text=err, text_color=RED))
            else:
                self._root.after(0, lambda: self._cell_result_lbl.configure(
                    text=val or "(empty)", text_color=GRN))
        threading.Thread(target=_do, daemon=True).start()

    def _sheet_preview_refresh(self):
        if not hasattr(self, "_prev_sheet_var"):
            return
        sheet_name = self._prev_sheet_var.get()
        if not sheet_name:
            self._show_alert("Preview", "Select a sheet first.")
            return

        # If user picked a different worksheet tab, update entry temporarily
        ws_tab = self._prev_ws_var.get() if hasattr(self, "_prev_ws_var") else ""
        lookup = self._ud.sheets
        if ws_tab:
            lookup = []
            for s in self._ud.sheets:
                if s.get("name") == sheet_name:
                    entry = dict(s)
                    entry["worksheet"] = ws_tab
                    lookup.append(entry)
                else:
                    lookup.append(s)

        for w in self._sheet_preview_frame.winfo_children():
            w.destroy()
        _lbl(self._sheet_preview_frame, "Loading...", text_color=MUT, fg_color=CARD, font=("Segoe UI", 9)).pack(anchor="w")

        def _do():
            from modules.sheets import connector as _sc
            rows, err = _sc.preview_data(lookup, sheet_name, max_rows=15)
            self._root.after(0, lambda r=rows, e=err:
                             self._sheet_preview_show(r, e))
        threading.Thread(target=_do, daemon=True).start()

    def _sheet_preview_show(self, rows, err):
        if not hasattr(self, "_sheet_preview_frame"):
            return
        for w in self._sheet_preview_frame.winfo_children():
            w.destroy()
        if err:
            _lbl(self._sheet_preview_frame, err, text_color=RED, fg_color=CARD,
                 font=("Segoe UI", 9), justify="left",
                 wraplength=560).pack(anchor="w")
            return
        if rows:
            tbl = _ck.Frame(self._sheet_preview_frame, fg_color=CARD)
            tbl.pack(fill="x")
            max_cols = min(max(len(r) for r in rows), 10)
            for ri, row in enumerate(rows[:15]):
                for ci in range(max_cols):
                    val = row[ci] if ci < len(row) else ""
                    bg  = SIDE if ri == 0 else CARD
                    _ck.Label(tbl, text=str(val)[:20], fg_color=bg, text_color=ACC if ri == 0 else FG,
                             font=("Segoe UI", 8),
                             relief="flat", padx=6, pady=3,
                             borderwidth=1).grid(row=ri, column=ci, sticky="w")
        else:
            _lbl(self._sheet_preview_frame,
                 "No data available. Make sure the sheet has data and access is correct.", text_color=MUT, fg_color=CARD, font=("Segoe UI", 9)).pack(anchor="w")

    # -- Quick Action handlers --

    def _sheet_qa_read(self):
        name = self._rc_sheet_var.get()
        cell = self._rc_cell_var.get().strip() or "A1"
        if not name:
            self._show_alert("Read Cell", "Select a sheet first.", "warning")
            return
        self._rc_result_lbl.configure(text="Reading...", text_color=MUT)

        def _do():
            from modules.sheets import connector as _sc
            val, err = _sc.read_cell(self._ud.sheets, name, cell)
            if err:
                self._root.after(0, lambda: self._rc_result_lbl.configure(
                    text=err, text_color=RED))
            else:
                self._root.after(0, lambda: self._rc_result_lbl.configure(
                    text=repr(val) if val else "(empty)", text_color=GRN))
        threading.Thread(target=_do, daemon=True).start()

    def _sheet_qa_write(self):
        name  = self._wc_sheet_var.get()
        cell  = self._wc_cell_var.get().strip()
        value = self._wc_val_var.get()
        if not name or not cell:
            self._show_alert("Write Cell", "Select a sheet and enter a cell address.", "warning")
            return
        now = datetime.now()
        value = value.replace("{current_date}", now.strftime("%Y-%m-%d"))
        value = value.replace("{current_time}", now.strftime("%H:%M:%S"))
        if not self._confirm_dialog(
                "Konfirmasi Tulis",
                "Tulis '{}' ke cell {} di '{}'?".format(value, cell, name),
                confirm_text="Ya, Tulis", accent=ACC):

            return

        def _do():
            from modules.sheets import connector as _sc
            ok, err = _sc.write_cell(self._ud.sheets, name, cell, value)
            if err:
                self._root.after(0, lambda e=err: self._toast_error(e))
            else:
                entry = next((s for s in self._ud.sheets
                              if s.get("name") == name), None)
                if entry:
                    entry["last_synced"] = now.strftime("%Y-%m-%d %H:%M")
                    self._ud.save()
                self._root.after(0, lambda: [
                    self._toast_success(
                        "Done! Value written to {}!{}.".format(name, cell)),
                    self._refresh_sheets_tree(),
                ])
        threading.Thread(target=_do, daemon=True).start()

    def _sheet_qa_append(self):
        name   = self._ar_sheet_var.get()
        values = self._ar_vals_var.get().strip()
        if not name or not values:
            self._show_alert("Append Row", "Select a sheet and enter values.", "warning")
            return
        vals_list = [v.strip() for v in values.split(",")]

        def _do():
            from modules.sheets import connector as _sc
            ok, err = _sc.append_row(self._ud.sheets, name, vals_list)
            if err:
                self._root.after(0, lambda e=err: self._toast_error(e))
            else:
                self._root.after(0, lambda: self._toast_success(
                    "Done! Row appended to '{}'.".format(name)))
        threading.Thread(target=_do, daemon=True).start()

    # ================================================================
    #  REKENING PAGE
    # ================================================================

    def _pg_rekening(self):
        import threading as _threading

        # ── outer page frame ──────────────────────────────────────────────────
        f = _ck.Frame(self._content, fg_color=BG)

        # ── HEADER ────────────────────────────────────────────────────────────
        hdr_frame = _ck.Frame(f, fg_color=BG)
        hdr_frame.pack(fill="x", padx=24, pady=(18, 6))
        _ck.Label(hdr_frame, text="\U0001f3e6 Cek Rekening", fg_color=BG, text_color=ACC,
                 font=("Segoe UI", 16, "bold"), anchor="w").pack(anchor="w")
        _ck.Label(hdr_frame, text="Cek informasi pemilik rekening bank", fg_color=BG, text_color=MUT, font=("Segoe UI", 9), anchor="w").pack(anchor="w")

        # ── BODY: split layout ────────────────────────────────────────────────
        body = _ck.Frame(f, fg_color=BG)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # ── LEFT: input (~420px) ──────────────────────────────────────────────
        left = _ck.Frame(body, fg_color=CARD, width=420, padx=16, pady=14)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        # Top accent
        _ck.Frame(left, fg_color=ACC, height=3).pack(fill="x", pady=(0, 10))

        _ck.Label(left, text="Nomor Rekening (satu per baris):", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8, "bold"),
                 anchor="w").pack(anchor="w", pady=(0, 4))

        txt = _ck.ScrolledText(
            left, fg_color=BG, text_color=FG, insertbackground=FG,
            font=("Consolas", 10), relief="flat", bd=0,
            height=12, wrap="none",
            selectbackground=ACC, selectforeground=BG)
        txt.pack(fill="x")
        txt.insert("1.0", "BCA 1234567890\nBNI 0987654321\nMANDIRI 1122334455")

        # Button row
        btn_row = _ck.Frame(left, fg_color=CARD)
        btn_row.pack(fill="x", pady=(10, 0))

        stop_event = _threading.Event()

        def _do_stop():
            stop_event.set()
            stop_btn.configure(state="disabled")

        def _do_clear():
            txt.delete("1.0", tk.END)
            for iid in tree.get_children():
                tree.delete(iid)

        def _do_check():
            raw   = txt.get("1.0", tk.END).strip()
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            if not lines:
                return
            for iid in tree.get_children():
                tree.delete(iid)
            stop_event.clear()
            run_btn.configure(state="disabled")
            stop_btn.configure(state="normal")

            def _worker():
                for ln in lines:
                    if stop_event.is_set():
                        break
                    iid = tree.insert("", "end",
                                      values=("-", ln, "...", "Checking..."),
                                      tags=("checking",))
                    self._check_rekening_line(ln, iid, tree)

                self._root.after(0, lambda: run_btn.configure(state="normal"))
                self._root.after(0, lambda: stop_btn.configure(state="disabled"))

            _threading.Thread(target=_worker, daemon=True).start()

        run_btn = _ck.Button(btn_row, text="Cek Semua", fg_color=ACC, text_color=BG, font=("Segoe UI", 9, "bold"),
                            relief="flat", bd=0, padx=12, pady=6,
                            cursor="hand2", command=_do_check)
        run_btn.pack(side="left", padx=(0, 6))

        stop_btn = _ck.Button(btn_row, text="Stop", fg_color=CARD, text_color=RED, font=("Segoe UI", 9),
                             relief="flat", bd=0, padx=12, pady=6,
                             cursor="hand2", command=_do_stop,
                             state="disabled")
        stop_btn.pack(side="left", padx=(0, 6))

        _ck.Button(btn_row, text="Clear", fg_color=CARD, text_color=MUT, font=("Segoe UI", 9),
                  relief="flat", bd=0, padx=12, pady=6,
                  cursor="hand2", command=_do_clear).pack(side="left")

        # Import row
        import_row = _ck.Frame(left, fg_color=CARD)
        import_row.pack(fill="x", pady=(8, 0))

        def _import_file():
            from tkinter import filedialog as _fd
            path = _fd.askopenfilename(
                title="Pilih file CSV / Excel",
                filetypes=[("CSV files", "*.csv"),
                           ("Excel files", "*.xlsx *.xls"),
                           ("All files", "*.*")])
            if not path:
                return
            rows = []
            try:
                if path.lower().endswith(".csv"):
                    import csv
                    with open(path, newline="", encoding="utf-8-sig") as fh:
                        reader = csv.reader(fh)
                        for row in reader:
                            rows.append(row)
                else:
                    try:
                        import openpyxl
                        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
                        ws = wb.active
                        for row in ws.iter_rows(values_only=True):
                            rows.append([str(c) if c is not None else "" for c in row])
                        wb.close()
                    except ImportError:
                        self._show_alert("Error",
                            "openpyxl tidak terinstall.\nGunakan file CSV atau jalankan:\npip install openpyxl",
                            kind="error")
                        return
            except Exception as ex:
                self._show_alert("Error Baca File", str(ex), kind="error")
                return

            # Try to find bank & nomor columns automatically
            # Expected: first text col = provider/bank, second numeric col = account number
            # OR single col with "BANK NOMOR" format
            lines = []
            for row in rows:
                non_empty = [str(c).strip() for c in row if str(c).strip()]
                if not non_empty:
                    continue
                if len(non_empty) >= 2:
                    # First col = bank, second = nomor
                    lines.append("{} {}".format(non_empty[0], non_empty[1]))
                elif len(non_empty) == 1:
                    lines.append(non_empty[0])

            if not lines:
                self._show_alert("File Kosong", "Tidak ada data yang bisa dibaca.", kind="info")
                return

            txt.delete("1.0", tk.END)
            txt.insert("1.0", "\n".join(lines))
            import_status.configure(
                text="{} baris diimpor dari {}".format(len(lines), path.split("/")[-1]))

        def _export_results():
            from tkinter import filedialog as _fd
            path = _fd.asksaveasfilename(
                title="Simpan hasil sebagai CSV",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")])
            if not path:
                return
            import csv
            rows = [tree.item(iid, "values") for iid in tree.get_children()]
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(["Provider", "Nomor", "Nama Pemilik", "Status"])
                w.writerows(rows)
            import_status.configure(text="Hasil disimpan ke: {}".format(path.split("/")[-1]))

        _ck.Button(import_row, text="📂 Import CSV/Excel", fg_color="#1A3A1A", text_color=GRN, font=("Segoe UI", 8, "bold"),
                  relief="flat", bd=0, padx=10, pady=4,
                  cursor="hand2", command=_import_file).pack(side="left", padx=(0, 6))
        _ck.Button(import_row, text="💾 Export Hasil", fg_color="#1A1A3A", text_color="#4A9EFF", font=("Segoe UI", 8, "bold"),
                  relief="flat", bd=0, padx=10, pady=4,
                  cursor="hand2", command=_export_results).pack(side="left")

        import_status = _ck.Label(left, text="", fg_color=CARD, text_color=MUT,
                                 font=("Segoe UI", 7), anchor="w", wraplength=380)
        import_status.pack(anchor="w", pady=(4, 0))

        # Hint
        _ck.Label(left, text="Double-klik baris untuk menyalin nama", fg_color=CARD, text_color=MUT, font=("Segoe UI", 7),
                 anchor="w").pack(anchor="w", pady=(4, 0))

        # ── RIGHT: results ────────────────────────────────────────────────────
        right = _ck.Frame(body, fg_color=BG)
        right.pack(side="left", fill="both", expand=True)

        res_hdr = _ck.Frame(right, fg_color=BG)
        res_hdr.pack(fill="x", pady=(0, 6))
        _ck.Label(res_hdr, text="Hasil Pengecekan", fg_color=BG, text_color=FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(anchor="w")

        tree_frame = _ck.Frame(right, fg_color=CARD)
        tree_frame.pack(fill="both", expand=True)

        cols = [
            ("provider", "Provider",     90),
            ("nomor",    "Nomor",       130),
            ("nama",     "Nama Pemilik",200),
            ("status",   "Status",       90),
        ]
        tree = ttk.Treeview(tree_frame, columns=[c[0] for c in cols],
                            show="headings", selectmode="browse")
        for cid, head, w in cols:
            tree.heading(cid, text=head)
            tree.column(cid, width=w, anchor="w")

        vsb = _ck.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        tree.tag_configure("ok",       foreground=GRN)
        tree.tag_configure("error",    foreground=RED)
        tree.tag_configure("checking", foreground=YEL)

        def _copy_nama(event):
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0], "values")
            if vals and len(vals) > 2 and vals[2] not in ("-", "...", ""):
                self._root.clipboard_clear()
                self._root.clipboard_append(vals[2])
                # brief flash
                orig_text = vals[3] if len(vals) > 3 else ""
                tree.item(sel[0], values=(vals[0], vals[1], vals[2], "Disalin!"))
                self._root.after(1200, lambda: tree.item(
                    sel[0], values=(vals[0], vals[1], vals[2], orig_text)))

        tree.bind("<Double-1>", _copy_nama)

        return f

    def _check_rekening_line(self, nomor, iid, tree):
        """Check a single rekening number; called from a worker thread."""
        try:
            from modules.rekening import check_rekening
            raw   = nomor.strip()
            parts = raw.split()
            prov  = parts[0].upper() if len(parts) >= 2 else "BCA"
            num   = parts[1]         if len(parts) >= 2 else parts[0]
            result = check_rekening(prov, num)
            nama   = result.get("name",   "-")
            status = result.get("status", "Gagal")
            tag    = "ok" if status == "Valid" else "error"
        except Exception as e:
            prov   = "?"
            num    = nomor.strip()
            nama   = "-"
            status = "Error: {}".format(str(e)[:25])
            tag    = "error"
        try:
            self._root.after(0, lambda: tree.item(
                iid, values=(prov, num, nama, status), tags=(tag,)))
        except Exception:
            pass

    # ================================================================
    #  HISTORY PAGE
    # ================================================================

    # ================================================================
    #  MONITOR HARGA PAGE
    # ================================================================

    def _pg_monitor(self):
        """Halaman Dashboard Update — ambil tabel web, tulis ke Google Sheet."""
        from modules.price_monitor import PriceMonitor

        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Monitor", "Pantau data tabel & perubahan halaman web secara otomatis")

        # State
        if not hasattr(self, "_price_monitor"):
            self._price_monitor = None

        # ── Notebook tabs ────────────────────────────────────────────────────
        style = ttk.Style()
        style.configure("Mon.TNotebook",        background=BG, borderwidth=0)
        style.configure("Mon.TNotebook.Tab",    background=CARD2, foreground=MUT,
                        padding=[14, 6], font=("Segoe UI", 9))
        style.map("Mon.TNotebook.Tab",
                  background=[("selected", CARD)],
                  foreground=[("selected", FG)])

        nb = ttk.Notebook(f)
        nb.pack(fill="both", expand=True, padx=0, pady=(4, 0))

        tab1 = _ck.Frame(nb, fg_color=BG)
        tab2 = _ck.Frame(nb, fg_color=BG)
        nb.add(tab1, text="📊  Tabel Otomatis")
        nb.add(tab2, text="👁  Pantau Perubahan")
        nb_tabs = [tab1, tab2]

        # ── Tab 1: Tabel Otomatis ────────────────────────────────────────────
        # ── Outer scroll area ─────────────────────────────────────────────────
        body = _ck.Frame(tab1, fg_color=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # ── Konfigurasi ───────────────────────────────────────────────────────
        cfg_card = _card(body, "Konfigurasi")
        cfg_card.pack(fill="x", pady=(8, 0))

        def _row(parent, label, widget_fn):
            row = _ck.Frame(parent, fg_color=CARD)
            row.pack(fill="x", padx=10, pady=3)
            _ck.Label(row, text=label, fg_color=CARD, text_color=MUT,
                     font=("Segoe UI", 9), width=22, anchor="w").pack(
                         side="left", padx=(0, 6))
            w = widget_fn(row)
            w.pack(side="left", fill="x", expand=True)
            return w

        # URL
        v_url = tk.StringVar()
        _row(cfg_card, "URL Halaman *",
             lambda p: _ck.Entry(p, textvariable=v_url, fg_color=CARD2, text_color=FG,
                                insertbackground=FG, relief="flat", font=("Segoe UI", 9)))

        # Tombol refresh selector
        v_btn = tk.StringVar()
        btn_entry = _row(cfg_card, "Selector Tombol Refresh",
                         lambda p: _ck.Entry(p, textvariable=v_btn, fg_color=CARD2, text_color=FG,
                                            insertbackground=FG, relief="flat",
                                            font=("Segoe UI", 9)))
        _ck.Label(cfg_card, text="   (kosongkan jika tidak ada tombol refresh)", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", padx=10)

        # Selector tabel
        v_tbl = tk.StringVar(value="table")
        _row(cfg_card, "Selector Tabel *",
             lambda p: _ck.Entry(p, textvariable=v_tbl, fg_color=CARD2, text_color=FG,
                                insertbackground=FG, relief="flat", font=("Segoe UI", 9)))

        # Mode
        v_mode = tk.StringVar(value="requests")
        mode_row = _ck.Frame(cfg_card, fg_color=CARD)
        mode_row.pack(fill="x", padx=10, pady=3)
        _ck.Label(mode_row, text="Mode Browser", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9), width=22, anchor="w").pack(side="left")
        for txt, val in [("Requests (halaman statis)", "requests"),
                         ("Headless Chrome (JS/dinamis)", "headless")]:
            _ck.Radiobutton(mode_row, text=txt, variable=v_mode, value=val, fg_color=CARD, text_color=FG, selectcolor=CARD2,
                           activebackground=CARD, activeforeground=FG,
                           font=("Segoe UI", 9)).pack(side="left", padx=(0, 12))

        _ck.Label(cfg_card,
                 text="   Headless = browser tersembunyi, tidak muncul di layar. "
                      "Tab browser kamu bisa diminimize.", fg_color=CARD, text_color=YEL, font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(0, 4))

        # Interval
        v_interval = tk.StringVar(value="5")
        intv_row = _ck.Frame(cfg_card, fg_color=CARD)
        intv_row.pack(fill="x", padx=10, pady=3)
        _ck.Label(intv_row, text="Interval (menit) *", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9), width=22, anchor="w").pack(side="left")
        tk.Spinbox(intv_row, from_=1, to=1440, textvariable=v_interval,
                   width=6, bg=CARD2, fg=FG, buttonbackground=CARD2,
                   relief="flat", font=("Segoe UI", 9)).pack(side="left")
        _ck.Label(intv_row, text="menit", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9)).pack(side="left", padx=4)

        # ── Google Sheet ──────────────────────────────────────────────────────
        sheet_card = _card(body, "Google Sheet Tujuan")
        sheet_card.pack(fill="x", pady=(10, 0))

        v_sheet_id = tk.StringVar()
        _row(sheet_card, "Sheet ID / URL *",
             lambda p: _ck.Entry(p, textvariable=v_sheet_id, fg_color=CARD2, text_color=FG,
                                insertbackground=FG, relief="flat", font=("Segoe UI", 9)))

        v_ws = tk.StringVar(value="Sheet1")
        _row(sheet_card, "Nama Worksheet",
             lambda p: _ck.Entry(p, textvariable=v_ws, fg_color=CARD2, text_color=FG,
                                insertbackground=FG, relief="flat", font=("Segoe UI", 9)))

        v_cell = tk.StringVar(value="A1")
        _row(sheet_card, "Mulai dari sel",
             lambda p: _ck.Entry(p, textvariable=v_cell, fg_color=CARD2, text_color=FG,
                                insertbackground=FG, relief="flat", font=("Segoe UI", 9)))

        v_clear = tk.BooleanVar(value=True)
        _ck.Checkbutton(sheet_card, text="Hapus isi sheet sebelum update",
                       variable=v_clear, fg_color=CARD, text_color=FG,
                       selectcolor=CARD2, activebackground=CARD,
                       activeforeground=FG, font=("Segoe UI", 9)).pack(
                           anchor="w", padx=10, pady=(0, 6))

        # ── Status & log ──────────────────────────────────────────────────────
        ctrl_card = _card(body, "Status & Kontrol")
        ctrl_card.pack(fill="both", expand=True, pady=(10, 0))

        # Stats row
        stats_row = _ck.Frame(ctrl_card, fg_color=CARD)
        stats_row.pack(fill="x", padx=10, pady=(6, 4))

        v_status_lbl  = tk.StringVar(value="Belum berjalan")
        v_last_update = tk.StringVar(value="-")
        v_cycle_count = tk.StringVar(value="0")

        _ck.Label(stats_row, text="Status:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        _ck.Label(stats_row, textvariable=v_status_lbl, fg_color=CARD, text_color=YEL,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(4, 20))
        _ck.Label(stats_row, text="Siklus:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        _ck.Label(stats_row, textvariable=v_cycle_count, fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(4, 20))
        _ck.Label(stats_row, text="Update terakhir:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        _ck.Label(stats_row, textvariable=v_last_update, fg_color=CARD, text_color=GRN,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=4)

        # Log box
        log_frame = _ck.Frame(ctrl_card, fg_color=CARD2, relief="flat")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        log_txt = _ck.Text(log_frame, height=7, fg_color=CARD2, text_color=FG,
                          font=("Consolas", 8), relief="flat",
                          state="disabled", wrap="word")
        log_scroll = tk.Scrollbar(log_frame, command=log_txt.yview, bg=CARD2, troughcolor=CARD2)
        log_txt.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        log_txt.pack(fill="both", expand=True, padx=4, pady=4)

        # Preview tabel
        prev_card = _card(body, "Preview Data Terakhir")
        prev_card.pack(fill="both", expand=True, pady=(10, 0))

        prev_txt = _ck.Text(prev_card, height=6, fg_color=CARD2, text_color=GRN,
                           font=("Consolas", 8), relief="flat",
                           state="disabled", wrap="none")
        prev_scroll_y = tk.Scrollbar(prev_card, command=prev_txt.yview, bg=CARD2, troughcolor=CARD2)
        prev_scroll_x = tk.Scrollbar(prev_card, orient="horizontal",
                                     command=prev_txt.xview, bg=CARD2, troughcolor=CARD2)
        prev_txt.configure(yscrollcommand=prev_scroll_y.set,
                           xscrollcommand=prev_scroll_x.set)
        prev_scroll_y.pack(side="right", fill="y")
        prev_scroll_x.pack(side="bottom", fill="x")
        prev_txt.pack(fill="both", expand=True, padx=4, pady=4)

        # ── Helpers ───────────────────────────────────────────────────────────

        def _log(msg):
            """Append a timestamped line to log box (thread-safe via after)."""
            import datetime
            ts  = datetime.datetime.now().strftime("%H:%M:%S")
            line = "[{}] {}\n".format(ts, msg)

            def _do():
                log_txt.configure(state="normal")
                log_txt.insert("end", line)
                log_txt.see("end")
                log_txt.configure(state="disabled")
            try:
                f.after(0, _do)
            except Exception:
                pass

        def _update_preview(rows):
            """Render table rows in preview box."""
            if not rows:
                return
            lines = []
            for row in rows[:20]:   # Max 20 baris di preview
                lines.append("  |  ".join(str(c)[:25] for c in row))
            text = "\n".join(lines)
            if len(rows) > 20:
                text += "\n... ({} baris total)".format(len(rows))

            def _do():
                prev_txt.configure(state="normal")
                prev_txt.delete("1.0", "end")
                prev_txt.insert("end", text)
                prev_txt.configure(state="disabled")
            try:
                f.after(0, _do)
            except Exception:
                pass

        def _refresh_stats():
            pm = self._price_monitor
            if pm is None:
                return
            v_cycle_count.set(str(pm.cycle_count))
            if pm.last_update:
                v_last_update.set(pm.last_update.strftime("%H:%M:%S"))

        def _on_status(msg):
            _log(msg)
            f.after(0, _refresh_stats)

        def _on_data(rows):
            f.after(0, lambda: _update_preview(rows))

        # ── Buttons ───────────────────────────────────────────────────────────

        btn_row = _ck.Frame(ctrl_card, fg_color=CARD)
        btn_row.pack(fill="x", padx=10, pady=(0, 8))

        def _build_monitor():
            """Read config vars and create/reconfigure PriceMonitor."""
            url = v_url.get().strip()
            if not url:
                self._show_alert("Dashboard Update", "URL wajib diisi.", "warning")
                return None
            if not url.startswith(("http://", "https://")):
                self._show_alert("Dashboard Update",
                                 "URL harus dimulai dengan http:// atau https://", "warning")
                return None

            try:
                interval_sec = max(1, int(v_interval.get())) * 60
            except ValueError:
                interval_sec = 300

            pm = PriceMonitor(on_status=_on_status, on_data=_on_data)
            pm.configure(
                url            = url,
                btn_selector   = v_btn.get().strip(),
                table_selector = v_tbl.get().strip() or "table",
                mode           = v_mode.get(),
                interval_sec   = interval_sec,
                sheet_id       = v_sheet_id.get().strip(),
                worksheet      = v_ws.get().strip() or "Sheet1",
                start_cell     = v_cell.get().strip().upper() or "A1",
                clear_before   = v_clear.get(),
            )
            return pm

        btn_start = _ck.Button(btn_row, text="MULAI MONITOR", fg_color=GRN, text_color=BG,
                              font=("Segoe UI", 10, "bold"), relief="flat",
                              padx=14, pady=6, cursor="hand2")
        btn_stop  = _ck.Button(btn_row, text="STOP", fg_color=RED, text_color="#fff",
                              font=("Segoe UI", 10, "bold"), relief="flat",
                              padx=14, pady=6, cursor="hand2",
                              state="disabled")
        btn_once  = _ck.Button(btn_row, text="JALANKAN SEKALI", fg_color=ACC2, text_color="#fff",
                              font=("Segoe UI", 10, "bold"), relief="flat",
                              padx=14, pady=6, cursor="hand2")

        def _start():
            if self._price_monitor and self._price_monitor.running:
                return
            pm = _build_monitor()
            if pm is None:
                return
            self._price_monitor = pm
            pm.start()
            v_status_lbl.set("Berjalan")
            btn_start.configure(state="disabled")
            btn_stop.configure(state="normal")
            btn_once.configure(state="disabled")

        def _stop():
            if self._price_monitor:
                self._price_monitor.stop()
                self._price_monitor = None
            v_status_lbl.set("Dihentikan")
            btn_start.configure(state="normal")
            btn_stop.configure(state="disabled")
            btn_once.configure(state="normal")

        def _run_once():
            pm = _build_monitor()
            if pm is None:
                return
            self._price_monitor = pm
            btn_once.configure(state="disabled")
            _log("Menjalankan satu siklus...")

            def _worker():
                pm.run_once()
                try:
                    f.after(0, lambda: btn_once.configure(state="normal"))
                except Exception:
                    pass

            threading.Thread(target=_worker, daemon=True).start()

        btn_start.configure(command=_start)
        btn_stop.configure(command=_stop)
        btn_once.configure(command=_run_once)

        btn_start.pack(side="left", padx=(0, 8))
        btn_stop.pack(side="left", padx=(0, 8))
        btn_once.pack(side="left")

        # Restore running state if monitor is already active
        if self._price_monitor and self._price_monitor.running:
            v_status_lbl.set("Berjalan")
            btn_start.configure(state="disabled")
            btn_stop.configure(state="normal")
            btn_once.configure(state="disabled")
            # Rewire callbacks to new UI
            self._price_monitor._on_status = _on_status
            self._price_monitor._on_data   = _on_data
            _log("Monitor sudah berjalan (dilanjutkan dari sesi sebelumnya).")

        # ── Tab 2: Pantau Perubahan ───────────────────────────────────────────
        tab2 = nb_tabs[1]
        body2 = _ck.Frame(tab2, fg_color=BG)
        body2.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        if not hasattr(self, "_wcm"):
            self._wcm = None   # WebChangeMonitor instance

        # Config card
        wc_cfg = _card(body2, "Konfigurasi Pantau Perubahan")
        wc_cfg.pack(fill="x", pady=(8, 0))

        def _wrow(parent, label, widget_fn):
            row = _ck.Frame(parent, fg_color=CARD)
            row.pack(fill="x", padx=10, pady=3)
            _ck.Label(row, text=label, fg_color=CARD, text_color=MUT,
                     font=("Segoe UI", 9), width=24, anchor="w").pack(
                side="left", padx=(0, 6))
            w = widget_fn(row)
            w.pack(side="left", fill="x", expand=True)
            return w

        v_wc_url = tk.StringVar()
        _wrow(wc_cfg, "URL yang dipantau *",
              lambda p: _ck.Entry(p, textvariable=v_wc_url, fg_color=CARD2, text_color=FG,
                                 insertbackground=FG, relief="flat",
                                 font=("Segoe UI", 9)))

        v_wc_kw = tk.StringVar()
        _wrow(wc_cfg, "Keyword (opsional)",
              lambda p: _ck.Entry(p, textvariable=v_wc_kw, fg_color=CARD2, text_color=FG,
                                 insertbackground=FG, relief="flat",
                                 font=("Segoe UI", 9)))
        _ck.Label(wc_cfg,
                 text="   Kosongkan = pantau semua perubahan. "
                      "Isi = pantau keyword ini muncul/hilang. "
                      "Contoh: Stok habis, Out of stock", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(
            anchor="w", padx=10, pady=(0, 4))

        v_wc_intv = tk.StringVar(value="5")
        intv_row2 = _ck.Frame(wc_cfg, fg_color=CARD)
        intv_row2.pack(fill="x", padx=10, pady=3)
        _ck.Label(intv_row2, text="Interval (menit)", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9), width=24, anchor="w").pack(side="left")
        tk.Spinbox(intv_row2, from_=1, to=1440, textvariable=v_wc_intv,
                   width=6, bg=CARD2, fg=FG, buttonbackground=CARD2,
                   relief="flat", font=("Segoe UI", 9)).pack(side="left")
        _ck.Label(intv_row2, text="menit", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9)).pack(side="left", padx=4)

        # AI analysis toggle
        v_wc_ai = tk.BooleanVar(value=False)
        _ck.Checkbutton(wc_cfg,
                       text="Analisis perubahan dengan AI (butuh API key di Settings)",
                       variable=v_wc_ai, fg_color=CARD, text_color=FG, selectcolor=CARD2,
                       activebackground=CARD, activeforeground=FG,
                       font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=(0, 6))

        # Status card
        wc_ctrl = _card(body2, "Status & Log")
        wc_ctrl.pack(fill="both", expand=True, pady=(10, 0))

        wc_stats_row = _ck.Frame(wc_ctrl, fg_color=CARD)
        wc_stats_row.pack(fill="x", padx=10, pady=(6, 4))
        v_wc_status = tk.StringVar(value="Belum berjalan")
        v_wc_changes = tk.StringVar(value="0")
        v_wc_last = tk.StringVar(value="-")
        _ck.Label(wc_stats_row, text="Status:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        _ck.Label(wc_stats_row, textvariable=v_wc_status, fg_color=CARD, text_color=YEL,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(4, 20))
        _ck.Label(wc_stats_row, text="Perubahan:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        _ck.Label(wc_stats_row, textvariable=v_wc_changes, fg_color=CARD, text_color=RED,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(4, 20))
        _ck.Label(wc_stats_row, text="Terakhir berubah:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        _ck.Label(wc_stats_row, textvariable=v_wc_last, fg_color=CARD, text_color=GRN,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=4)

        # Log
        wc_log_f = _ck.Frame(wc_ctrl, fg_color=CARD2, relief="flat")
        wc_log_f.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        wc_log_txt = _ck.Text(wc_log_f, height=6, fg_color=CARD2, text_color=FG,
                             font=("Consolas", 8), relief="flat",
                             state="disabled", wrap="word")
        wc_log_sb = tk.Scrollbar(wc_log_f, command=wc_log_txt.yview, bg=CARD2, troughcolor=CARD2)
        wc_log_txt.configure(yscrollcommand=wc_log_sb.set)
        wc_log_sb.pack(side="right", fill="y")
        wc_log_txt.pack(fill="both", expand=True, padx=4, pady=4)

        # Change detail area
        wc_change_card = _card(body2, "Detail Perubahan Terakhir")
        wc_change_card.pack(fill="both", expand=True, pady=(10, 0))
        wc_diff_txt = _ck.Text(wc_change_card, height=5, fg_color=CARD2, text_color=YEL,
                              font=("Consolas", 8), relief="flat",
                              state="disabled", wrap="word")
        wc_diff_txt.pack(fill="both", expand=True, padx=6, pady=6)

        def _wc_log(msg: str):
            import datetime as _dtt
            ts = _dtt.datetime.now().strftime("%H:%M:%S")
            line = "[{}] {}\n".format(ts, msg)
            def _do():
                wc_log_txt.configure(state="normal")
                wc_log_txt.insert("end", line)
                wc_log_txt.see("end")
                wc_log_txt.configure(state="disabled")
                if self._wcm:
                    v_wc_changes.set(str(self._wcm.change_count))
                    if self._wcm.last_change:
                        v_wc_last.set(
                            self._wcm.last_change.strftime("%H:%M:%S"))
            try: f.after(0, _do)
            except Exception: pass

        def _wc_on_change(old_text, new_text, summary):
            def _do():
                wc_diff_txt.configure(state="normal")
                wc_diff_txt.delete("1.0", "end")
                wc_diff_txt.insert("end", summary)
                wc_diff_txt.configure(state="disabled")
                _wc_log("BERUBAH: " + summary[:80])
            try: f.after(0, _do)
            except Exception: pass

        def _wc_build():
            url = v_wc_url.get().strip()
            if not url:
                return None
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            try:
                intv = max(1, int(v_wc_intv.get())) * 60
            except ValueError:
                intv = 300
            from modules.web_change_monitor import WebChangeMonitor as _WCM
            wm = _WCM(on_status=_wc_log, on_change=_wc_on_change)
            ai_key = self.config.get("ai.api_key", "").strip() if v_wc_ai.get() else ""
            wm.configure(
                url=url,
                interval_sec=intv,
                keyword=v_wc_kw.get().strip(),
                ai_analysis=v_wc_ai.get() and bool(ai_key),
                ai_key=ai_key,
                ai_provider=self.config.get("ai.provider", "openai"),
                ai_model=self.config.get("ai.model", ""),
            )
            return wm

        wc_btn_row = _ck.Frame(wc_ctrl, fg_color=CARD)
        wc_btn_row.pack(fill="x", padx=10, pady=(0, 8))

        wc_btn_start = _ck.Button(wc_btn_row, text="MULAI PANTAU", fg_color=GRN, text_color=BG,
                                 font=("Segoe UI", 10, "bold"), relief="flat",
                                 padx=14, pady=6, cursor="hand2")
        wc_btn_stop  = _ck.Button(wc_btn_row, text="STOP", fg_color=RED, text_color="#fff",
                                 font=("Segoe UI", 10, "bold"), relief="flat",
                                 padx=14, pady=6, cursor="hand2", state="disabled")
        wc_btn_once  = _ck.Button(wc_btn_row, text="CEK SEKARANG", fg_color=ACC2, text_color="#fff",
                                 font=("Segoe UI", 10, "bold"), relief="flat",
                                 padx=14, pady=6, cursor="hand2")

        def _wc_start():
            if self._wcm and self._wcm.running:
                return
            wm = _wc_build()
            if not wm:
                _wc_log("ERROR: URL wajib diisi")
                return
            self._wcm = wm
            wm.start()
            v_wc_status.set("Berjalan")
            wc_btn_start.configure(state="disabled")
            wc_btn_stop.configure(state="normal")
            wc_btn_once.configure(state="disabled")

        def _wc_stop():
            if self._wcm:
                self._wcm.stop()
                self._wcm = None
            v_wc_status.set("Dihentikan")
            wc_btn_start.configure(state="normal")
            wc_btn_stop.configure(state="disabled")
            wc_btn_once.configure(state="normal")

        def _wc_once():
            wm = _wc_build()
            if not wm:
                _wc_log("ERROR: URL wajib diisi")
                return
            self._wcm = wm
            wc_btn_once.configure(state="disabled")
            _wc_log("Menjalankan satu pengecekan…")
            def _w():
                wm.check_now()
                try: f.after(0, lambda: wc_btn_once.configure(state="normal"))
                except Exception: pass
            threading.Thread(target=_w, daemon=True).start()

        wc_btn_start.configure(command=_wc_start)
        wc_btn_stop.configure(command=_wc_stop)
        wc_btn_once.configure(command=_wc_once)
        wc_btn_start.pack(side="left", padx=(0, 8))
        wc_btn_stop.pack(side="left", padx=(0, 8))
        wc_btn_once.pack(side="left")

        if self._wcm and self._wcm.running:
            v_wc_status.set("Berjalan")
            wc_btn_start.configure(state="disabled")
            wc_btn_stop.configure(state="normal")
            wc_btn_once.configure(state="disabled")
            self._wcm._on_status  = _wc_log
            self._wcm._on_change  = _wc_on_change

        return f

    # ================================================================
    #  REMOTE PAGE  (ADB Mirror via scrcpy) — multi-device
    # ================================================================

    def _pg_remote(self):
        import threading as _thr
        import os as _os

        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Mirror HP",
                  "Mirror & control multiple Android devices simultaneously")

        _FB = dict(relief="flat", bd=0, cursor="hand2")

        # ── scrollable body ──────────────────────────────────────────────────
        sb = _ck.Scrollbar(f, orient="vertical")
        sb.pack(side="right", fill="y")
        cv = tk.Canvas(f, bg=BG, highlightthickness=0, yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.config(command=cv.yview)
        body = _ck.Frame(cv, fg_color=BG)
        _wid = cv.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>",
                lambda e: cv.itemconfig(_wid, width=e.width))

        def _sec(title, accent=ACC, subtitle=""):
            w = _ck.Frame(body, fg_color=CARD)
            w.pack(fill="x", padx=20, pady=(0, 12))
            h = _ck.Frame(w, fg_color=accent, padx=14, pady=9)
            h.pack(fill="x")
            _ck.Label(h, text=title, fg_color=accent, text_color="white",
                     font=("Segoe UI", 10, "bold")).pack(side="left")
            if subtitle:
                _ck.Label(h, text=subtitle, fg_color=accent, text_color="white",
                         font=("Segoe UI", 8)).pack(
                    side="left", padx=(8, 0))
            b = _ck.Frame(w, fg_color=CARD, padx=14, pady=12)
            b.pack(fill="x")
            return b

        _ck.Frame(body, fg_color=BG, height=8).pack()

        # ══════════════════════════════════════════════════════════════
        # SECTION 1 — Perangkat Terhubung
        # ══════════════════════════════════════════════════════════════
        conn = _sec("Perangkat", accent="#1A0840")

        # Status row
        st = _ck.Frame(conn, fg_color=CARD)
        st.pack(fill="x", pady=(0, 10))
        dot = _ck.Label(st, text="\u25cf", fg_color=CARD, text_color=MUT,
                       font=("Segoe UI", 14))
        dot.pack(side="left")
        status_var = tk.StringVar(value="Menginisialisasi...")
        _ck.Label(st, textvariable=status_var, fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 0))
        _ck.Button(st, text="  Refresh", fg_color=CARD2, text_color=FG,
                  font=("Segoe UI", 8), padx=10, pady=4,
                  command=lambda: _thr.Thread(
                      target=_refresh_devs, daemon=True).start(),
                  **_FB).pack(side="right")

        msg_var = tk.StringVar(value="")
        msg_lbl = _ck.Label(conn, textvariable=msg_var, fg_color=CARD, text_color="#7B7B9B",
                           font=("Segoe UI", 8), wraplength=560, justify="left")
        msg_lbl.pack(anchor="w", pady=(0, 8))

        # ── Device cards container ───────────────────────────────────────────
        cards_frame = _ck.Frame(conn, fg_color=CARD)
        cards_frame.pack(fill="x", pady=(0, 4))

        if not hasattr(self, "_scrcpy_map"):
            self._scrcpy_map = {}

        _card_widgets = {}

        empty_lbl = _ck.Label(cards_frame,
                             text="Tidak ada perangkat — sambungkan HP via USB atau WiFi", fg_color=CARD, text_color=MUT, font=("Segoe UI", 9, "italic"))
        empty_lbl.pack(anchor="w", pady=6)

        def _make_device_card(serial: str):
            is_wifi = ":" in serial
            accent_clr = "#7C3AED" if is_wifi else "#0EA5E9"

            card = _ck.Frame(cards_frame, fg_color="#16162a", bd=0)
            card.pack(fill="x", pady=(0, 6))

            _ck.Frame(card, fg_color=accent_clr, width=4).pack(side="left", fill="y")

            inner = _ck.Frame(card, fg_color="#16162a", padx=12, pady=10)
            inner.pack(side="left", fill="both", expand=True)

            row = _ck.Frame(inner, fg_color="#16162a")
            row.pack(fill="x")

            icon = "wifi" if is_wifi else "usb "
            mir_dot = _ck.Label(row, text="\u25cf", fg_color="#16162a", text_color=MUT,
                               font=("Segoe UI", 11))
            mir_dot.pack(side="left")
            _ck.Label(row, text="[{}]  {}".format(icon, serial), fg_color="#16162a", text_color=FG,
                     font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 0))
            mir_lbl = _ck.Label(row, text="", fg_color="#16162a", text_color=MUT,
                               font=("Segoe UI", 8))
            mir_lbl.pack(side="left", padx=(10, 0))

            btn_f = _ck.Frame(row, fg_color="#16162a")
            btn_f.pack(side="right")

            def _disc():
                def _bg():
                    if self._adb:
                        ok2, m2 = self._adb.disconnect(serial)
                        if self._root:
                            self._root.after(0, lambda: msg_var.set(m2))
                    _refresh_devs()
                _thr.Thread(target=_bg, daemon=True).start()

            stop_b = _ck.Button(btn_f, text="\u25a0  Stop", fg_color="#7F1D1D", text_color="white",
                               font=("Segoe UI", 8, "bold"),
                               padx=10, pady=5, state="disabled", **_FB,
                               command=lambda: _stop_mirror_serial(
                                   serial, start_b, stop_b, mir_dot, mir_lbl))
            stop_b.pack(side="right", padx=(4, 0))

            start_b = _ck.Button(btn_f, text="\u25b6  Mirror", fg_color="#14532D", text_color="white",
                                font=("Segoe UI", 8, "bold"),
                                padx=10, pady=5, **_FB,
                                command=lambda: _start_mirror_serial(
                                    serial, start_b, stop_b, mir_dot, mir_lbl))
            start_b.pack(side="right", padx=(4, 0))

            _ck.Button(btn_f, text="Putuskan", fg_color=CARD, text_color="#7B7B9B",
                      font=("Segoe UI", 8), padx=8, pady=5,
                      **_FB, command=_disc).pack(side="right", padx=(4, 0))

            if serial in self._scrcpy_map and self._scrcpy_map[serial].running:
                mir_dot.configure(text_color=GRN)
                mir_lbl.configure(text="Sedang mirror", text_color=GRN)
                start_b.configure(state="disabled", fg_color="#1A3A2A")
                stop_b.configure(state="normal", fg_color=RED)

            _card_widgets[serial] = {
                "card": card, "mir_dot": mir_dot,
                "mir_lbl": mir_lbl, "start_b": start_b, "stop_b": stop_b,
            }
            return card

        def _refresh_devs():
            if self._adb is None:
                return
            try:
                devs = self._adb.list_devices()
                vals = [d["serial"] for d in devs if d["state"] == "device"]
                def _apply():
                    for s in list(_card_widgets.keys()):
                        if s not in vals:
                            try:
                                _card_widgets[s]["card"].destroy()
                            except Exception:
                                pass
                            del _card_widgets[s]
                    new_devices = [s for s in vals if s not in _card_widgets]
                    for s in vals:
                        if s not in _card_widgets:
                            _make_device_card(s)
                    if vals:
                        empty_lbl.pack_forget()
                        status_var.set("{} perangkat terhubung".format(len(vals)))
                        dot.configure(text_color=GRN)
                        if new_devices:
                            first_serial = new_devices[0]
                            if self.config.get("remote.auto_bypass_secure", False):
                                def _do_bypass(s=first_serial):
                                    if self._adb:
                                        self._adb._run(
                                            "-s", s, "shell",
                                            "service", "call", "SurfaceFlinger",
                                            "1008", "i32", "0")
                                _thr.Thread(target=_do_bypass, daemon=True).start()
                            # Auto-install Synthex companion ke semua perangkat baru
                            if self.config.get("remote.auto_install_companion", True):
                                for _ns in new_devices:
                                    _thr.Thread(
                                        target=lambda s=_ns: self._auto_install_companion(s, msg_var),
                                        daemon=True).start()
                    else:
                        empty_lbl.pack(anchor="w", pady=6)
                        status_var.set("Tidak ada perangkat")
                        dot.configure(text_color=MUT)
                if self._root:
                    self._root.after(0, _apply)
            except Exception:
                pass

        # ── Mirror logic per device ──────────────────────────────────────────
        res_var   = tk.StringVar(value="1024")
        br_var    = tk.StringVar(value="8M")
        fps_var   = tk.StringVar(value="60")
        ori_var   = tk.StringVar(value="Auto")
        stay_var  = tk.BooleanVar(value=True)
        touch_var = tk.BooleanVar(value=False)
        top_var   = tk.BooleanVar(value=True)
        audio_var = tk.BooleanVar(value=False)

        def _start_mirror_serial(serial, start_b, stop_b, mir_dot, mir_lbl):
            from modules.remote_control import ScrcpyManager
            if serial not in self._scrcpy_map:
                self._scrcpy_map[serial] = ScrcpyManager(self._adb)
                if self._scrcpy:
                    self._scrcpy_map[serial].path = self._scrcpy.path
            scr = self._scrcpy_map[serial]
            if not scr.available:
                msg_var.set("scrcpy belum ada — klik Download dulu.")
                return
            try:
                max_size = int(res_var.get())
            except (ValueError, TypeError):
                max_size = 1024
            try:
                fps = int(fps_var.get())
            except (ValueError, TypeError):
                fps = 60
            ok, msg = scr.start(
                serial=serial,
                max_size=max_size,
                bitrate=br_var.get(),
                fps=fps,
                orientation=ori_var.get(),
                stay_awake=stay_var.get(),
                show_touches=touch_var.get(),
                always_on_top=top_var.get(),
                no_audio=audio_var.get(),
            )
            msg_var.set(msg)
            if ok:
                start_b.configure(state="disabled", fg_color="#1A3A2A")
                stop_b.configure(state="normal", fg_color=RED)
                mir_dot.configure(text_color=GRN)
                mir_lbl.configure(text="Sedang mirror", text_color=GRN)
                _poll_mirror_serial(serial, start_b, stop_b, mir_dot, mir_lbl)
                _open_control_panel(serial)

        def _stop_mirror_serial(serial, start_b, stop_b, mir_dot, mir_lbl):
            if serial in self._scrcpy_map:
                self._scrcpy_map[serial].stop()
            try:
                start_b.configure(state="normal", fg_color="#14532D")
                stop_b.configure(state="disabled", fg_color="#7F1D1D")
                mir_dot.configure(text_color=MUT)
                mir_lbl.configure(text="", text_color=MUT)
            except Exception:
                pass
            msg_var.set("Mirror {} dihentikan.".format(serial))

        def _poll_mirror_serial(serial, start_b, stop_b, mir_dot, mir_lbl):
            scr = self._scrcpy_map.get(serial)
            if scr is None or not scr.running:
                try:
                    start_b.configure(state="normal", fg_color="#14532D")
                    stop_b.configure(state="disabled", fg_color="#7F1D1D")
                    mir_dot.configure(text_color=MUT)
                    mir_lbl.configure(text="Selesai", text_color=MUT)
                except Exception:
                    pass
                return
            if self._root:
                self._root.after(800, lambda: _poll_mirror_serial(
                    serial, start_b, stop_b, mir_dot, mir_lbl))

        # ── Vysor-like Control Panel ─────────────────────────────────────────
        _ctrl_wins = {}

        def _open_control_panel(serial: str):
            if serial in _ctrl_wins:
                try:
                    if _ctrl_wins[serial].winfo_exists():
                        _ctrl_wins[serial].lift()
                        return
                except Exception:
                    pass

            adb = self._adb
            def _kev(code):
                def _do():
                    if adb:
                        adb._run("-s", serial, "shell", "input", "keyevent", str(code))
                        if self._macro_engine:
                            self._macro_engine.ping()
                _thr.Thread(target=_do, daemon=True).start()

            def _tap_input(text: str):
                def _do():
                    if adb and text.strip():
                        adb._run("-s", serial, "shell", "input", "text", text)
                        if self._macro_engine:
                            self._macro_engine.ping()
                _thr.Thread(target=_do, daemon=True).start()

            _screen_size = [None]  # cache (w, h)

            def _get_screen_size():
                if _screen_size[0]:
                    return _screen_size[0]
                try:
                    _, out, _ = adb._run("-s", serial, "shell",
                                         "wm", "size")
                    import re as _re
                    m = _re.search(r"(\d+)x(\d+)", out or "")
                    if m:
                        _screen_size[0] = (int(m.group(1)), int(m.group(2)))
                        return _screen_size[0]
                except Exception:
                    pass
                return (1080, 1920)

            def _swipe(fx1, fy1, fx2, fy2):
                def _do():
                    if adb:
                        w, h = _get_screen_size()
                        x1 = int(w * fx1)
                        y1 = int(h * fy1)
                        x2 = int(w * fx2)
                        y2 = int(h * fy2)
                        adb._run("-s", serial, "shell", "input", "swipe",
                                 str(x1), str(y1), str(x2), str(y2), "300")
                        if self._macro_engine:
                            self._macro_engine.ping()
                _thr.Thread(target=_do, daemon=True).start()

            win = ctk.CTkToplevel(self._root)
            win.withdraw()
            win.title("Synthex Control — {}".format(serial))
            win.configure(fg_color="#0D0D14")
            win.resizable(False, False)
            win.attributes("-topmost", True)
            _ico = _resolve_icon()
            if _ico:
                try: win.iconbitmap(_ico)
                except Exception: pass
            _ctrl_wins[serial] = win
            win.protocol("WM_DELETE_WINDOW", lambda: (
                _ctrl_wins.pop(serial, None), win.destroy()))

            # ── Header ──
            _ck.Frame(win, fg_color=ACC, height=3).pack(fill="x")
            hdr = _ck.Frame(win, fg_color="#111120", padx=12, pady=8)
            hdr.pack(fill="x")
            _ck.Label(hdr, text="⚡ Synthex Control", fg_color="#111120", text_color=ACC,
                     font=("Segoe UI", 10, "bold")).pack(side="left")
            _ck.Label(hdr, text=serial, fg_color="#111120", text_color=MUT,
                     font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))
            _ck.Button(hdr, text="✕", fg_color="#111120", text_color=MUT, relief="flat",
                      bd=0, font=("Segoe UI", 9), cursor="hand2",
                      command=win.destroy).pack(side="right")

            def _mbtn(parent, text, cmd, fg_color="#1c1c2e", text_color=FG, w=5):
                return _ck.Button(parent, text=text, command=cmd, fg_color=bg, text_color=fg, relief="flat", bd=0,
                                 font=("Segoe UI", 12), width=w,
                                 cursor="hand2", activebackground=ACC,
                                 activeforeground="white", pady=10)

            # ── Navigation row ──
            nav = _ck.Frame(win, fg_color="#0D0D14", pady=6)
            nav.pack(fill="x", padx=10)
            _ck.Label(nav, text="NAVIGASI", fg_color="#0D0D14", text_color="#444466",
                     font=("Segoe UI", 7, "bold")).pack(anchor="w", pady=(0, 4))
            nr = _ck.Frame(nav, fg_color="#0D0D14")
            nr.pack()
            for txt, code in [("◀  Back", 4), ("⏺  Home", 3), ("⬛  Recent", 187),
                               ("🔔  Notif", 83)]:
                _mbtn(nr, txt, lambda c=code: _kev(c), w=9).pack(
                    side="left", padx=2)

            _ck.Frame(win, fg_color="#1c1c2e", height=1).pack(fill="x", padx=10, pady=4)

            # ── Volume + Brightness row ──
            vb = _ck.Frame(win, fg_color="#0D0D14", padx=10)
            vb.pack(fill="x")
            _ck.Label(vb, text="VOLUME  &  BRIGHTNESS", fg_color="#0D0D14", text_color="#444466",
                     font=("Segoe UI", 7, "bold")).pack(anchor="w", pady=(0, 4))
            vr = _ck.Frame(vb, fg_color="#0D0D14")
            vr.pack()
            for txt, code in [("🔉 Vol−", 25), ("🔊 Vol+", 24),
                               ("🔅 Dim", 220), ("🔆 Bright", 221)]:
                _mbtn(vr, txt, lambda c=code: _kev(c), w=9).pack(
                    side="left", padx=2)

            _ck.Frame(win, fg_color="#1c1c2e", height=1).pack(fill="x", padx=10, pady=4)

            # ── System row ──
            sys_f = _ck.Frame(win, fg_color="#0D0D14", padx=10)
            sys_f.pack(fill="x")
            _ck.Label(sys_f, text="SISTEM", fg_color="#0D0D14", text_color="#444466",
                     font=("Segoe UI", 7, "bold")).pack(anchor="w", pady=(0, 4))
            sr = _ck.Frame(sys_f, fg_color="#0D0D14")
            sr.pack()
            for txt, cmd in [
                ("🔒 Lock",     lambda: _kev(26)),
                ("📸 SS",       lambda: _kev(120)),
                ("⬆ Swipe Up",  lambda: _swipe(0.5, 0.85, 0.5, 0.2)),
                ("⬇ Notif Bar", lambda: _swipe(0.5, 0.01, 0.5, 0.5)),
            ]:
                _mbtn(sr, txt, cmd, w=9).pack(side="left", padx=2)

            _ck.Frame(win, fg_color="#1c1c2e", height=1).pack(fill="x", padx=10, pady=4)

            # ── Text input ──
            ti = _ck.Frame(win, fg_color="#0D0D14", padx=10, pady=6)
            ti.pack(fill="x")
            _ck.Label(ti, text="KIRIM TEKS KE HP", fg_color="#0D0D14", text_color="#444466",
                     font=("Segoe UI", 7, "bold")).pack(anchor="w", pady=(0, 4))
            ti_row = _ck.Frame(ti, fg_color="#0D0D14")
            ti_row.pack(fill="x")
            ti_var = tk.StringVar()
            ti_entry = _ck.Entry(ti_row, textvariable=ti_var, fg_color="#16162a", text_color=FG,
                                insertbackground=FG, relief="flat",
                                font=("Segoe UI", 10), bd=6)
            ti_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
            _ck.Button(ti_row, text="Kirim", fg_color=ACC, text_color="white",
                      relief="flat", bd=0, font=("Segoe UI", 9, "bold"),
                      padx=10, cursor="hand2",
                      command=lambda: (_tap_input(ti_var.get()), ti_var.set("")),
                      ).pack(side="left")
            _ck.Button(ti_row, text="⌫ Del", fg_color="#2A1A1A", text_color=RED,
                      relief="flat", bd=0, font=("Segoe UI", 9),
                      padx=8, cursor="hand2",
                      command=lambda: _kev(67),
                      ).pack(side="left", padx=(4, 0))
            ti_entry.bind("<Return>", lambda e: (_tap_input(ti_var.get()), ti_var.set("")))

            _ck.Frame(win, fg_color="#0D0D14", height=8).pack()
            win.update()
            win.deiconify()

        # ── Wireless Connect ─────────────────────────────────────────────────
        _ck.Frame(conn, fg_color=CARD2, height=1).pack(fill="x", pady=(4, 10))

        # IP history helpers
        def _get_ip_history() -> list:
            return self.config.get("remote.ip_history", [])

        def _save_ip_to_history(ip: str):
            hist = _get_ip_history()
            if ip in hist:
                hist.remove(ip)
            hist.insert(0, ip)
            self.config.set("remote.ip_history", hist[:5])
            self.config.save()
            _refresh_history_btns()

        # Input row
        ip_row = _ck.Frame(conn, fg_color=CARD)
        ip_row.pack(fill="x", pady=(0, 4))
        _ck.Label(ip_row, text="IP HP:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        ip_var = tk.StringVar(value=self.config.get("remote.last_ip", ""))
        _ck.Entry(ip_row, textvariable=ip_var, fg_color="#16162a", text_color=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 10),
                 width=18, bd=4).pack(side="left", padx=(6, 4))
        _ck.Label(ip_row, text="Port:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        port_var = tk.StringVar(value=str(self.config.get("remote.last_port", "5555")))
        _ck.Entry(ip_row, textvariable=port_var, fg_color="#16162a", text_color=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 10),
                 width=6, bd=4).pack(side="left", padx=(4, 10))

        def _connect_bg(ip_override=None):
            ip = (ip_override or ip_var.get()).strip()
            if not ip:
                if self._root:
                    self._root.after(0, lambda: msg_var.set("Masukkan IP address HP."))
                return
            try:
                port = int(port_var.get().strip())
            except ValueError:
                port = 5555
            if self._root:
                self._root.after(0, lambda: msg_var.set(
                    "Menghubungkan ke {}:{}...".format(ip, port)))
            if self._adb is None:
                return
            ok, msg = self._adb.connect(ip, port)
            if ok:
                self.config.set("remote.last_ip", ip)
                self.config.set("remote.last_port", str(port))
                if self._root:
                    self._root.after(0, lambda: ip_var.set(ip))
                _save_ip_to_history(ip)
            if self._root:
                self._root.after(0, lambda: msg_var.set(msg))
            _refresh_devs()

        _ck.Button(ip_row, text="⚡ Hubungkan", fg_color=ACC, text_color="white",
                  font=("Segoe UI", 9, "bold"), padx=14, pady=6,
                  command=lambda: _thr.Thread(
                      target=_connect_bg, daemon=True).start(),
                  **_FB).pack(side="left")

        # IP history quick-connect buttons
        hist_frame = _ck.Frame(conn, fg_color=CARD)
        hist_frame.pack(fill="x", pady=(0, 4))

        def _refresh_history_btns():
            for w in hist_frame.winfo_children():
                w.destroy()
            hist = _get_ip_history()
            if not hist:
                return
            _ck.Label(hist_frame, text="Terakhir:", fg_color=CARD, text_color=MUT,
                     font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))
            for saved_ip in hist:
                def _quick(ip=saved_ip):
                    ip_var.set(ip)
                    _thr.Thread(target=lambda: _connect_bg(ip),
                                daemon=True).start()
                _ck.Button(hist_frame, text=saved_ip, fg_color="#1A1A38", text_color=BLUE,
                          font=("Segoe UI", 8), padx=8, pady=3,
                          relief="flat", cursor="hand2",
                          command=_quick).pack(side="left", padx=(0, 4))

        _refresh_history_btns()

        # ── USB Wireless Setup ───────────────────────────────────────────────
        _ck.Frame(conn, fg_color=CARD2, height=1).pack(fill="x", pady=(8, 8))

        setup_hdr = _ck.Frame(conn, fg_color=CARD)
        setup_hdr.pack(fill="x", pady=(0, 6))
        _ck.Label(setup_hdr, text="Setup Wireless Debugging", fg_color=CARD, text_color=FG, font=("Segoe UI", 9, "bold")).pack(side="left")

        steps_frame = _ck.Frame(conn, fg_color="#12121E")
        steps_frame.pack(fill="x", pady=(0, 8))
        steps = [
            ("1", "Colok HP ke PC via USB"),
            ("2", "Klik tombol di bawah → ADB aktif via WiFi"),
            ("3", "Cabut USB → klik Mulai Mirror"),
        ]
        for num, txt in steps:
            row_s = _ck.Frame(steps_frame, fg_color="#12121E", padx=10, pady=4)
            row_s.pack(fill="x")
            _ck.Label(row_s, text=num, fg_color=ACC, text_color="white",
                     font=("Segoe UI", 8, "bold"),
                     width=2, anchor="center").pack(side="left")
            _ck.Label(row_s, text="  " + txt, fg_color="#12121E", text_color=MUT,
                     font=("Segoe UI", 9)).pack(side="left")

        usb_row = _ck.Frame(conn, fg_color=CARD)
        usb_row.pack(fill="x")
        _ck.Button(usb_row, text="⚙ Setup Wireless via USB", fg_color="#3A1060", text_color="white",
                  font=("Segoe UI", 9, "bold"), padx=14, pady=6,
                  command=lambda: _thr.Thread(
                      target=_usb_setup_bg, daemon=True).start(),
                  **_FB).pack(side="left", padx=(0, 10))
        _ck.Label(usb_row,
                 text="HP harus sudah di-authorize USB debugging", fg_color=CARD, text_color="#4A4A6A", font=("Segoe UI", 8)).pack(side="left")

        def _usb_setup_bg():
            if self._root:
                self._root.after(0, lambda: msg_var.set(
                    "Menjalankan adb tcpip 5555..."))
            if self._adb is None:
                if self._root:
                    self._root.after(0, lambda: msg_var.set(
                        "ADB tidak ditemukan — download ADB dulu."))
                return
            ok, m = self._adb.tcpip(5555)
            if not ok:
                if self._root:
                    self._root.after(0, lambda: msg_var.set("Gagal: " + m))
                return
            import time as _t; _t.sleep(1)
            ip = self._adb.get_device_ip()
            if ip:
                self.config.set("remote.last_ip", ip)
                self.config.save()
                if self._root:
                    self._root.after(0, lambda: ip_var.set(ip))
                    self._root.after(0, lambda: _show_unplug_dialog(ip))
            else:
                if self._root:
                    self._root.after(0, lambda: msg_var.set(
                        "tcpip OK, IP tidak terdeteksi — isi manual lalu klik Tambah HP."))
            _refresh_devs()

        def _show_unplug_dialog(ip: str):
            dlg = ctk.CTkToplevel(self._root)
            dlg.withdraw()
            dlg.attributes("-topmost", True)
            dlg.configure(fg_color="#0D0D14")
            dlg.resizable(False, False)
            _ck.Frame(dlg, fg_color="#7C3AED", height=4).pack(fill="x")
            _b = _ck.Frame(dlg, fg_color="#0D0D14", padx=28, pady=20)
            _b.pack(fill="both", expand=True)
            _ck.Label(_b, text="WiFi Siap!", fg_color="#0D0D14", text_color="white",
                     font=("Segoe UI", 13, "bold")).pack(anchor="w")
            _ck.Label(_b, text="{}:5555".format(ip), fg_color="#0D0D14", text_color="#7C3AED",
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 2))
            _ck.Label(_b, text="Cabut kabel USB, lalu klik Mulai Mirror.", fg_color="#0D0D14", text_color="#8080A0",
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 16))
            br = _ck.Frame(_b, fg_color="#0D0D14")
            br.pack(anchor="e")

            def _do_connect_mirror():
                dlg.destroy()
                msg_var.set("Memeriksa {}:5555...".format(ip))
                def _bg():
                    import time as _t2
                    target = "{}:5555".format(ip)
                    _t2.sleep(2)
                    probe = self._adb.probe_port(ip, 5555, timeout=3.0)
                    if probe == "refused":
                        if self._root:
                            self._root.after(0, lambda: msg_var.set(
                                "Port 5555 ditolak HP. Aktifkan Wireless Debugging di Developer Options."))
                        return
                    if probe == "timeout":
                        if self._root:
                            self._root.after(0, lambda: msg_var.set(
                                "Timeout. Cek: HP & PC di jaringan sama? "
                                "Router AP Isolation aktif?"))
                        return
                    ok2 = False; m2 = ""
                    for attempt in range(4):
                        ok2, m2 = self._adb.connect(ip, 5555)
                        if ok2:
                            break
                        if self._root:
                            self._root.after(0, lambda a=attempt: msg_var.set(
                                "Mencoba... ({}/4)".format(a + 1)))
                        _t2.sleep(1.5)
                    if self._root:
                        self._root.after(0, lambda: msg_var.set(m2))
                    if ok2:
                        _refresh_devs()
                        _t2.sleep(0.6)
                        if self._root:
                            self._root.after(0, lambda: _auto_mirror(target))
                import threading as _thr2
                _thr2.Thread(target=_bg, daemon=True).start()

            def _auto_mirror(serial):
                w = _card_widgets.get(serial)
                if w:
                    _start_mirror_serial(
                        serial, w["start_b"], w["stop_b"],
                        w["mir_dot"], w["mir_lbl"])

            _ck.Button(br, text="Mulai Mirror", fg_color="#7C3AED", text_color="white",
                      font=("Segoe UI", 9, "bold"), padx=18, pady=7,
                      relief="flat", cursor="hand2",
                      command=_do_connect_mirror).pack(side="left", padx=(0, 8))
            _ck.Button(br, text="Tutup", fg_color="#1c1c2e", text_color="#8080A0",
                      font=("Segoe UI", 9), padx=12, pady=7,
                      relief="flat", cursor="hand2",
                      command=dlg.destroy).pack(side="left")
            dlg.update_idletasks()
            sw = dlg.winfo_screenwidth(); sh = dlg.winfo_screenheight()
            dlg.geometry("+{}+{}".format(
                (sw - dlg.winfo_width()) // 2,
                (sh - dlg.winfo_height()) // 2))
            dlg.update()
            dlg.deiconify()
            dlg.grab_set()

        # ══════════════════════════════════════════════════════════════
        # SECTION — Beda Jaringan? Solusi Koneksi
        # ══════════════════════════════════════════════════════════════
        net = _sec("Beda Jaringan? Solusi Koneksi", accent="#1A2A0A",
                   subtitle="LAN ≠ WiFi — pakai cara ini")

        # ── Mode 1: USB Direct ───────────────────────────────────────────────
        usb_card = _ck.Frame(net, fg_color="#111820", padx=14, pady=10)
        usb_card.pack(fill="x", pady=(0, 8))
        _ck.Frame(usb_card, fg_color="#0EA5E9", width=3).pack(side="left", fill="y")
        usb_inner = _ck.Frame(usb_card, fg_color="#111820", padx=12)
        usb_inner.pack(side="left", fill="both", expand=True)
        _ck.Label(usb_inner, text="🔌  Mode 1 — USB Direct (Paling Simpel)", fg_color="#111820", text_color=FG, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        _ck.Label(usb_inner,
                 text="Hubungkan HP ke PC via kabel USB. ADB & scrcpy otomatis\n"
                      "berjalan lewat USB — tidak perlu WiFi sama sekali.", fg_color="#111820", text_color=MUT, font=("Segoe UI", 8), justify="left").pack(anchor="w", pady=(2, 6))
        usb_steps = [
            "1. Aktifkan Developer Options di HP (ketuk Build Number 7x)",
            "2. Aktifkan USB Debugging",
            "3. Colok kabel USB ke PC",
            "4. Izinkan USB Debugging saat muncul popup di HP",
            "5. Klik Refresh di atas — HP muncul sebagai [usb]",
        ]
        for s in usb_steps:
            _ck.Label(usb_inner, text=s, fg_color="#111820", text_color="#8888AA",
                     font=("Segoe UI", 8)).pack(anchor="w")

        # ── Mode 2: USB Tethering ────────────────────────────────────────────
        teth_card = _ck.Frame(net, fg_color="#111820", padx=14, pady=10)
        teth_card.pack(fill="x", pady=(0, 8))
        _ck.Frame(teth_card, fg_color="#7C3AED", width=3).pack(side="left", fill="y")
        teth_inner = _ck.Frame(teth_card, fg_color="#111820", padx=12)
        teth_inner.pack(side="left", fill="both", expand=True)
        _ck.Label(teth_inner, text="📡  Mode 2 — USB Tethering (Wireless ADB via USB)", fg_color="#111820", text_color=FG, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        _ck.Label(teth_inner,
                 text="HP berbagi jaringan ke PC via USB → PC dan HP jadi satu subnet.\n"
                      "Setelah itu bisa pakai ADB wireless di IP yang didapat.", fg_color="#111820", text_color=MUT, font=("Segoe UI", 8), justify="left").pack(anchor="w", pady=(2, 6))
        teth_steps = [
            "1. Colok kabel USB ke PC",
            "2. Di HP: Settings → Hotspot & Tethering → USB Tethering → ON",
            "3. PC dapat IP dari HP (misal 192.168.x.x di adapter baru)",
            "4. ADB otomatis jalan lewat USB — atau klik 'Deteksi IP HP'",
        ]
        for s in teth_steps:
            _ck.Label(teth_inner, text=s, fg_color="#111820", text_color="#8888AA",
                     font=("Segoe UI", 8)).pack(anchor="w")

        def _detect_usb_ip():
            def _bg():
                if not self._adb:
                    return
                ip = self._adb.get_device_ip()
                devs = self._adb.list_devices()
                usb_devs = [d["serial"] for d in devs
                            if d["state"] == "device" and ":" not in d["serial"]]
                if ip and usb_devs:
                    if self._root:
                        self._root.after(0, lambda: (
                            ip_var.set(ip),
                            msg_var.set("IP HP terdeteksi: {} (dari USB device {})".format(
                                ip, usb_devs[0]))))
                elif usb_devs:
                    if self._root:
                        self._root.after(0, lambda: msg_var.set(
                            "Device USB ada ({}) tapi IP tidak terdeteksi. "
                            "Pastikan USB Tethering atau WiFi aktif di HP.".format(usb_devs[0])))
                else:
                    if self._root:
                        self._root.after(0, lambda: msg_var.set(
                            "Tidak ada device USB. Colok kabel dulu."))
            _thr.Thread(target=_bg, daemon=True).start()

        teth_btn_row = _ck.Frame(teth_inner, fg_color="#111820")
        teth_btn_row.pack(anchor="w", pady=(6, 0))
        _ck.Button(teth_btn_row, text="🔍 Deteksi IP HP via USB", fg_color="#7C3AED", text_color="white", relief="flat", bd=0,
                  font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                  cursor="hand2", command=_detect_usb_ip).pack(side="left", padx=(0, 8))

        # ── Mode 3: Windows Hotspot ──────────────────────────────────────────
        hs_card = _ck.Frame(net, fg_color="#111820", padx=14, pady=10)
        hs_card.pack(fill="x", pady=(0, 4))
        _ck.Frame(hs_card, fg_color=GRN, width=3).pack(side="left", fill="y")
        hs_inner = _ck.Frame(hs_card, fg_color="#111820", padx=12)
        hs_inner.pack(side="left", fill="both", expand=True)
        _ck.Label(hs_inner, text="📶  Mode 3 — Windows Mobile Hotspot (LAN → WiFi)", fg_color="#111820", text_color=FG, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        _ck.Label(hs_inner,
                 text="PC bagikan koneksi LAN sebagai WiFi hotspot → HP connect ke hotspot PC\n"
                      "→ HP & PC satu subnet → ADB wireless normal.", fg_color="#111820", text_color=MUT, font=("Segoe UI", 8), justify="left").pack(anchor="w", pady=(2, 6))

        def _open_hotspot_settings():
            import subprocess as _sp
            try:
                _sp.Popen(["ms-settings:network-mobilehotspot"], shell=True)
            except Exception:
                try:
                    _sp.Popen(["control", "/name", "Microsoft.NetworkAndSharingCenter"],
                              creationflags=_sp.CREATE_NO_WINDOW)
                except Exception:
                    pass

        _ck.Button(hs_inner, text="⚙ Buka Settings Hotspot Windows", fg_color=GRN, text_color="#000", relief="flat", bd=0,
                  font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                  cursor="hand2", command=_open_hotspot_settings).pack(anchor="w")
        _ck.Label(hs_inner,
                 text="Setelah HP connect ke hotspot PC, HP dapat IP 192.168.137.x — masukkan ke kolom IP di bawah.", fg_color="#111820", text_color="#555577", font=("Segoe UI", 7)).pack(anchor="w", pady=(4, 0))

        # ══════════════════════════════════════════════════════════════
        # SECTION 2 — Pengaturan Mirror (shared untuk semua HP)
        # ══════════════════════════════════════════════════════════════
        mir = _sec("Pengaturan Mirror", accent="#0A2A18")

        def _lbl_cb(parent, lbl, var, vals, w=8):
            _ck.Label(parent, text=lbl, fg_color=CARD, text_color=MUT,
                     font=("Segoe UI", 9)).pack(side="left")
            _ck.Combobox(parent, textvariable=var, values=vals,
                         state="readonly", width=w).pack(
                side="left", padx=(4, 14))

        row1 = _ck.Frame(mir, fg_color=CARD)
        row1.pack(fill="x", pady=(0, 10))
        _lbl_cb(row1, "Resolusi:", res_var,
                ["480", "720", "1024", "1280", "1920"], w=6)
        _lbl_cb(row1, "Bitrate:",  br_var,
                ["2M", "4M", "8M", "16M", "32M"],      w=5)
        _lbl_cb(row1, "FPS:",      fps_var,
                ["24", "30", "45", "60"],               w=4)
        _lbl_cb(row1, "Orientasi:", ori_var,
                ["Auto", "Portrait", "Landscape"],      w=9)

        row2 = _ck.Frame(mir, fg_color=CARD)
        row2.pack(fill="x", pady=(0, 12))
        for _txt, _v in [
            ("Stay Awake", stay_var), ("Show Touches", touch_var),
            ("Always On Top", top_var), ("No Audio", audio_var),
        ]:
            _ck.Checkbutton(row2, text=_txt, variable=_v, fg_color=CARD, text_color=FG, selectcolor=CARD2,
                           activebackground=CARD, activeforeground=FG,
                           font=("Segoe UI", 9)).pack(side="left", padx=(0, 14))

        # ── Tool status bars ─────────────────────────────────────────────────
        def _dl_zip(url, tdir, label_var, strip_root=True, on_done=None):
            def _do():
                import urllib.request as _ur
                import zipfile as _zf
                import os as _o
                _o.makedirs(tdir, exist_ok=True)
                zpath = _o.path.join(tdir, "_download.zip")
                try:
                    def _reporthook(count, bs, total):
                        if total > 0 and self._root:
                            pct = min(int(count * bs * 100 / total), 99)
                            self._root.after(0, lambda p=pct:
                                label_var.set("Mengunduh {}%...".format(p)))
                    _ur.urlretrieve(url, zpath, reporthook=_reporthook)
                    if self._root:
                        self._root.after(0, lambda: label_var.set("Mengekstrak..."))
                    with _zf.ZipFile(zpath, "r") as z:
                        for m in z.namelist():
                            parts = m.split("/", 1)
                            tgt = (parts[1] if strip_root and len(parts) > 1
                                   else parts[0])
                            if not tgt:
                                continue
                            dest = _o.path.join(tdir, tgt)
                            if m.endswith("/"):
                                _o.makedirs(dest, exist_ok=True)
                            else:
                                _o.makedirs(_o.path.dirname(dest), exist_ok=True)
                                with z.open(m) as src, open(dest, "wb") as out:
                                    out.write(src.read())
                    _o.remove(zpath)
                    if self._root:
                        self._root.after(0, lambda: label_var.set("Selesai!"))
                    if on_done:
                        on_done()
                except Exception as ex:
                    if self._root:
                        self._root.after(0, lambda e=str(ex)[:60]:
                                         label_var.set("Gagal: " + e))
            _thr.Thread(target=_do, daemon=True).start()

        def _tools_base():
            import sys as _sy, os as _o
            return (_o.path.dirname(_sy.executable)
                    if getattr(_sy, "frozen", False)
                    else _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))

        tools_bar = _ck.Frame(mir, fg_color="#0E0E1C", padx=10, pady=8)
        tools_bar.pack(fill="x")

        scrcpy_sv = tk.StringVar(value="scrcpy: memeriksa...")
        scrcpy_lbl = _ck.Label(tools_bar, textvariable=scrcpy_sv, fg_color="#0E0E1C", text_color=MUT, font=("Segoe UI", 8))
        scrcpy_lbl.pack(side="left")

        dl_sv = tk.StringVar(value="")
        _ck.Label(tools_bar, textvariable=dl_sv, fg_color="#0E0E1C", text_color=YEL,
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))

        adb_sv = tk.StringVar(value="  |  ADB: memeriksa...")
        adb_lbl = _ck.Label(tools_bar, textvariable=adb_sv, fg_color="#0E0E1C", text_color=MUT, font=("Segoe UI", 8))
        adb_lbl.pack(side="left", padx=(6, 0))

        def _upd_scrcpy():
            if self._scrcpy and self._scrcpy.available:
                scrcpy_sv.set("scrcpy: siap")
                scrcpy_lbl.configure(text_color=GRN)
                for sm in self._scrcpy_map.values():
                    sm.path = self._scrcpy.path
            else:
                scrcpy_sv.set("scrcpy: belum ada")
                scrcpy_lbl.configure(text_color=YEL)

        def _download_scrcpy():
            dl_sv.set("Mengunduh scrcpy...")
            SCRCPY_URL = ("https://github.com/Genymobile/scrcpy/releases/"
                          "download/v3.1/scrcpy-win64-v3.1.zip")
            tdir = os.path.join(_tools_base(), "tools", "scrcpy")
            def _after():
                from modules.remote_control import _find_scrcpy
                if self._scrcpy:
                    self._scrcpy.path = _find_scrcpy()
                if self._root:
                    self._root.after(0, _upd_scrcpy)
            _dl_zip(SCRCPY_URL, tdir, dl_sv, strip_root=True, on_done=_after)

        def _download_adb():
            adb_sv.set("  |  ADB: mengunduh...")
            ADB_URL = ("https://dl.google.com/android/repository/"
                       "platform-tools-latest-windows.zip")
            tdir = os.path.join(_tools_base(), "tools", "platform-tools")
            def _after():
                from modules.remote_control import _find_adb
                if self._adb:
                    self._adb.adb = _find_adb()
                if self._root:
                    self._root.after(0, lambda: [
                        adb_sv.set("  |  ADB: siap"),
                        adb_lbl.configure(text_color=GRN),
                        _refresh_devs() if self._adb and self._adb.available else None,
                    ])
            _dl_zip(ADB_URL, tdir, adb_sv, strip_root=True, on_done=_after)

        dl_btns = _ck.Frame(tools_bar, fg_color="#0E0E1C")
        dl_btns.pack(side="right")
        _ck.Button(dl_btns, text="Download scrcpy", fg_color="#2A1050", text_color="white",
                  font=("Segoe UI", 8), padx=8, pady=4,
                  command=_download_scrcpy, **_FB).pack(side="left", padx=(0, 4))
        _ck.Button(dl_btns, text="Download ADB", fg_color="#103020", text_color="white",
                  font=("Segoe UI", 8), padx=8, pady=4,
                  command=_download_adb, **_FB).pack(side="left")

        # ── Screenshot button ────────────────────────────────────────────────
        ss_row = _ck.Frame(mir, fg_color=CARD)
        ss_row.pack(fill="x", pady=(8, 0))
        ss_sv = tk.StringVar(value="")
        _ck.Label(ss_row, textvariable=ss_sv, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(side="left")

        def _take_screenshot():
            if not self._adb or not self._adb.available:
                ss_sv.set("ADB tidak tersedia.")
                return
            devs_now = self._adb.list_devices()
            serials = [d["serial"] for d in devs_now if d["state"] == "device"]
            if not serials:
                ss_sv.set("Tidak ada perangkat terhubung.")
                return
            # Prefer device that is currently mirroring
            mirroring = [s for s in serials
                         if s in self._scrcpy_map and self._scrcpy_map[s].running]
            serial = mirroring[0] if mirroring else serials[0]
            import datetime as _dt2, os as _os2
            ss_dir = os.path.join(os.path.expanduser("~"), "Pictures", "Synthex Screenshots")
            _os2.makedirs(ss_dir, exist_ok=True)
            fname = "ss_{}.png".format(
                _dt2.datetime.now().strftime("%Y%m%d_%H%M%S"))
            local = _os2.path.join(ss_dir, fname)
            ss_sv.set("Mengambil screenshot...")
            def _bg():
                rc, _, err = self._adb._run(
                    "-s", serial, "shell",
                    "screencap", "-p", "/sdcard/_sx_ss.png")
                if rc != 0:
                    if self._root:
                        self._root.after(0, lambda: ss_sv.set("Gagal: " + err[:60]))
                    return
                rc2, _, err2 = self._adb._run(
                    "-s", serial, "pull", "/sdcard/_sx_ss.png", local,
                    timeout=15)
                if rc2 == 0:
                    if self._root:
                        self._root.after(0, lambda: ss_sv.set(
                            "Tersimpan: {}".format(local)))
                    import subprocess as _sp
                    _sp.Popen(["explorer", "/select,", local],
                              creationflags=_sp.CREATE_NO_WINDOW)
                else:
                    if self._root:
                        self._root.after(0, lambda: ss_sv.set("Pull gagal: " + err2[:60]))
            _thr.Thread(target=_bg, daemon=True).start()

        _ck.Button(ss_row, text="\U0001f4f7  Screenshot HP", fg_color="#1A3A5A", text_color="white",
                  font=("Segoe UI", 9, "bold"), padx=14, pady=6,
                  relief="flat", bd=0, cursor="hand2",
                  command=_take_screenshot).pack(side="right")

        # ══════════════════════════════════════════════════════════════
        # ══════════════════════════════════════════════════════════════
        # SECTION — Tailscale (beda jaringan, tanpa kabel)
        # ══════════════════════════════════════════════════════════════
        ts_sec = _sec("Tailscale — Wireless Tanpa Kabel & Beda Jaringan",
                      accent="#5B21B6", subtitle="VPN mesh langsung peer-to-peer")

        ts_status_var = tk.StringVar(value="Belum dicek…")
        ts_status_lbl = _ck.Label(ts_sec, textvariable=ts_status_var, fg_color=CARD, text_color=MUT, font=("Segoe UI", 8))
        ts_status_lbl.pack(anchor="w", pady=(0, 8))

        ts_peers_frame = _ck.Frame(ts_sec, fg_color=CARD)
        ts_peers_frame.pack(fill="x")

        def _tailscale_cmd(*args, timeout=5):
            import subprocess as _sp, shutil
            ts = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
            if not ts:
                return None, "Tailscale tidak ditemukan"
            try:
                r = _sp.run([ts] + list(args), capture_output=True, text=True,
                            timeout=timeout,
                            creationflags=_sp.CREATE_NO_WINDOW if os.name=="nt" else 0)
                return r.stdout.strip(), r.stderr.strip()
            except FileNotFoundError:
                return None, "Tailscale tidak terinstall"
            except Exception as e:
                return None, str(e)

        def _refresh_tailscale():
            def _bg():
                import json as _j
                out, err = _tailscale_cmd("status", "--json")
                if out is None:
                    def _ui():
                        ts_status_var.set("❌ " + err)
                        ts_status_lbl.configure(text_color=RED)
                        for w in ts_peers_frame.winfo_children(): w.destroy()
                        _ck.Label(ts_peers_frame,
                                 text="Download Tailscale di tailscale.com, install di PC & HP.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w")
                    if self._root: self._root.after(0, _ui)
                    return
                try:
                    data = _j.loads(out)
                except Exception:
                    if self._root:
                        self._root.after(0, lambda: ts_status_var.set("❌ Gagal parse status Tailscale"))
                    return

                self_node = data.get("Self", {})
                peers = data.get("Peer", {})
                my_ip = (self_node.get("TailscaleIPs") or ["?"])[0]

                peer_list = []
                for node_id, peer in peers.items():
                    if not peer.get("Active", False) and not peer.get("Online", False):
                        continue
                    ips = peer.get("TailscaleIPs", [])
                    if not ips:
                        continue
                    peer_list.append({
                        "name": peer.get("HostName", peer.get("DNSName", node_id)),
                        "ip":   ips[0],
                        "os":   peer.get("OS", ""),
                        "online": peer.get("Online", False),
                    })

                def _ui():
                    ts_status_var.set("✅ Tailscale aktif  •  IP PC kamu: {}".format(my_ip))
                    ts_status_lbl.configure(text_color=GRN)
                    for w in ts_peers_frame.winfo_children():
                        w.destroy()
                    if not peer_list:
                        _ck.Label(ts_peers_frame,
                                 text="Tidak ada peer online. Pastikan Tailscale aktif di HP juga.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w")
                        return
                    for p in peer_list:
                        row = _ck.Frame(ts_peers_frame, fg_color="#16162a", pady=6, padx=10)
                        row.pack(fill="x", pady=(0, 4))
                        clr = GRN if p["online"] else MUT
                        dot_t = "🟢" if p["online"] else "⚪"
                        _ck.Label(row, text=dot_t, fg_color="#16162a",
                                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))
                        info = _ck.Frame(row, fg_color="#16162a")
                        info.pack(side="left", fill="both", expand=True)
                        _ck.Label(info, text=p["name"], fg_color="#16162a", text_color=FG,
                                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
                        _ck.Label(info, text="{} • {}".format(p["ip"], p["os"]), fg_color="#16162a", text_color=MUT,
                                 font=("Segoe UI", 8)).pack(anchor="w")
                        def _connect_ts(ip=p["ip"], name=p["name"]):
                            def _auto_mirror(serial, attempt=0):
                                if serial in _card_widgets:
                                    w = _card_widgets[serial]
                                    _start_mirror_serial(serial, w["start_b"], w["stop_b"],
                                                         w["mir_dot"], w["mir_lbl"])
                                elif attempt < 15 and self._root:
                                    self._root.after(200, lambda: _auto_mirror(serial, attempt + 1))
                            def _do():
                                if not self._adb:
                                    return
                                # Enable tcpip mode on any USB-connected device first
                                usb_devs = [d["serial"] for d in self._adb.list_devices()
                                            if d["state"]=="device" and ":"not in d["serial"]]
                                if usb_devs:
                                    self._adb.tcpip(5555)
                                    import time as _t; _t.sleep(1)
                                ok, msg = self._adb.connect(ip, 5555)
                                serial_ts = "{}:5555".format(ip)
                                def _ui2():
                                    msg_var.set("Tailscale → {}: {}".format(name, msg))
                                    _thr.Thread(target=_refresh_devs, daemon=True).start()
                                    if ok:
                                        self._root.after(300, lambda: _auto_mirror(serial_ts))
                                if self._root: self._root.after(0, _ui2)
                            _thr.Thread(target=_do, daemon=True).start()
                        _ck.Button(row, text="⚡ Connect ADB", fg_color="#5B21B6", text_color="white", relief="flat", bd=0,
                                  font=("Segoe UI", 8, "bold"), padx=10, pady=4,
                                  cursor="hand2", command=_connect_ts).pack(side="right")
                if self._root: self._root.after(0, _ui)
            _thr.Thread(target=_bg, daemon=True).start()

        ts_btn_row = _ck.Frame(ts_sec, fg_color=CARD)
        ts_btn_row.pack(anchor="w", pady=(8, 4))
        _ck.Button(ts_btn_row, text="🔍 Cek & Tampilkan Peers Tailscale", fg_color="#5B21B6", text_color="white", relief="flat", bd=0,
                  font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                  cursor="hand2", command=_refresh_tailscale).pack(side="left", padx=(0, 8))
        _ck.Label(ts_sec,
                 text="💡 Install Tailscale di PC (tailscale.com) + di HP (Play Store) → login akun sama → klik Cek.", fg_color=CARD, text_color="#555577", font=("Segoe UI", 7)).pack(anchor="w")

        _refresh_tailscale()

        # SECTION 3 — Tools
        # ══════════════════════════════════════════════════════════════
        tools_sec = _sec("Tools", accent="#1A1A0A")

        secure_sv = tk.StringVar(value="")
        secure_row = _ck.Frame(tools_sec, fg_color=CARD)
        secure_row.pack(fill="x", pady=(0, 6))

        _ck.Label(secure_row,
                 text="Layar hitam saat buka app bank di mirror?", fg_color=CARD, text_color=MUT, font=("Segoe UI", 9)).pack(side="left")

        _ck.Label(tools_sec, textvariable=secure_sv, fg_color=CARD, text_color=YEL, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        def _run_surface_cmd(flag: str, ok_msg: str):
            devs = list(_card_widgets.keys())
            serial = devs[0] if devs else None
            if not serial or self._adb is None:
                secure_sv.set("Tidak ada perangkat terhubung.")
                return
            def _bg():
                try:
                    rc, _, err = self._adb._run(
                        "-s", serial, "shell",
                        "service", "call", "SurfaceFlinger", "1008", "i32", flag)
                    msg = ok_msg if rc == 0 else "Gagal: {}".format((err or "rc={}".format(rc))[:60])
                except Exception as ex:
                    msg = "Error: {}".format(str(ex)[:60])
                if self._root:
                    self._root.after(0, lambda m=msg: secure_sv.set(m))
            _thr.Thread(target=_bg, daemon=True).start()

        def _bypass_secure(silent=False):
            _run_surface_cmd("0", "" if silent else "Bypass aktif — layar hitam tidak akan muncul lagi.")

        def _restore_secure():
            _run_surface_cmd("1", "Secure screen dikembalikan ke normal.")

        # Auto-bypass toggle — persisted in config
        auto_bypass_var = tk.BooleanVar(
            value=self.config.get("remote.auto_bypass_secure", False))

        def _toggle_auto_bypass():
            val = auto_bypass_var.get()
            self.config.set("remote.auto_bypass_secure", val)
            self.config.save()
            if val:
                secure_sv.set("Auto-bypass aktif — akan bypass otomatis tiap kali HP connect.")
                _bypass_secure(silent=True)

        btn_row = _ck.Frame(tools_sec, fg_color=CARD)
        btn_row.pack(anchor="w")
        _ck.Button(btn_row, text="\U0001f513  Bypass Sekarang", fg_color="#3A2A00", text_color=YEL,
                  font=("Segoe UI", 9, "bold"), padx=14, pady=6,
                  relief="flat", bd=0, cursor="hand2",
                  command=_bypass_secure).pack(side="left", padx=(0, 8))
        _ck.Button(btn_row, text="Kembalikan Normal", fg_color=CARD2, text_color=MUT,
                  font=("Segoe UI", 9), padx=10, pady=6,
                  relief="flat", bd=0, cursor="hand2",
                  command=_restore_secure).pack(side="left")

        auto_row = _ck.Frame(tools_sec, fg_color=CARD)
        auto_row.pack(anchor="w", pady=(8, 0))
        _ck.Checkbutton(auto_row, text="Auto-bypass tiap kali HP connect (selalu aktif)",
                       variable=auto_bypass_var,
                       command=_toggle_auto_bypass, fg_color=CARD, text_color=FG, selectcolor="#1c1c2e",
                       activebackground=CARD, activeforeground=FG,
                       font=("Segoe UI", 9), cursor="hand2").pack(side="left")

        # ══════════════════════════════════════════════════════════════
        # SECTION — USB First-time Wizard (tombol launcher)
        # ══════════════════════════════════════════════════════════════
        usb_wiz_sec = _sec("USB Setup Wizard",
                           accent="#0D2240",
                           subtitle="Koneksi USB pertama kali — panduan otomatis")

        _ck.Label(usb_wiz_sec,
                 text="Wizard ini memandu kamu menghubungkan HP via USB lalu beralih ke WiFi "
                      "secara otomatis — tinggal ikuti langkah yang muncul.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 9),
                 wraplength=560, justify="left").pack(anchor="w", pady=(0, 10))

        wiz_btn_row = _ck.Frame(usb_wiz_sec, fg_color=CARD)
        wiz_btn_row.pack(anchor="w")
        _ck.Button(wiz_btn_row,
                  text="  Buka USB Setup Wizard", fg_color="#0EA5E9", text_color="white",
                  font=("Segoe UI", 10, "bold"), padx=18, pady=8,
                  relief="flat", bd=0, cursor="hand2",
                  command=lambda: self._show_usb_wizard(msg_var, ip_var, _refresh_devs)
                  ).pack(side="left", padx=(0, 12))

        # Auto-install companion toggle
        auto_install_var = tk.BooleanVar(
            value=self.config.get("remote.auto_install_companion", True))
        def _toggle_auto_install():
            self.config.set("remote.auto_install_companion", auto_install_var.get())
            self.config.save()
        _ck.Checkbutton(usb_wiz_sec,
                       text="Auto-install Synthex App ke HP saat pertama terhubung",
                       variable=auto_install_var,
                       command=_toggle_auto_install, fg_color=CARD, text_color=FG, selectcolor="#1c1c2e",
                       activebackground=CARD, activeforeground=FG,
                       font=("Segoe UI", 9), cursor="hand2").pack(
            anchor="w", pady=(8, 0))
        _ck.Label(usb_wiz_sec,
                 text="Letakkan Synthex.apk di folder  synthex/tools/Synthex.apk  "
                      "setelah download dari GitHub Actions.", fg_color=CARD, text_color="#3A3A5A", font=("Segoe UI", 8)).pack(
            anchor="w", pady=(2, 0))

        _ck.Label(wiz_btn_row,
                 text="Sudah terhubung sebelumnya? Gunakan IP History di atas.", fg_color=CARD, text_color="#3A3A5A", font=("Segoe UI", 8)).pack(side="left")

        # ══════════════════════════════════════════════════════════════
        # SECTION — Macro Remote
        # ══════════════════════════════════════════════════════════════
        mac_sec = _sec("Macro Remote", accent="#1A0A30",
                       subtitle="Auto-action saat tidak ada gerakan")

        mac_hdr_row = _ck.Frame(mac_sec, fg_color=CARD)
        mac_hdr_row.pack(fill="x", pady=(0, 8))

        mac_enable_var = tk.BooleanVar(
            value=self.config.get("remote.macro_enabled", False))
        _ck.Checkbutton(mac_hdr_row,
                       text="Aktifkan Macro Engine",
                       variable=mac_enable_var, fg_color=CARD, text_color=FG, selectcolor="#1c1c2e",
                       activebackground=CARD, activeforeground=FG,
                       font=("Segoe UI", 9, "bold"), cursor="hand2").pack(
            side="left")

        mac_status_var = tk.StringVar(value="")
        _ck.Label(mac_hdr_row, textvariable=mac_status_var, fg_color=CARD, text_color=GRN, font=("Segoe UI", 8)).pack(
            side="right")

        # Macro rules list container
        mac_rules_frame = _ck.Frame(mac_sec, fg_color="#0D0D18")
        mac_rules_frame.pack(fill="x", pady=(0, 8))

        # Stored rules from config
        _mac_rules: list = list(self.config.get("remote.macro_rules", []))

        def _fmt_delay(sec):
            if sec < 60:  return "{}d".format(sec)
            if sec < 3600: return "{}m".format(sec // 60)
            return "{}j {}m".format(sec // 3600, (sec // 60) % 60)

        def _rebuild_mac_rows():
            for w in mac_rules_frame.winfo_children():
                try: w.destroy()
                except Exception: pass
            if not _mac_rules:
                _ck.Label(mac_rules_frame, text="  Belum ada rule macro — klik + Tambah Rule di bawah.", fg_color="#0D0D18", text_color=MUT, font=("Segoe UI", 8)).pack(
                    anchor="w", pady=6, padx=10)
                return
            for i, rule in enumerate(_mac_rules):
                _make_mac_row(i, rule)

        _ACTION_LABELS_LOCAL = {
            "tap":          "Tap Koordinat",
            "swipe_down":   "Swipe Bawah",
            "swipe_up":     "Swipe Atas",
            "swipe_left":   "Swipe Kiri",
            "swipe_right":  "Swipe Kanan",
            "swipe_custom": "Swipe Custom",
            "key_home":     "Home",
            "key_back":     "Back",
            "key_wakeup":   "Wake Up",
        }

        def _make_mac_row(i: int, rule: dict):
            enabled = rule.get("enabled", True)
            row = _ck.Frame(mac_rules_frame, fg_color="#0D0D18", padx=10, pady=6)
            row.pack(fill="x")
            _ck.Frame(mac_rules_frame, fg_color="#16162a", height=1).pack(fill="x")

            en_var = tk.BooleanVar(value=enabled)
            def _toggle_en(idx=i, v=en_var):
                _mac_rules[idx]["enabled"] = v.get()
                _save_mac_rules()
            _ck.Checkbutton(row, variable=en_var, fg_color="#0D0D18", text_color=FG, selectcolor="#1c1c2e",
                           activebackground="#0D0D18",
                           command=_toggle_en).pack(side="left")

            delay_txt = _fmt_delay(rule.get("delay_sec", 180))
            act_txt   = _ACTION_LABELS_LOCAL.get(rule.get("action", "tap"), rule.get("action", ""))
            coord_txt = ""
            if rule.get("action") == "tap":
                coord_txt = "  ({}, {})".format(rule.get("x",540), rule.get("y",960))
            elif rule.get("action") == "swipe_custom":
                coord_txt = "  ({},{})→({},{})".format(
                    rule.get("x1",540), rule.get("y1",300),
                    rule.get("x2",540), rule.get("y2",1200))

            _ck.Label(row,
                     text="Idle {}  →  {}{}".format(delay_txt, act_txt, coord_txt), fg_color="#0D0D18", text_color=FG, font=("Segoe UI", 9)).pack(
                side="left", padx=(4, 0))
            if rule.get("label"):
                _ck.Label(row, text="  [{}]".format(rule["label"]), fg_color="#0D0D18", text_color=MUT, font=("Segoe UI", 8)).pack(
                    side="left")

            def _del(idx=i):
                _mac_rules.pop(idx)
                _save_mac_rules()
                _rebuild_mac_rows()
                _apply_mac_engine()

            def _fire(r=rule):
                if self._macro_engine:
                    self._macro_engine.fire_now(r)
                elif self._adb:
                    from modules.remote_macro import MacroEngine as _ME
                    _tmp = _ME(self._adb)
                    _tmp.fire_now(r)
                mac_status_var.set("Dijalankan manual!")
                if self._root:
                    self._root.after(2000, lambda: mac_status_var.set(""))

            _ck.Button(row, text="▶", fg_color="#1A1A38", text_color=ACC,
                      font=("Segoe UI", 8, "bold"), padx=6, pady=2,
                      relief="flat", bd=0, cursor="hand2",
                      command=_fire).pack(side="right", padx=(4, 0))
            _ck.Button(row, text="✕", fg_color="#1A1A38", text_color=RED,
                      font=("Segoe UI", 8), padx=6, pady=2,
                      relief="flat", bd=0, cursor="hand2",
                      command=_del).pack(side="right", padx=(4, 0))

        def _save_mac_rules():
            self.config.set("remote.macro_rules", _mac_rules)
            self.config.save()

        def _apply_mac_engine():
            enabled = mac_enable_var.get()
            self.config.set("remote.macro_enabled", enabled)
            self.config.save()
            if not enabled:
                if self._macro_engine and self._macro_engine.running:
                    self._macro_engine.stop()
                mac_status_var.set("Macro: nonaktif")
                return
            if not self._adb:
                mac_status_var.set("ADB belum siap")
                return
            active_rules = [r for r in _mac_rules if r.get("enabled", True)]
            if not active_rules:
                mac_status_var.set("Tidak ada rule aktif")
                return
            from modules.remote_macro import MacroEngine as _ME
            if self._macro_engine is None:
                self._macro_engine = _ME(self._adb)

            def _on_fire(rule):
                label = rule.get("label") or rule.get("action", "")
                if self._root:
                    self._root.after(0, lambda l=label:
                        mac_status_var.set("Fired: {}".format(l)))
                    self._root.after(3000, lambda: mac_status_var.set(
                        "Engine aktif — idle: ..."))

            self._macro_engine.on_fire = _on_fire
            self._macro_engine.set_rules(active_rules)
            # Always use dynamic serial so engine tracks device changes
            def _get_mirror_serial():
                mirrored = list(self._scrcpy_map.keys()) if hasattr(self, "_scrcpy_map") else []
                return mirrored[0] if mirrored else ""
            self._macro_engine._serial_fn = _get_mirror_serial
            if not self._macro_engine.running:
                self._macro_engine.start()
            mac_status_var.set("Engine aktif — {} rule".format(len(active_rules)))

        mac_enable_var.trace_add("write", lambda *_: _apply_mac_engine())
        _rebuild_mac_rows()

        # ── Add Rule dialog ──────────────────────────────────────────────────
        def _open_add_rule():
            dlg = ctk.CTkToplevel(self._root)
            dlg.withdraw()
            dlg.title("Tambah Macro Rule")
            dlg.configure(fg_color="#0D0D14")
            dlg.resizable(False, False)
            dlg.update()
            dlg.grab_set()
            dlg.update_idletasks()
            dlg.geometry("+{}+{}".format(
                (dlg.winfo_screenwidth() - 380) // 2,
                (dlg.winfo_screenheight() - 440) // 2))

            _ck.Frame(dlg, fg_color=ACC, height=4).pack(fill="x")
            b = _ck.Frame(dlg, fg_color="#0D0D14", padx=24, pady=18)
            b.pack(fill="both", expand=True)

            def _row(parent, lbl, widget_fn):
                r = _ck.Frame(parent, fg_color="#0D0D14")
                r.pack(fill="x", pady=(0, 10))
                _ck.Label(r, text=lbl, fg_color="#0D0D14", text_color=MUT,
                         font=("Segoe UI", 9), width=18, anchor="w").pack(side="left")
                return widget_fn(r)

            _ck.Label(b, text="Tambah Macro Rule", fg_color="#0D0D14", text_color=FG,
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 14))

            # Label (opsional)
            lbl_var = tk.StringVar()
            _row(b, "Label (opsional):",
                 lambda p: _ck.Entry(p, textvariable=lbl_var, fg_color="#16162a", text_color=FG, insertbackground=FG,
                                    relief="flat", width=22, bd=4).pack(side="left"))

            # Delay
            delay_var = tk.StringVar(value="180")
            dr = _row(b, "Idle sebelum fire:", lambda p: p)
            _ck.Entry(dr, textvariable=delay_var, fg_color="#16162a", text_color=FG, insertbackground=FG,
                     relief="flat", width=8, bd=4).pack(side="left")
            _ck.Label(dr, text="detik  (180=3 menit, 300=5 menit)", fg_color="#0D0D14", text_color=MUT, font=("Segoe UI", 8)).pack(side="left", padx=(6,0))

            # Action
            act_var = tk.StringVar(value="swipe_down")
            act_options = list(_ACTION_LABELS_LOCAL.keys())
            act_labels  = [_ACTION_LABELS_LOCAL[k] for k in act_options]
            _row(b, "Aksi:", lambda p: _ck.Combobox(
                p, textvariable=act_var,
                values=act_labels, state="readonly", width=20).pack(side="left"))

            # Coord frame (shown only for tap/swipe_custom)
            coord_frame = _ck.Frame(b, fg_color="#0D0D14")
            coord_frame.pack(fill="x")
            x_var  = tk.StringVar(value="540"); y_var  = tk.StringVar(value="960")
            x1_var = tk.StringVar(value="540"); y1_var = tk.StringVar(value="300")
            x2_var = tk.StringVar(value="540"); y2_var = tk.StringVar(value="1200")
            ms_var = tk.StringVar(value="350")

            def _entry(parent, lbl, var, w=6):
                _ck.Label(parent, text=lbl, fg_color="#0D0D14", text_color=MUT,
                         font=("Segoe UI", 8)).pack(side="left", padx=(0,2))
                _ck.Entry(parent, textvariable=var, fg_color="#16162a", text_color=FG, insertbackground=FG,
                         relief="flat", width=w, bd=3).pack(side="left", padx=(0,8))

            tap_frame = _ck.Frame(coord_frame, fg_color="#0D0D14")
            _entry(tap_frame, "X:", x_var); _entry(tap_frame, "Y:", y_var)

            cust_frame = _ck.Frame(coord_frame, fg_color="#0D0D14")
            _entry(cust_frame, "X1:", x1_var); _entry(cust_frame, "Y1:", y1_var)
            _entry(cust_frame, "X2:", x2_var); _entry(cust_frame, "Y2:", y2_var)
            _entry(cust_frame, "ms:", ms_var, 5)

            def _update_coord_vis(*_):
                # Map display label back to key
                disp = act_var.get()
                key  = act_options[act_labels.index(disp)] if disp in act_labels else disp
                tap_frame.pack_forget(); cust_frame.pack_forget()
                if key == "tap":
                    tap_frame.pack(anchor="w", pady=(0, 8))
                elif key == "swipe_custom":
                    cust_frame.pack(anchor="w", pady=(0, 8))

            act_var.trace_add("write", _update_coord_vis)
            _update_coord_vis()

            err_var = tk.StringVar(value="")
            _ck.Label(b, textvariable=err_var, fg_color="#0D0D14", text_color=RED,
                     font=("Segoe UI", 8)).pack(anchor="w")

            def _save():
                disp = act_var.get()
                key  = act_options[act_labels.index(disp)] if disp in act_labels else disp
                try:
                    delay = int(delay_var.get())
                    if delay < 5:
                        err_var.set("Delay minimum 5 detik"); return
                except ValueError:
                    err_var.set("Delay harus angka"); return

                rule: dict = {
                    "delay_sec": delay,
                    "action":    key,
                    "enabled":   True,
                }
                if lbl_var.get().strip():
                    rule["label"] = lbl_var.get().strip()
                if key == "tap":
                    try:
                        rule["x"] = int(x_var.get()); rule["y"] = int(y_var.get())
                    except ValueError:
                        err_var.set("Koordinat tap harus angka"); return
                elif key == "swipe_custom":
                    try:
                        rule["x1"] = int(x1_var.get()); rule["y1"] = int(y1_var.get())
                        rule["x2"] = int(x2_var.get()); rule["y2"] = int(y2_var.get())
                        rule["ms"]  = int(ms_var.get())
                    except ValueError:
                        err_var.set("Koordinat swipe harus angka"); return

                _mac_rules.append(rule)
                _save_mac_rules()
                _rebuild_mac_rows()
                _apply_mac_engine()
                dlg.destroy()

            btn_r = _ck.Frame(b, fg_color="#0D0D14")
            btn_r.pack(anchor="e", pady=(10, 0))
            _ck.Button(btn_r, text="Simpan", fg_color=ACC, text_color="white",
                      font=("Segoe UI", 9, "bold"), padx=18, pady=7,
                      relief="flat", bd=0, cursor="hand2",
                      command=_save).pack(side="left", padx=(0, 8))
            _ck.Button(btn_r, text="Batal", fg_color="#1c1c2e", text_color=MUT,
                      font=("Segoe UI", 9), padx=12, pady=7,
                      relief="flat", bd=0, cursor="hand2",
                      command=dlg.destroy).pack(side="left")
            dlg.update()
            dlg.deiconify()

        mac_add_row = _ck.Frame(mac_sec, fg_color=CARD)
        mac_add_row.pack(anchor="w")
        _ck.Button(mac_add_row, text="+ Tambah Rule", fg_color="#1A0840", text_color=ACC,
                  font=("Segoe UI", 9, "bold"), padx=14, pady=6,
                  relief="flat", bd=0, cursor="hand2",
                  command=_open_add_rule).pack(side="left", padx=(0, 10))
        _ck.Button(mac_add_row, text="Stop Engine", fg_color="#1c1c2e", text_color=MUT,
                  font=("Segoe UI", 8), padx=10, pady=6,
                  relief="flat", bd=0, cursor="hand2",
                  command=lambda: (
                      self._macro_engine.stop() if self._macro_engine else None,
                      mac_status_var.set("Dihentikan")
                  )).pack(side="left")

        # ══════════════════════════════════════════════════════════════
        # SECTION — Synthex Companion (HP → PC via browser)
        # ══════════════════════════════════════════════════════════════
        comp_sec = _sec("Synthex Companion App",
                        accent="#0A2A0A",
                        subtitle="Kontrol dari HP tanpa APK — buka di Chrome")

        comp_info = _ck.Label(comp_sec,
            text="PC akan menjalankan server lokal. Buka URL di bawah dari Chrome HP kamu.\n"
                 "Tambahkan ke Home Screen (menu Chrome → Add to Home Screen) "
                 "supaya terasa seperti app sungguhan.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 9), wraplength=560, justify="left")
        comp_info.pack(anchor="w", pady=(0, 10))

        comp_url_var  = tk.StringVar(value="Server belum berjalan")
        comp_stat_var = tk.StringVar(value="")

        comp_url_lbl = _ck.Label(comp_sec, textvariable=comp_url_var, fg_color=CARD, text_color=ACC, font=("Segoe UI", 11, "bold"),
                                cursor="hand2")
        comp_url_lbl.pack(anchor="w", pady=(0, 6))

        _ck.Label(comp_sec, textvariable=comp_stat_var, fg_color=CARD, text_color=GRN, font=("Segoe UI", 8)).pack(anchor="w")

        def _comp_copy_url():
            url = comp_url_var.get()
            if url.startswith("http"):
                self._root.clipboard_clear()
                self._root.clipboard_append(url)
                comp_stat_var.set("URL disalin ke clipboard!")
                if self._root:
                    self._root.after(2500, lambda: comp_stat_var.set(""))

        comp_url_lbl.bind("<Button-1>", lambda e: _comp_copy_url())

        def _start_companion():
            if self._bridge and self._bridge.running:
                comp_stat_var.set("Server sudah berjalan")
                return
            from modules.synthex_bridge import SynthexBridge
            port = int(self.config.get("remote.companion_port", 8765))
            self._bridge = SynthexBridge(
                adb_manager=self._adb, port=port)

            def _on_cmd(cmd):
                ctype = cmd.get("type", "")
                if ctype == "fire_macro" and self._macro_engine:
                    idx = cmd.get("index", 0)
                    rules = self._macro_engine._rules
                    if 0 <= idx < len(rules):
                        self._macro_engine.fire_now(rules[idx])

            self._bridge.on_command = _on_cmd
            ok = self._bridge.start()
            if ok:
                comp_url_var.set(self._bridge.url)
                comp_stat_var.set("Server aktif — klik URL untuk salin, buka di Chrome HP")
                _update_bridge_state()
            else:
                comp_stat_var.set("Gagal — port mungkin sudah dipakai")

        def _stop_companion():
            if self._bridge:
                self._bridge.stop()
                self._bridge = None
            comp_url_var.set("Server belum berjalan")
            comp_stat_var.set("Server dihentikan")

        _bridge_poll_id = [None]

        def _update_bridge_state():
            if not self._bridge or not self._bridge.running:
                return
            devs = []
            if self._adb:
                try:
                    devs = self._adb.list_devices()
                except Exception:
                    pass
            mirrored = list(self._scrcpy_map.keys()) if hasattr(self, "_scrcpy_map") else []
            self._bridge.update_status(
                macros=[r for r in _mac_rules if r.get("enabled", True)],
                devices=devs,
                mirror_serial=mirrored[0] if mirrored else "")
            if self._root:
                _bridge_poll_id[0] = self._root.after(5000, _update_bridge_state)

        comp_btn_row = _ck.Frame(comp_sec, fg_color=CARD)
        comp_btn_row.pack(anchor="w", pady=(8, 0))
        _ck.Button(comp_btn_row, text="▶ Jalankan Server Companion", fg_color="#16803C", text_color="white",
                  font=("Segoe UI", 9, "bold"), padx=14, pady=6,
                  relief="flat", bd=0, cursor="hand2",
                  command=_start_companion).pack(side="left", padx=(0, 8))
        _ck.Button(comp_btn_row, text="■ Stop", fg_color="#1c1c2e", text_color=MUT,
                  font=("Segoe UI", 9), padx=10, pady=6,
                  relief="flat", bd=0, cursor="hand2",
                  command=_stop_companion).pack(side="left")

        # If bridge was already running from a previous page load
        if self._bridge and self._bridge.running:
            comp_url_var.set(self._bridge.url)
            comp_stat_var.set("Server aktif")

        # ── Init ADB in background ───────────────────────────────────────────
        def _init_adb():
            from modules.remote_control import AdbManager, ScrcpyManager
            if self._adb is None:
                self._adb    = AdbManager()
                self._scrcpy = ScrcpyManager(self._adb)
            def _after():
                if self._adb.available:
                    adb_sv.set("  |  ADB: siap")
                    adb_lbl.configure(text_color=GRN)
                    _refresh_devs()
                else:
                    adb_sv.set("  |  ADB: tidak ditemukan")
                    adb_lbl.configure(text_color=YEL)
                    status_var.set("ADB tidak ditemukan — klik Download")
                    dot.configure(text_color=RED)
                _upd_scrcpy()
            if self._root:
                self._root.after(0, _after)

        def _init_adb_then_reconnect():
            _init_adb()
            # After ADB ready, try auto-reconnect to last saved IP
            import time as _tr
            _tr.sleep(1.5)
            last_ip = self.config.get("remote.last_ip", "")
            if last_ip and self._adb and self._adb.available:
                try:
                    port = int(self.config.get("remote.last_port", "5555"))
                except (ValueError, TypeError):
                    port = 5555
                ok, _ = self._adb.connect(last_ip, port)
                if ok:
                    _refresh_devs()

        _thr.Thread(target=_init_adb_then_reconnect, daemon=True).start()

        # ── Auto-refresh device list every 10s ──────────────────────────────
        # Cancel any previous poll timer from a prior page instance
        if hasattr(self, "_adb_poll_id") and self._adb_poll_id:
            try: self._root.after_cancel(self._adb_poll_id)
            except Exception: pass
            self._adb_poll_id = None

        _poll_active = [True]

        def _poll_adb():
            if not self._root or not _poll_active[0]:
                return
            if self._cur == "remote":
                _thr.Thread(target=_refresh_devs, daemon=True).start()
            self._adb_poll_id = self._root.after(10000, _poll_adb)

        def _on_page_destroy(event):
            _poll_active[0] = False
            if hasattr(self, "_adb_poll_id") and self._adb_poll_id:
                try: self._root.after_cancel(self._adb_poll_id)
                except Exception: pass
                self._adb_poll_id = None
            if _bridge_poll_id[0]:
                try: self._root.after_cancel(_bridge_poll_id[0])
                except Exception: pass
                _bridge_poll_id[0] = None

        f.bind("<Destroy>", _on_page_destroy)
        self._adb_poll_id = self._root.after(10000, _poll_adb)

        return f

    # ================================================================
    #  SYNTHEX COMPANION AUTO-INSTALL
    # ================================================================

    def _auto_install_companion(self, serial: str, msg_var=None):
        """
        Called when a new device is detected.
        Checks if Synthex app is installed; if not, prompts + installs via ADB.
        """
        import time as _t
        if not self._adb or not self._adb.available:
            return

        def _set_msg(txt):
            if self._root and msg_var:
                self._root.after(0, lambda t=txt: msg_var.set(t))

        # Check if already installed
        installed = self._adb.is_companion_installed(serial)
        if installed:
            return  # already there, nothing to do

        # Not installed — check if APK is available locally
        apk_path = self._adb.get_companion_apk_path()

        if not apk_path:
            # APK not downloaded yet — show download prompt in UI
            if self._root:
                self._root.after(0, lambda: self._show_companion_download_prompt(serial, msg_var))
            return

        # APK available — install silently
        _set_msg("HP baru terdeteksi — menginstall Synthex App...")
        ok, msg = self._adb.install_companion(apk_path, serial)
        if ok:
            _set_msg("Synthex App berhasil diinstall!")
            _t.sleep(1)
            self._adb.launch_companion(serial)
            _set_msg("Synthex App diluncurkan di HP")
        else:
            _set_msg("Install Synthex App gagal: {}".format(msg[:80]))

    def _show_companion_download_prompt(self, serial: str, msg_var=None):
        """Show a dialog asking user to download companion APK first."""
        import webbrowser as _wb

        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Synthex App diperlukan")
        dlg.configure(fg_color="#0A0A0F")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.update()
        dlg.grab_set()
        dlg.update_idletasks()
        dlg.geometry("+{}+{}".format(
            (dlg.winfo_screenwidth()  - 460) // 2,
            (dlg.winfo_screenheight() - 280) // 2))

        _ck.Frame(dlg, fg_color="#6C4AFF", height=4).pack(fill="x")
        body = _ck.Frame(dlg, fg_color="#0A0A0F", padx=28, pady=22)
        body.pack(fill="both", expand=True)

        _ck.Label(body, text="HP Baru Terdeteksi!", fg_color="#0A0A0F", text_color="white",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        _ck.Label(body,
                 text="HP kamu belum punya Synthex App.\n"
                      "Install sekarang supaya bisa dikontrol dari app ini.", fg_color="#0A0A0F", text_color="#8080A0",
                 font=("Segoe UI", 9),
                 wraplength=400, justify="left").pack(anchor="w", pady=(6, 0))

        _ck.Label(body, text="Serial: {}".format(serial), fg_color="#0A0A0F", text_color="#6C4AFF",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 0))

        info = _ck.Label(body,
                 text="Download Synthex.apk dari GitHub Actions lalu letakkan di:\n"
                      "synthex/tools/Synthex.apk\n\n"
                      "Setelah file ada, colok HP lagi → install otomatis.", fg_color="#0A0A0F", text_color="#555577",
                 font=("Segoe UI", 8),
                 wraplength=400, justify="left")
        info.pack(anchor="w", pady=(6, 0))

        br = _ck.Frame(body, fg_color="#0A0A0F")
        br.pack(anchor="e", pady=(16, 0))

        def _open_actions():
            _wb.open("https://github.com/Yohn18/synthex-releases/actions")
            dlg.destroy()

        _ck.Button(br, text="Buka GitHub Actions", fg_color="#6C4AFF", text_color="white",
                  font=("Segoe UI", 9, "bold"), padx=16, pady=7,
                  relief="flat", bd=0, cursor="hand2",
                  command=_open_actions).pack(side="left", padx=(0, 8))
        _ck.Button(br, text="Nanti", fg_color="#1c1c2e", text_color="#555577",
                  font=("Segoe UI", 9), padx=12, pady=7,
                  relief="flat", bd=0, cursor="hand2",
                  command=dlg.destroy).pack(side="left")
        dlg.update()
        dlg.deiconify()

    # ================================================================
    #  USB SETUP WIZARD
    # ================================================================

    def _show_usb_wizard(self, msg_var=None, ip_var=None, refresh_devs=None):
        """Step-by-step Toplevel wizard: USB → tcpip → WiFi → mirror."""
        import threading as _thr
        import time as _time

        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Synthex USB Setup Wizard")
        dlg.configure(fg_color="#0A0A0F")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.update()
        dlg.grab_set()
        dlg.update_idletasks()
        _w, _h = 480, 520
        dlg.geometry("{}x{}+{}+{}".format(
            _w, _h,
            (dlg.winfo_screenwidth()  - _w) // 2,
            (dlg.winfo_screenheight() - _h) // 2))

        # Header
        _ck.Frame(dlg, fg_color="#0EA5E9", height=4).pack(fill="x")
        hdr = _ck.Frame(dlg, fg_color="#111118", padx=20, pady=14)
        hdr.pack(fill="x")
        _ck.Label(hdr, text="USB Setup Wizard", fg_color="#111118", text_color="white",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        _ck.Label(hdr,
                 text="Hubungkan HP pertama kali — panduan otomatis langkah demi langkah", fg_color="#111118", text_color="#64748b",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

        body = _ck.Frame(dlg, fg_color="#0A0A0F", padx=20, pady=14)
        body.pack(fill="both", expand=True)

        STEPS = [
            ("Colok kabel USB",
             "Pastikan Developer Options dan USB Debugging sudah aktif di HP.\n"
             "Saat ada popup izin di HP, pilih Allow/Izinkan."),
            ("Mendeteksi HP",
             "Menunggu HP terdeteksi oleh ADB..."),
            ("Aktifkan ADB via WiFi",
             "Menjalankan 'adb tcpip 5555' — HP akan siap menerima koneksi WiFi."),
            ("Mendapatkan IP HP",
             "Mengambil IP WiFi HP secara otomatis..."),
            ("Cabut USB & Hubungkan WiFi",
             "Cabut kabel USB sekarang, lalu klik Lanjut untuk connect via WiFi."),
            ("Menghubungkan via WiFi",
             "Mencoba adb connect ke IP HP..."),
        ]
        _N = len(STEPS)

        step_frames: list[tk.Frame] = []
        step_dots:   list[tk.Label] = []
        step_lbls:   list[tk.Label] = []
        step_descs:  list[tk.Label] = []

        for i, (title, desc) in enumerate(STEPS):
            row = _ck.Frame(body, fg_color="#0A0A0F", pady=3)
            row.pack(fill="x")
            dot = _ck.Label(row, text="●", fg_color="#0A0A0F", text_color="#374151",
                           font=("Segoe UI", 12))
            dot.pack(side="left", padx=(0, 8))
            info = _ck.Frame(row, fg_color="#0A0A0F")
            info.pack(side="left", fill="x", expand=True)
            lbl  = _ck.Label(info, text="{}. {}".format(i+1, title), fg_color="#0A0A0F", text_color="#64748b",
                            font=("Segoe UI", 9, "bold"), anchor="w")
            lbl.pack(anchor="w")
            desc_lbl = _ck.Label(info, text=desc, fg_color="#0A0A0F", text_color="#374151",
                                font=("Segoe UI", 8),
                                wraplength=370, justify="left", anchor="w")
            desc_lbl.pack(anchor="w")
            step_frames.append(row)
            step_dots.append(dot)
            step_lbls.append(lbl)
            step_descs.append(desc_lbl)

        # Status + progress
        status_var = tk.StringVar(value="Siap — klik Mulai untuk memulai wizard")
        _ck.Frame(body, fg_color="#1c1c2e", height=1).pack(fill="x", pady=(10, 6))
        st_lbl = _ck.Label(body, textvariable=status_var, fg_color="#0A0A0F", text_color="#e2e8f0",
                          font=("Segoe UI", 9), wraplength=420, justify="left")
        st_lbl.pack(anchor="w")

        # Buttons
        btn_row = _ck.Frame(dlg, fg_color="#0A0A0F", padx=20, pady=12)
        btn_row.pack(fill="x", side="bottom")
        next_btn = _ck.Button(btn_row, text="▶  Mulai Wizard", fg_color="#0EA5E9", text_color="white",
                             font=("Segoe UI", 10, "bold"),
                             padx=18, pady=8, relief="flat", bd=0, cursor="hand2")
        next_btn.pack(side="left", padx=(0, 10))
        _ck.Button(btn_row, text="Tutup", fg_color="#1c1c2e", text_color="#64748b",
                  font=("Segoe UI", 9), padx=12, pady=8,
                  relief="flat", bd=0, cursor="hand2",
                  command=dlg.destroy).pack(side="left")
        dlg.update()
        dlg.deiconify()

        _ip_found   = [""]
        _serial_usb = [""]
        _step_idx   = [-1]

        def _mark(i, state):
            # state: "wait" / "running" / "ok" / "err"
            colors = {"wait": ("#374151", "#374151"), "running": ("#FBBF24", "#D4A400"),
                      "ok":   ("#10b981", "#E2E8F0"), "err":    ("#F87171", "#F87171")}
            dot_c, fg_c = colors.get(state, ("#374151", "#374151"))
            try:
                step_dots[i].configure(text_color=dot_c)
                step_lbls[i].configure(text_color=fg_c)
            except Exception:
                pass

        def _set_status(msg, color="#e2e8f0"):
            if self._root:
                self._root.after(0, lambda: status_var.set(msg))
                self._root.after(0, lambda: st_lbl.configure(text_color=color))

        def _run_wizard():
            if not self._adb:
                _set_status("ADB belum diinisialisasi — buka halaman Remote dulu", "#f87171")
                return

            # Step 0: Colok USB
            _mark(0, "running")
            _set_status("Langkah 1: Colok kabel USB dan izinkan USB debugging di HP...")

            # Step 1: Deteksi HP
            _mark(1, "running")
            _set_status("Menunggu HP terdeteksi (maks 30 detik)...")
            found = False
            for _ in range(30):
                devs = self._adb.list_devices()
                usb  = [d["serial"] for d in devs
                        if d["state"] == "device" and ":" not in d["serial"]]
                if usb:
                    _serial_usb[0] = usb[0]
                    _mark(0, "ok"); _mark(1, "ok")
                    _set_status("HP terdeteksi: {}".format(usb[0]), "#10b981")
                    found = True
                    break
                _time.sleep(1)
            if not found:
                _mark(0, "err"); _mark(1, "err")
                _set_status("Tidak ada HP USB terdeteksi. Pastikan USB Debugging aktif "
                            "dan izinkan popup di HP.", "#f87171")
                if self._root:
                    self._root.after(0, lambda: next_btn.configure(
                        text="▶  Coba Lagi", command=lambda: _thr.Thread(
                            target=_run_wizard, daemon=True).start(),
                        state="normal"))
                return

            # Step 2: adb tcpip
            _mark(2, "running")
            _set_status("Menjalankan adb tcpip 5555...")
            _time.sleep(0.5)
            ok, msg = self._adb.tcpip(5555)
            if not ok:
                _mark(2, "err")
                _set_status("Gagal: {} — coba cabut-colok USB lagi".format(msg), "#f87171")
                return
            _mark(2, "ok")
            _time.sleep(1.5)

            # Step 3: Dapatkan IP
            _mark(3, "running")
            _set_status("Mendapatkan IP WiFi HP...")
            ip = self._adb.get_device_ip()
            if not ip:
                _mark(3, "err")
                _set_status("IP WiFi tidak terdeteksi — pastikan HP terhubung ke WiFi.", "#f87171")
                if self._root:
                    self._root.after(0, lambda: next_btn.configure(
                        text="Isi IP Manual & Lanjut",
                        state="normal",
                        command=lambda: _manual_continue()))
                return
            _ip_found[0] = ip
            _mark(3, "ok")
            _set_status("IP ditemukan: {}:5555".format(ip), "#10b981")

            # Step 4: Cabut USB — tunggu user klik Lanjut
            _mark(4, "running")
            if self._root:
                self._root.after(0, lambda: next_btn.configure(
                    text="✔  Cabut USB, lalu klik Lanjut",
                    state="normal",
                    command=lambda: _thr.Thread(
                        target=_step_wifi, daemon=True).start()))
            _set_status("Cabut kabel USB sekarang, lalu klik tombol di bawah.", "#FBBF24")

        def _manual_continue():
            import tkinter.simpledialog as _sd
            ip = _sd.askstring("IP HP", "Masukkan IP WiFi HP kamu (tanpa port):",
                               parent=dlg)
            if ip and ip.strip():
                _ip_found[0] = ip.strip()
                _mark(3, "ok")
                _mark(4, "running")
                next_btn.configure(text="✔  Cabut USB, lalu klik Lanjut",
                                   state="normal",
                                   command=lambda: _thr.Thread(
                                       target=_step_wifi, daemon=True).start())
                _set_status("IP manual: {} — cabut USB lalu klik Lanjut".format(
                    _ip_found[0]), "#FBBF24")

        def _step_wifi():
            _mark(4, "ok")
            if self._root:
                self._root.after(0, lambda: next_btn.configure(
                    state="disabled", text="Sedang menghubungkan..."))

            # Step 5: Connect WiFi
            _mark(5, "running")
            ip = _ip_found[0]
            _set_status("Menghubungkan ke {}:5555...".format(ip))
            _time.sleep(2.5)
            ok2, msg2 = False, ""
            for attempt in range(5):
                probe = self._adb.probe_port(ip, 5555, timeout=3)
                if probe == "open":
                    ok2, msg2 = self._adb.connect(ip, 5555)
                    if ok2:
                        break
                _set_status("Mencoba... ({}/5)".format(attempt+1))
                _time.sleep(1.5)

            if ok2:
                _mark(5, "ok")
                _set_status("Terhubung! HP siap di-mirror via WiFi.", "#10b981")
                if msg_var and self._root:
                    self._root.after(0, lambda: msg_var.set(msg2))
                if ip_var and self._root:
                    self._root.after(0, lambda: ip_var.set(ip))
                self.config.set("remote.last_ip", ip)
                self.config.set("remote.last_port", "5555")
                self.config.save()
                if refresh_devs:
                    refresh_devs()
                if self._root:
                    self._root.after(0, lambda: next_btn.configure(
                        text="✔  Selesai — Tutup", state="normal",
                        command=dlg.destroy))
            else:
                _mark(5, "err")
                _set_status(
                    "Gagal terhubung. {}\n"
                    "Coba: HP & PC di WiFi yang sama? Port 5555 terbuka?".format(msg2),
                    "#f87171")
                if self._root:
                    self._root.after(0, lambda: next_btn.configure(
                        text="Coba Lagi WiFi", state="normal",
                        command=lambda: _thr.Thread(
                            target=_step_wifi, daemon=True).start()))

        def _start():
            next_btn.configure(state="disabled", text="Sedang berjalan...")
            for i in range(_N):
                _mark(i, "wait")
            _thr.Thread(target=_run_wizard, daemon=True).start()

        next_btn.configure(command=_start)

    # ================================================================
    #  CHAT PAGE
    # ================================================================

    def _pg_chat(self):
        import threading as _thr
        from datetime import datetime as _dt

        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Chat", "Ngobrol dengan pengguna Synthex yang sedang online")

        # ── Layout: sidebar kiri (online users) + area chat kanan ───────────
        body = _ck.Frame(f, fg_color=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(8, 16))

        # ── Left: online users ───────────────────────────────────────────────
        left = _ck.Frame(body, fg_color=CARD, width=190)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        _ck.Frame(left, fg_color="#7C3AED", height=4).pack(fill="x")
        _ck.Label(left, text="Online Sekarang", fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 9, "bold"),
                 padx=12, pady=8).pack(anchor="w")
        _ck.Frame(left, fg_color=CARD2, height=1).pack(fill="x")

        users_frame = _ck.Frame(left, fg_color=CARD)
        users_frame.pack(fill="both", expand=True, pady=4)

        online_count_var = tk.StringVar(value="")
        _ck.Label(left, textvariable=online_count_var, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 7), padx=12, pady=4).pack(anchor="w")

        # ── Right: messages + input ──────────────────────────────────────────
        right = _ck.Frame(body, fg_color=CARD)
        right.pack(side="left", fill="both", expand=True)

        _ck.Frame(right, fg_color="#1A0840", height=4).pack(fill="x")

        # Messages area (Text widget, read-only)
        msg_area = _ck.Text(right, fg_color="#0F0F1C", text_color=FG,
                           font=("Segoe UI", 9),
                           relief="flat", bd=0,
                           wrap="word", state="disabled",
                           padx=12, pady=8,
                           selectbackground=ACC)
        msg_sb = _ck.Scrollbar(right, command=msg_area.yview)
        msg_area.configure(yscrollcommand=msg_sb.set)
        msg_sb.pack(side="right", fill="y")
        msg_area.pack(fill="both", expand=True)

        # Tags for message styling
        msg_area.tag_configure("time",    foreground=MUT,        font=("Segoe UI", 7))
        msg_area.tag_configure("me",      foreground="#7C3AED",  font=("Segoe UI", 9, "bold"))
        msg_area.tag_configure("other",   foreground="#0EA5E9",  font=("Segoe UI", 9, "bold"))
        msg_area.tag_configure("system",  foreground=YEL,        font=("Segoe UI", 8, "italic"))
        msg_area.tag_configure("text",    foreground=FG,         font=("Segoe UI", 9))
        msg_area.tag_configure("err",     foreground=RED,        font=("Segoe UI", 8, "italic"))
        msg_area.tag_configure("mention", foreground="#FFD700",  font=("Segoe UI", 9, "bold"),
                               background="#2A1A00")

        # Input row
        inp_row = _ck.Frame(right, fg_color="#16162a", padx=10, pady=8)
        inp_row.pack(fill="x")
        inp_var = tk.StringVar()
        inp_entry = _ck.Entry(inp_row, textvariable=inp_var, fg_color="#0F0F1C", text_color=FG, insertbackground=FG,
                             relief="flat", font=("Segoe UI", 10),
                             bd=6)
        inp_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        send_btn = _ck.Button(inp_row, text="Kirim", fg_color="#7C3AED", text_color="white",
                             font=("Segoe UI", 9, "bold"),
                             padx=16, pady=5,
                             relief="flat", bd=0, cursor="hand2")
        send_btn.pack(side="left")

        status_var = tk.StringVar(value="")
        _ck.Label(right, textvariable=status_var, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 7), pady=2).pack(anchor="e", padx=8)

        # ── Helpers ─────────────────────────────────────────────────────────
        _my_email = self._email or ""
        _shown_keys = {}  # OrderedDict-style: key → 1, insertion order = arrival order
        _online_names = []  # list of username strings (email prefix) currently online

        # @mention autocomplete popup
        _mention_popup = [None]  # mutable container for the Toplevel

        def _close_mention_popup():
            if _mention_popup[0]:
                try: _mention_popup[0].destroy()
                except Exception: pass
                _mention_popup[0] = None

        def _on_inp_key(event):
            val = inp_var.get()
            m = re.search(r'@(\w*)$', val)
            if not m:
                _close_mention_popup()
                return
            prefix = m.group(1).lower()
            matches = [n for n in _online_names
                       if n.lower().startswith(prefix) and n != _my_email.split("@")[0]]
            if not matches:
                _close_mention_popup()
                return
            _close_mention_popup()
            popup = ctk.CTkToplevel(self._root)
            popup.withdraw()
            popup.configure(fg_color="#1c1c2e")
            _mention_popup[0] = popup
            x = inp_entry.winfo_rootx()
            y = inp_entry.winfo_rooty() - len(matches) * 26 - 4
            popup.geometry("+{}+{}".format(x, y))
            for name in matches[:5]:
                def _pick(n=name):
                    cur = inp_var.get()
                    new_val = _re2.sub(r'@\w*$', "@{} ".format(n), cur)
                    inp_var.set(new_val)
                    inp_entry.icursor(len(new_val))
                    _close_mention_popup()
                    inp_entry.focus_set()
                btn = _ck.Button(popup, text="@{}".format(name), fg_color="#1c1c2e", text_color="#FFD700",
                                font=("Segoe UI", 9), relief="flat", bd=0,
                                padx=10, pady=3, cursor="hand2",
                                command=_pick)
                btn.pack(fill="x")
            popup.update()
            popup.deiconify()
        inp_entry.bind("<KeyRelease>", _on_inp_key)
        inp_entry.bind("<Escape>", lambda e: _close_mention_popup())

        def _append(sender, text, ts, key, is_me=False, system=False, error=False):
            if key in _shown_keys:
                return
            _shown_keys[key] = 1
            msg_area.configure(state="normal")
            try:
                t = _dt.fromtimestamp(ts).strftime("%H:%M")
            except Exception:
                t = ""
            if system:
                msg_area.insert("end", "  [{}] {}\n".format(t, text), "system")
            elif error:
                msg_area.insert("end", "  {}\n".format(text), "err")
            else:
                import re as _re
                name_tag = "me" if is_me else "other"
                msg_area.insert("end", "[{}] ".format(t), "time")
                msg_area.insert("end", "{}: ".format(sender), name_tag)
                _my_name = _my_email.split("@")[0].lower()
                # Inline @mention parsing
                _segs = _re.split(r'(@\w+)', text)
                for _seg in _segs:
                    if _seg.startswith("@") and _seg[1:].lower() == _my_name:
                        msg_area.insert("end", _seg, "mention")
                    else:
                        msg_area.insert("end", _seg, "text")
                msg_area.insert("end", "\n")
            msg_area.configure(state="disabled")
            msg_area.see("end")

        def _update_users(users):
            _online_names.clear()
            for u in users:
                _online_names.append(u["email"].split("@")[0])
            for w in users_frame.winfo_children():
                w.destroy()
            me_found = False
            for u in users:
                em = u["email"]
                is_me = (em == _my_email)
                if is_me:
                    me_found = True
                dot_clr = "#7C3AED" if is_me else GRN
                name = em.split("@")[0]
                label = "{} (kamu)".format(name) if is_me else name
                row = _ck.Frame(users_frame, fg_color=CARD)
                row.pack(fill="x", padx=8, pady=2)
                _ck.Label(row, text="\u25cf", fg_color=CARD, text_color=dot_clr,
                         font=("Segoe UI", 10)).pack(side="left")
                _ck.Label(row, text=label, fg_color=CARD, text_color=FG,
                         font=("Segoe UI", 8)).pack(side="left", padx=(4, 0))
            if not me_found and _my_email:
                row = _ck.Frame(users_frame, fg_color=CARD)
                row.pack(fill="x", padx=8, pady=2)
                _ck.Label(row, text="\u25cf", fg_color=CARD, text_color="#7C3AED",
                         font=("Segoe UI", 10)).pack(side="left")
                _ck.Label(row, text="{} (kamu)".format(_my_email.split("@")[0]), fg_color=CARD, text_color=FG,
                         font=("Segoe UI", 8)).pack(side="left", padx=(4, 0))
            online_count_var.set("{} online".format(
                len(users) + (0 if me_found else 1)))

        def _fetch_messages_bg():
            from modules.chat import fetch_messages
            from auth.firebase_auth import get_valid_token, refresh_id_token
            token = get_valid_token()
            if not token:
                return
            msgs = fetch_messages(token, limit=80)
            if msgs == "AUTH_EXPIRED":
                refreshed = refresh_id_token()
                if refreshed and isinstance(refreshed, dict) and "idToken" in refreshed:
                    msgs = fetch_messages(refreshed["idToken"], limit=80)
            if not isinstance(msgs, list):
                return
            if self._root:
                self._root.after(0, lambda m=msgs: _apply_messages(m))

        def _apply_messages(msgs):
            for m in msgs:
                key  = m.get("_key", str(m.get("ts", "")))
                em   = m.get("from", "")
                name = m.get("name", em.split("@")[0] if em else "?")
                text = m.get("text", "")
                ts   = m.get("ts", 0)
                if text:
                    _append(name, text, ts, key, is_me=(em == _my_email))

        def _fetch_users_bg():
            from modules.chat import fetch_online_users, update_presence
            from auth.firebase_auth import get_valid_token
            token = get_valid_token()
            if not token:
                return
            if _my_email:
                update_presence(_my_email, token, online=True)
            users = fetch_online_users(token)
            if self._root:
                self._root.after(0, lambda u=users: _update_users(u))

        def _poll_messages():
            if not self._root:
                return
            _thr.Thread(target=_fetch_messages_bg, daemon=True).start()
            interval = 3000 if self._cur == "chat" else 15000
            self._chat_poll_id = self._root.after(interval, _poll_messages)

        def _poll_users():
            if not self._root:
                return
            _thr.Thread(target=_fetch_users_bg, daemon=True).start()
            self._chat_pres_id = self._root.after(20000, _poll_users)

        # Broadcast watcher — check every 30s for master broadcasts
        _last_broadcast_ts = [0.0]
        def _fetch_broadcast_bg():
            from modules.master_config import get_broadcast
            from auth.firebase_auth import get_valid_token
            tok = get_valid_token()
            if not tok:
                return
            bc = get_broadcast(tok)
            if not bc:
                return
            bc_ts = bc.get("ts", 0)
            if bc_ts > _last_broadcast_ts[0] and bc_ts > _session_start:
                _last_broadcast_ts[0] = bc_ts
                msg = "📢 BROADCAST: {}".format(bc.get("message", ""))
                bc_text = bc.get("message", "")
                if self._root:
                    self._root.after(0, lambda m=msg, t=bc_ts: _append(
                        "Master", m, t, "bc_{}".format(bc_ts), system=True))
                def _bc_toast(t=bc_text):
                    with _toast_lock:
                        try:
                            nonlocal _toaster
                            if _toaster is None:
                                from win10toast import ToastNotifier
                                _toaster = ToastNotifier()
                            _toaster.show_toast(
                                "📢 Broadcast Synthex", t,
                                duration=8, threaded=True)
                        except Exception:
                            pass
                _thr.Thread(target=_bc_toast, daemon=True).start()

        def _poll_broadcast():
            if not self._root:
                return
            _thr.Thread(target=_fetch_broadcast_bg, daemon=True).start()
            self._broadcast_poll_id = self._root.after(30000, _poll_broadcast)

        self._root.after(5000, _poll_broadcast)

        def _send():
            text = inp_var.get().strip()
            if not text:
                return
            inp_var.set("")
            inp_entry.focus()
            def _bg():
                from modules.chat import send_message
                from auth.firebase_auth import get_valid_token
                token = get_valid_token()
                if not token:
                    return
                ok = send_message(_my_email, text, token)
                if self._root:
                    self._root.after(0, lambda: status_var.set(
                        "" if ok else "Gagal kirim — cek koneksi"))

            _thr.Thread(target=_bg, daemon=True).start()

        send_btn.configure(command=_send)
        inp_entry.bind("<Return>", lambda e: _send())

        # Stop polls when page is destroyed
        def _on_destroy(e):
            if e.widget is not f:
                return
            for attr in ("_chat_poll_id", "_chat_pres_id", "_broadcast_poll_id"):
                poll_id = getattr(self, attr, None)
                if poll_id:
                    try:
                        self._root.after_cancel(poll_id)
                    except Exception:
                        pass
                    setattr(self, attr, None)
        f.bind("<Destroy>", _on_destroy)

        # ── Kick off ─────────────────────────────────────────────────────────
        import time as _time_mod
        _session_start = _time_mod.time()

        # Wrap _apply_messages: filter ephemeral + badge + toast
        _orig_apply  = _apply_messages
        _toaster     = None
        _toast_lock  = _thr.Lock()
        def _apply_messages(msgs):  # noqa: F811
            nonlocal _toaster
            new_msgs = []
            for m in msgs:
                key = m.get("_key", str(m.get("ts", "")))
                if m.get("ts", 0) < _session_start:
                    _shown_keys[key] = 1
                    continue
                if key not in _shown_keys:
                    new_msgs.append(m)
            # Prune dict: pertahankan 200 key terbaru (insertion order = arrival order)
            if len(_shown_keys) > 400:
                drop = list(_shown_keys)[:-200]
                for k in drop:
                    del _shown_keys[k]
            _orig_apply(msgs)
            # Badge + toast only for messages while away from chat page
            if new_msgs and self._cur != "chat":
                new_count = len(new_msgs)
                if self._root:
                    self._root.after(0, lambda n=new_count: self._set_chat_badge(
                        self._chat_unread + n))
                # Windows toast notification
                last = new_msgs[-1]
                sender = last.get("name", last.get("from", "?").split("@")[0])
                text   = last.get("text", "")[:60]
                def _toast(s=sender, t=text, n=new_count):
                    nonlocal _toaster
                    with _toast_lock:
                        try:
                            if _toaster is None:
                                from win10toast import ToastNotifier
                                _toaster = ToastNotifier()
                            title = "Chat Synthex ({} pesan baru)".format(n) if n > 1 \
                                    else "Chat Synthex"
                            _toaster.show_toast(title, "{}: {}".format(s, t),
                                                duration=5, threaded=True)
                        except Exception:
                            pass
                _thr.Thread(target=_toast, daemon=True).start()

        _append("Synthex", "Selamat datang di chat! Hanya pesan baru yang tampil.",
                0, "__welcome__", system=True)
        _thr.Thread(target=_fetch_messages_bg, daemon=True).start()
        _thr.Thread(target=_fetch_users_bg,    daemon=True).start()
        self._root.after(3000,  _poll_messages)
        self._root.after(20000, _poll_users)
        inp_entry.focus()

        return f

    # ================================================================
    #  AI CHAT PAGE
    # ================================================================

    def _pg_ai_chat(self):
        import threading as _thr
        import re as _re
        from datetime import datetime as _dt

        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "AI Chat",
                  "Chat pribadi dengan AI — GPT, Claude, Gemini, Groq")

        provider   = self.config.get("ai.provider", "openai")
        api_key    = self.config.get("ai.api_key", "").strip()
        sys_prompt = self.config.get(
            "ai.system_prompt",
            "You are a helpful automation assistant. Answer concisely.")
        max_tokens = self.config.get("ai.max_tokens", 800)

        # history persists across navigations via self._ai_chat_history
        _history  = self._ai_chat_history
        _thinking = [False]
        _last_user_text = [""]   # for regenerate

        # ── model list per provider ───────────────────────────────────────────
        _PROV_MODELS = {
            "openai":    ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
            "anthropic": ["claude-opus-4-7", "claude-sonnet-4-6",
                          "claude-haiku-4-5-20251001"],
            "gemini":    ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
            "groq":      ["llama-3.3-70b-versatile", "llama3-8b-8192",
                          "mixtral-8x7b-32768"],
        }
        _saved_model = self.config.get("ai.model", "").strip()
        _m_list      = list(_PROV_MODELS.get(provider, []))
        if _saved_model and _saved_model not in _m_list:
            _m_list.insert(0, _saved_model)
        if not _m_list:
            _m_list = ["default"]
        _model_var = tk.StringVar(value=_saved_model or _m_list[0])

        def _on_model_change(*_):
            m = _model_var.get().strip()
            self.config.set("ai.model", m)
            self.config.save()

        # ── top bar ──────────────────────────────────────────────────────────
        top_bar = _ck.Frame(f, fg_color=CARD, padx=16, pady=8)
        top_bar.pack(fill="x")

        _prov_colors = {
            "openai": "#10A37F", "anthropic": "#C76B3A",
            "groq": "#F55036",   "gemini": "#4285F4",
        }
        _ck.Label(top_bar,
                 text=" {} ".format(provider.upper()), fg_color=_prov_colors.get(provider, ACC), text_color="white",
                 font=("Segoe UI", 8, "bold"),
                 padx=6, pady=3).pack(side="left")

        # Model switcher (OptionMenu styled dark)
        model_om = tk.OptionMenu(top_bar, _model_var, *_m_list,
                                 command=_on_model_change)
        model_om.configure(bg=CARD2, fg=FG, relief="flat", bd=0,
                           activebackground=CARD, activeforeground=FG,
                           font=("Segoe UI", 8), highlightthickness=0,
                           indicatoron=True, padx=6, pady=2)
        model_om["menu"].configure(bg=CARD2, fg=FG, relief="flat",
                                   activebackground=ACC, activeforeground="white",
                                   font=("Segoe UI", 8))
        model_om.pack(side="left", padx=(6, 0))

        if not api_key:
            _ck.Label(top_bar,
                     text="  ⚠ API key belum diset — Settings → AI Integration", fg_color=CARD, text_color=YEL, font=("Segoe UI", 8)).pack(
                side="left", padx=(12, 0))

        def _clear_chat():
            self._ai_chat_history.clear()
            _rebuild_messages()

        def _copy_all_chat():
            if not _history:
                return
            lines = []
            for m in _history:
                who = "Kamu" if m["role"] == "user" else provider.upper()
                ts  = m.get("ts", "")
                lines.append("[{} {}]\n{}".format(who, ts, m["content"]))
            try:
                self._root.clipboard_clear()
                self._root.clipboard_append("\n\n".join(lines))
                _copy_all_btn.configure(text="📋 Tersalin!")
                self._root.after(2000, lambda: _copy_all_btn.configure(text="📋 Salin Semua"))
            except Exception:
                pass

        _copy_all_btn = _ck.Button(top_bar, text="📋 Salin Semua", fg_color=CARD2, text_color=MUT, relief="flat", bd=0,
                  font=("Segoe UI", 8), padx=8, pady=3,
                  cursor="hand2", command=_copy_all_chat)
        _copy_all_btn.pack(side="right", padx=(0, 6))

        _ck.Button(top_bar, text="🗑 Hapus", fg_color=CARD2, text_color=MUT, relief="flat", bd=0,
                  font=("Segoe UI", 8), padx=8, pady=3,
                  cursor="hand2", command=_clear_chat).pack(side="right")

        # ── message canvas ───────────────────────────────────────────────────
        msg_outer = _ck.Frame(f, fg_color=BG)
        msg_outer.pack(fill="both", expand=True)

        msg_sb = _ck.Scrollbar(msg_outer, orient="vertical")
        msg_sb.pack(side="right", fill="y")
        msg_cv = tk.Canvas(msg_outer, bg=BG, highlightthickness=0,
                           yscrollcommand=msg_sb.set)
        msg_cv.pack(side="left", fill="both", expand=True)
        msg_sb.config(command=msg_cv.yview)
        msg_body = _ck.Frame(msg_cv, fg_color=BG)
        _mwid = msg_cv.create_window((0, 0), window=msg_body, anchor="nw")
        msg_body.bind("<Configure>",
                      lambda e: msg_cv.configure(
                          scrollregion=msg_cv.bbox("all")))
        msg_cv.bind("<Configure>",
                    lambda e: msg_cv.itemconfig(_mwid, width=e.width))

        def _on_scroll(e):
            msg_cv.yview_scroll(int(-1 * (e.delta / 120)), "units")
        msg_cv.bind("<MouseWheel>", _on_scroll)
        msg_body.bind("<MouseWheel>", _on_scroll)

        def _bind_scroll_recursive(w):
            w.bind("<MouseWheel>", _on_scroll)
            for ch in w.winfo_children():
                _bind_scroll_recursive(ch)

        def _scroll_bottom():
            if self._root:
                self._root.after(80, lambda: msg_cv.yview_moveto(1.0))

        # ── animated typing indicator ────────────────────────────────────────
        _typing_frame_ref = [None]
        _dot_idx = [0]

        _typing_frame = _ck.Frame(msg_body, fg_color=BG)
        _typing_frame_ref[0] = _typing_frame
        _dot_lbl = _ck.Label(_typing_frame, text="●", fg_color=BG, text_color=MUT, font=("Segoe UI", 11))
        _dot_lbl.pack(side="left", padx=(16, 4))
        _ck.Label(_typing_frame, text="AI sedang mengetik", fg_color=BG, text_color=MUT, font=("Segoe UI", 8, "italic")).pack(side="left")

        def _animate_typing():
            if not _thinking[0]:
                return
            frames = ["●", "● ●", "● ● ●", "● ●"]
            _dot_idx[0] = (_dot_idx[0] + 1) % len(frames)
            try:
                _dot_lbl.configure(text=frames[_dot_idx[0]])
            except Exception:
                return
            if self._root and _thinking[0]:
                self._root.after(350, _animate_typing)

        def _show_typing(show: bool):
            if show:
                _typing_frame.pack_forget()
                _typing_frame.pack(fill="x", pady=(0, 4))
                _dot_idx[0] = 0
                _animate_typing()
            else:
                _typing_frame.pack_forget()
            _scroll_bottom()

        # ── regen frame ref ──────────────────────────────────────────────────
        _regen_ref = [None]

        # ── quick prompt chips ───────────────────────────────────────────────
        _QUICK = [
            ("🔍  Analisis halaman web",   "@url [tempel URL di sini] analisis isi halaman ini"),
            ("🐛  Debug kode",             "Tolong debug kode ini:\n\n"),
            ("📋  Buat rangkuman",         "Buat rangkuman singkat dari:\n\n"),
            ("✍  Tulis email",             "Tulis email profesional tentang: "),
            ("📊  Analisis data",          "Analisis data ini dan berikan insight:\n\n"),
            ("🌐  Terjemahkan",            "Terjemahkan ke Bahasa Indonesia:\n\n"),
        ]
        _inp_ref = [None]   # forward ref untuk inp_entry

        def _build_quick_into(parent):
            _ck.Label(parent, text="Halo! Mau ngapain hari ini?", fg_color=BG, text_color=FG,
                     font=("Segoe UI", 12, "bold")).pack(pady=(20, 4))
            _ck.Label(parent,
                     text="Pilih prompt cepat atau ketik sendiri di bawah.", fg_color=BG, text_color=MUT,
                     font=("Segoe UI", 8)).pack(pady=(0, 18))
            for i in range(0, len(_QUICK), 3):
                row = _ck.Frame(parent, fg_color=BG)
                row.pack(pady=3)
                for label, prompt in _QUICK[i:i + 3]:
                    def _use(p=prompt):
                        inp = _inp_ref[0]
                        if not inp:
                            return
                        inp.delete("1.0", tk.END)
                        inp.insert("1.0", p)
                        inp.focus_set()
                        inp.mark_set("insert", tk.END)
                    _ck.Button(row, text=label, fg_color=CARD2, text_color=FG, relief="flat", bd=0,
                              font=("Segoe UI", 8), padx=10, pady=7,
                              cursor="hand2", command=_use,
                              activebackground=ACC,
                              activeforeground="white").pack(
                        side="left", padx=5)
            _ck.Label(parent,
                     text="Tip: ketik @url https://... untuk analisis isi halaman web", fg_color=BG, text_color=MUT,
                     font=("Segoe UI", 7, "italic")).pack(pady=(14, 0))

        # ── bubble builder ───────────────────────────────────────────────────
        def _add_bubble(role: str, text: str, ts: str = "",
                        is_last_ai: bool = False):
            is_user   = role == "user"
            bubble_bg = ACC    if is_user else CARD
            bubble_fg = "white" if is_user else FG
            anchor    = "e"    if is_user else "w"
            padx_l    = (80, 16) if is_user else (16, 80)
            name      = "Kamu" if is_user else provider.upper()
            name_fg   = ACC2   if is_user else MUT

            row = _ck.Frame(msg_body, fg_color=BG)
            row.pack(fill="x", pady=(0, 6))

            # Name row + timestamp + copy button (AI only)
            hdr = _ck.Frame(row, fg_color=BG)
            hdr.pack(anchor=anchor, padx=padx_l)
            _ck.Label(hdr, text=name, fg_color=BG, text_color=name_fg,
                     font=("Segoe UI", 7, "bold")).pack(side="left")
            if ts:
                _ck.Label(hdr, text="  {}".format(ts), fg_color=BG, text_color=MUT,
                         font=("Segoe UI", 7)).pack(side="left")
            if not is_user:
                def _copy_fn(t=text):
                    try:
                        self._root.clipboard_clear()
                        self._root.clipboard_append(t)
                        _cb.configure(text="✓", text_color=GRN)
                        self._root.after(1500, lambda: _cb.configure(
                            text="📋", text_color=MUT))
                    except Exception:
                        pass
                _cb = _ck.Button(hdr, text="📋", fg_color=BG, text_color=MUT,
                                relief="flat", bd=0,
                                font=("Segoe UI", 8), cursor="hand2",
                                command=_copy_fn, activebackground=BG)
                _cb.pack(side="left", padx=(6, 0))

            # Bubble
            bubble = _ck.Frame(row, fg_color=bubble_bg, padx=12, pady=8)
            bubble.pack(anchor=anchor, padx=padx_l)
            _wrap = max(280, msg_cv.winfo_width() - 160)
            _ck.Label(bubble, text=text, fg_color=bubble_bg, text_color=bubble_fg,
                     font=("Segoe UI", 9),
                     wraplength=_wrap, justify="left").pack(anchor="w")
            _bind_scroll_recursive(row)

            # Regenerate button after last AI message
            if is_last_ai:
                if _regen_ref[0]:
                    try: _regen_ref[0].destroy()
                    except Exception: pass
                rf = _ck.Frame(msg_body, fg_color=BG)
                rf.pack(anchor="w", padx=16, pady=(0, 4))
                _regen_ref[0] = rf
                _ck.Button(rf, text="↺  Ulangi jawaban", fg_color=CARD2, text_color=MUT, relief="flat", bd=0,
                          font=("Segoe UI", 8), padx=8, pady=3,
                          cursor="hand2",
                          command=lambda: _regenerate()).pack(side="left")

        # ── rebuild ──────────────────────────────────────────────────────────
        def _rebuild_messages():
            for w in msg_body.winfo_children():
                if w is _typing_frame_ref[0]:
                    continue
                try: w.destroy()
                except Exception: pass
            _regen_ref[0] = None
            if not _history:
                qf = _ck.Frame(msg_body, fg_color=BG)
                qf.pack(fill="x")
                _build_quick_into(qf)
                return
            for i, msg in enumerate(_history):
                is_last_ai = (
                    msg["role"] == "assistant"
                    and i == len(_history) - 1
                    and not _thinking[0])
                _add_bubble(msg["role"], msg["content"],
                            ts=msg.get("ts", ""),
                            is_last_ai=is_last_ai)
            _scroll_bottom()

        # ── input bar ────────────────────────────────────────────────────────
        inp_frame = _ck.Frame(f, fg_color=CARD, padx=12, pady=8)
        inp_frame.pack(fill="x", side="bottom")

        # Hint + char counter row
        meta_row = _ck.Frame(inp_frame, fg_color=CARD)
        meta_row.pack(fill="x", pady=(0, 5))
        _ck.Label(meta_row,
                 text="Enter / Ctrl+Enter kirim  •  Shift+Enter baris baru  •  @url https://... scrape web", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 7, "italic")).pack(side="left")
        char_var = tk.StringVar(value="0 karakter")
        _ck.Label(meta_row, textvariable=char_var, fg_color=CARD, text_color=MUT, font=("Segoe UI", 7)).pack(side="right")

        # Input + buttons row
        inp_row = _ck.Frame(inp_frame, fg_color=CARD)
        inp_row.pack(fill="x")

        inp_entry = _ck.Text(inp_row, height=3, fg_color="#16162a", text_color=FG, insertbackground=FG,
                            relief="flat", font=("Segoe UI", 10),
                            bd=8, wrap="word")
        inp_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        inp_entry.focus_set()
        _inp_ref[0] = inp_entry

        def _on_text_change(e=None):
            char_var.set("{} karakter".format(
                len(inp_entry.get("1.0", tk.END).strip())))
        inp_entry.bind("<KeyRelease>", _on_text_change)

        right_col = _ck.Frame(inp_row, fg_color=CARD)
        right_col.pack(side="left", fill="y")

        send_btn = _ck.Button(right_col, text="Kirim ➤", fg_color=ACC, text_color="white", relief="flat", bd=0,
                             font=("Segoe UI", 9, "bold"),
                             padx=14, pady=6, cursor="hand2")
        send_btn.pack(anchor="n")

        status_var = tk.StringVar(value="")
        status_lbl = _ck.Label(right_col, textvariable=status_var, fg_color=CARD, text_color=RED,
                              font=("Segoe UI", 8),
                              wraplength=140, justify="left")
        status_lbl.pack(anchor="n", pady=(4, 0))

        def _show_status(msg: str, color=None):
            status_var.set(msg)
            status_lbl.configure(text_color=color or RED)
            if self._root:
                self._root.after(5000, lambda: status_var.set(""))

        # ── core send logic (shared by send + regenerate) ─────────────────
        def _do_send(text: str):
            if _thinking[0] or not text:
                return
            if not api_key:
                _show_status("API key kosong — buka Settings → AI Integration")
                return
            _last_user_text[0] = text
            status_var.set("")
            inp_entry.delete("1.0", tk.END)
            char_var.set("0 karakter")
            _history.append({"role": "user", "content": text,
                             "ts": _dt.now().strftime("%H:%M")})
            _rebuild_messages()
            _show_typing(True)
            _thinking[0] = True
            send_btn.configure(state="disabled", fg_color=MUT)

            def _bg():
                try:
                    from modules.ai_client import call_ai
                    # @url scraping injection
                    actual = text
                    url_m  = _re.search(r'@url\s+(https?://\S+)', text)
                    if url_m:
                        url = url_m.group(1)
                        try:
                            from modules.web_scraper import scrape_url
                            scraped = scrape_url(url)
                            actual  = text.replace(
                                url_m.group(0),
                                "[Konten dari {}]\n{}\n".format(url, scraped))
                        except Exception as se:
                            actual = text.replace(
                                url_m.group(0),
                                "[Gagal membaca {}: {}]".format(url, se))

                    resp = call_ai(
                        prompt=actual,
                        provider=provider,
                        api_key=api_key,
                        model=_model_var.get() or None,
                        max_tokens=max_tokens,
                        system_prompt=sys_prompt,
                        history=[h for h in _history[:-1]],
                    )

                    def _ui():
                        _history.append({"role": "assistant", "content": resp,
                                         "ts": _dt.now().strftime("%H:%M")})
                        _show_typing(False)
                        _rebuild_messages()
                        _thinking[0] = False
                        send_btn.configure(state="normal", fg_color=ACC)
                    if self._root: self._root.after(0, _ui)

                except Exception as e:
                    err = str(e)[:120]
                    def _ui_err():
                        _show_typing(False)
                        _show_status(err)
                        _thinking[0] = False
                        send_btn.configure(state="normal", fg_color=ACC)
                        if _history and _history[-1]["role"] == "user":
                            _history.pop()
                        _rebuild_messages()
                    if self._root: self._root.after(0, _ui_err)

            _thr.Thread(target=_bg, daemon=True).start()

        def _send(event=None):
            _do_send(inp_entry.get("1.0", tk.END).strip())
            return "break"

        def _regenerate():
            if _history and _history[-1]["role"] == "assistant":
                _history.pop()
            if _history and _history[-1]["role"] == "user":
                last = _history.pop()
                _rebuild_messages()
                _do_send(last["content"])

        def _on_enter(event):
            if event.state & 0x1:   # Shift+Enter → newline
                return
            _send()
            return "break"

        send_btn.configure(command=_send)
        inp_entry.bind("<Return>", _on_enter)
        inp_entry.bind("<Control-Return>", lambda e: (_send(), "break")[1])

        _rebuild_messages()
        return f

    # ================================================================
    #  AI TEAM PAGE
    # ================================================================
    #  BLOG PAGE
    # ================================================================

    def _pg_blog(self):
        import threading as _thr
        import webbrowser as _wb
        import io as _io
        from datetime import datetime as _dt
        from tkinter import filedialog as _fd
        from PIL import Image as _Img, ImageTk as _ITk

        ADMIN = "yohanesnzzz777@gmail.com"
        _is_admin = (self._email == ADMIN)
        BLUE_ACC = "#0EA5E9"

        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Blog", "Artikel, foto & video dari komunitas Synthex")

        body = _ck.Frame(f, fg_color=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(8, 16))

        # ── Left: post list ──────────────────────────────────────────────────
        left = _ck.Frame(body, fg_color=CARD, width=260)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        _ck.Frame(left, fg_color=BLUE_ACC, height=4).pack(fill="x")

        top_bar = _ck.Frame(left, fg_color=CARD, padx=12, pady=8)
        top_bar.pack(fill="x")
        _ck.Label(top_bar, text="Semua Post", fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        if _is_admin:
            _ck.Button(top_bar, text="+ Tulis", fg_color=BLUE_ACC, text_color="white",
                      font=("Segoe UI", 8, "bold"), padx=8, pady=3,
                      relief="flat", bd=0, cursor="hand2",
                      command=lambda: _open_editor()).pack(side="right")

        _ck.Frame(left, fg_color=CARD2, height=1).pack(fill="x")

        list_canvas = tk.Canvas(left, bg=CARD, highlightthickness=0)
        list_sb = _ck.Scrollbar(left, command=list_canvas.yview)
        list_sb.pack(side="right", fill="y")
        list_canvas.pack(fill="both", expand=True)
        list_canvas.configure(yscrollcommand=list_sb.set)
        list_frame = _ck.Frame(list_canvas, fg_color=CARD)
        list_wid = list_canvas.create_window((0, 0), window=list_frame, anchor="nw")
        list_frame.bind("<Configure>",
                        lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))
        list_canvas.bind("<Configure>",
                         lambda e: list_canvas.itemconfig(list_wid, width=e.width))

        # ── Right: post reader ───────────────────────────────────────────────
        right = _ck.Frame(body, fg_color=CARD)
        right.pack(side="left", fill="both", expand=True)
        _ck.Frame(right, fg_color="#7C3AED", height=4).pack(fill="x")

        reader_wrap = _ck.Frame(right, fg_color="#0A0A18")
        reader_wrap.pack(fill="both", expand=True)
        reader_sb = _ck.Scrollbar(reader_wrap)
        reader_sb.pack(side="right", fill="y")
        reader = _ck.Text(reader_wrap, fg_color="#0A0A18", text_color=FG,
                         font=("Segoe UI", 10),
                         relief="flat", bd=0, wrap="word",
                         state="disabled", padx=20, pady=16,
                         yscrollcommand=reader_sb.set,
                         selectbackground=ACC)
        reader_sb.configure(command=reader.yview)
        reader.pack(side="left", fill="both", expand=True)

        reader.tag_configure("title",  foreground="white",      font=("Segoe UI", 16, "bold"))
        reader.tag_configure("meta",   foreground=MUT,          font=("Segoe UI", 8))
        reader.tag_configure("h1",     foreground="white",      font=("Segoe UI", 14, "bold"))
        reader.tag_configure("h2",     foreground="#C0C0F0",    font=("Segoe UI", 12, "bold"))
        reader.tag_configure("body",   foreground="#D0D0E0",    font=("Segoe UI", 10))
        reader.tag_configure("bold",   foreground="white",      font=("Segoe UI", 10, "bold"))
        reader.tag_configure("italic", foreground="#C8C8F0",    font=("Segoe UI", 10, "italic"))
        reader.tag_configure("code",   foreground="#A0F0A0",    font=("Consolas", 9),
                             background="#0A1A0A")
        reader.tag_configure("link",   foreground="#4A9EFF",    font=("Segoe UI", 10, "underline"))
        reader.tag_configure("empty",  foreground=MUT,          font=("Segoe UI", 10, "italic"))
        reader.tag_configure("cap",    foreground=MUT,          font=("Segoe UI", 8, "italic"),
                             justify="center")
        reader.tag_configure("video",  foreground=BLUE_ACC,     font=("Segoe UI", 9, "bold"),
                             background="#0A1428")
        reader.tag_configure("divider", foreground="#2A2A4A")

        if not hasattr(self, "_blog_photo_refs"):
            self._blog_photo_refs = []

        def _render_markdown(text: str):
            import re as _re
            for raw_line in text.split("\n"):
                line = raw_line
                if line.startswith("## "):
                    reader.insert("end", line[3:] + "\n", "h2"); continue
                if line.startswith("# "):
                    reader.insert("end", line[2:] + "\n", "h1"); continue
                pattern = _re.compile(
                    r'(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[([^\]]+)\]\([^)]+\))')
                pos = 0
                for m in pattern.finditer(line):
                    if m.start() > pos:
                        reader.insert("end", line[pos:m.start()], "body")
                    full = m.group(0)
                    if full.startswith("**"):   reader.insert("end", m.group(2), "bold")
                    elif full.startswith("*"):  reader.insert("end", m.group(3), "italic")
                    elif full.startswith("`"):  reader.insert("end", m.group(4), "code")
                    else:                       reader.insert("end", m.group(5), "link")
                    pos = m.end()
                reader.insert("end", line[pos:] + "\n", "body")

        def _load_and_show_image(url: str, caption: str):
            try:
                import requests as _rq, certifi as _ca
                resp = None
                for verify in (_ca.where(), False):
                    try:
                        resp = _rq.get(url, timeout=12, verify=verify)
                        if resp and resp.ok:
                            break
                    except Exception:
                        continue
                if not resp or not resp.ok:
                    return
                img = _Img.open(_io.BytesIO(resp.content)).convert("RGBA")
                max_w = 480
                if img.width > max_w:
                    ratio = max_w / img.width
                    img = img.resize((max_w, int(img.height * ratio)), _Img.LANCZOS)
                photo = _ITk.PhotoImage(img)
                self._blog_photo_refs.append(photo)
                if self._root and reader.winfo_exists():
                    reader.after(0, lambda ph=photo, cap=caption: _embed_image(ph, cap))
            except Exception:
                pass

        def _embed_image(photo, caption):
            reader.configure(state="normal")
            reader.insert("end", "\n")
            reader.image_create("end", image=photo, padx=20)
            if caption:
                reader.insert("end", "\n" + caption + "\n", "cap")
            reader.insert("end", "\n")
            reader.configure(state="disabled")

        def _show_video_card(url: str, caption: str):
            label = caption if caption else (url[:55] + ("..." if len(url) > 55 else ""))
            btn_text = "  ▶  Video: {}  ".format(label)
            reader.configure(state="normal")
            reader.insert("end", "\n")
            tag_id = "video_{}".format(id(url))
            reader.tag_configure(tag_id, foreground=BLUE_ACC,
                                 font=("Segoe UI", 9, "bold"), background="#0A1428")
            reader.insert("end", btn_text, tag_id)
            reader.tag_bind(tag_id, "<Button-1>", lambda e, u=url: _wb.open(u))
            reader.tag_bind(tag_id, "<Enter>",
                            lambda e: reader.configure(cursor="hand2"))
            reader.tag_bind(tag_id, "<Leave>",
                            lambda e: reader.configure(cursor=""))
            reader.insert("end", "\n\n")
            reader.configure(state="disabled")

        _posts = []

        def _show_post(post):
            self._blog_photo_refs.clear()
            reader.configure(state="normal")
            reader.delete("1.0", "end")
            ts = post.get("ts", 0)
            try: date_str = _dt.fromtimestamp(ts).strftime("%d %B %Y  %H:%M")
            except Exception: date_str = ""
            reader.insert("end", post.get("title", "Tanpa Judul") + "\n", "title")
            reader.insert("end", "oleh {}  ·  {}\n\n".format(
                post.get("author_name", "?"), date_str), "meta")
            _render_markdown(post.get("content", ""))

            media = post.get("media") or []
            if media:
                reader.insert("end", "\n" + "─" * 40 + "\n", "divider")
            reader.configure(state="disabled")

            for item in media:
                mtype = item.get("type", "")
                url   = item.get("url", "")
                cap   = item.get("caption", "")
                if not url:
                    continue
                if mtype == "image":
                    _thr.Thread(target=_load_and_show_image,
                                args=(url, cap), daemon=True).start()
                elif mtype == "video":
                    _show_video_card(url, cap)

            for w in right.winfo_children():
                if getattr(w, "_is_admin_btn", False):
                    w.destroy()
            if _is_admin:
                admin_bar = _ck.Frame(right, fg_color=CARD)
                admin_bar._is_admin_btn = True
                admin_bar.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=8)
                _ck.Button(admin_bar, text=" Edit ", fg_color="#1D4E8F", text_color="white",
                          font=("Segoe UI", 8), padx=8, pady=4,
                          relief="flat", bd=0, cursor="hand2",
                          command=lambda p=post: _open_editor(p)).pack(side="left", padx=(0, 4))
                _ck.Button(admin_bar, text=" Hapus ", fg_color="#7F1D1D", text_color="white",
                          font=("Segoe UI", 8), padx=8, pady=4,
                          relief="flat", bd=0, cursor="hand2",
                          command=lambda p=post: _delete_post(p)).pack(side="left")

        def _show_empty():
            reader.configure(state="normal")
            reader.delete("1.0", "end")
            reader.insert("end", "\n\nBelum ada post.\n", "empty")
            if _is_admin:
                reader.insert("end", "Klik '+ Tulis' untuk membuat post pertama.", "empty")
            reader.configure(state="disabled")

        def _render_list():
            for w in list_frame.winfo_children():
                w.destroy()
            if not _posts:
                _ck.Label(list_frame, text="Belum ada post.", fg_color=CARD, text_color=MUT,
                         font=("Segoe UI", 9, "italic"),
                         padx=12, pady=10).pack(anchor="w")
                _show_empty()
                return
            for p in _posts:
                ts = p.get("ts", 0)
                try: date_s = _dt.fromtimestamp(ts).strftime("%d %b %Y")
                except Exception: date_s = ""
                media_count = len(p.get("media") or [])
                card = _ck.Frame(list_frame, fg_color=CARD, cursor="hand2")
                card.pack(fill="x", pady=(0, 1))
                _ck.Frame(card, fg_color=CARD2, height=1).pack(fill="x")
                inner = _ck.Frame(card, fg_color=CARD, padx=12, pady=8)
                inner.pack(fill="x")
                _ck.Label(inner, text=p.get("title", "")[:36], fg_color=CARD, text_color=FG,
                         font=("Segoe UI", 9, "bold"),
                         wraplength=220, justify="left").pack(anchor="w")
                _ck.Label(inner, text=p.get("summary", "")[:70], fg_color=CARD, text_color=MUT,
                         font=("Segoe UI", 8),
                         wraplength=220, justify="left").pack(anchor="w", pady=(2, 0))
                meta_row = _ck.Frame(inner, fg_color=CARD)
                meta_row.pack(anchor="w", pady=(4, 0), fill="x")
                _ck.Label(meta_row, text=date_s, fg_color=CARD, text_color="#5A5A7A",
                         font=("Segoe UI", 7)).pack(side="left")
                if media_count:
                    _ck.Label(meta_row,
                             text="  \U0001f5bc {}  ".format(media_count), fg_color=CARD, text_color=BLUE_ACC,
                             font=("Segoe UI", 7)).pack(side="left")
                for w in (card, inner, meta_row):
                    w.bind("<Button-1>", lambda e, post=p: _show_post(post))
                    w.bind("<Enter>", lambda e, c=card: _deep_bg(c, "#18183A"))
                    w.bind("<Leave>", lambda e, c=card: _deep_bg(c, CARD))
            _show_post(_posts[0])

        def _load_posts():
            from modules.blog import fetch_posts
            from auth.firebase_auth import get_valid_token
            token = get_valid_token()
            if not token: return
            posts = fetch_posts(token)
            if self._root:
                self._root.after(0, lambda p=posts: _apply_posts(p))

        def _apply_posts(posts):
            _posts.clear()
            _posts.extend(posts)
            _render_list()

        def _delete_post(post):
            from modules.blog import delete_post
            from auth.firebase_auth import get_valid_token
            def _bg():
                token = get_valid_token()
                if token: delete_post(post.get("_id", ""), token)
                if self._root:
                    self._root.after(0, lambda: _thr.Thread(
                        target=_load_posts, daemon=True).start())
            _thr.Thread(target=_bg, daemon=True).start()

        # ── Editor ────────────────────────────────────────────────────────────
        def _open_editor(post=None):
            dlg = ctk.CTkToplevel(self._root)
            dlg.withdraw()
            dlg.title("Tulis Post" if not post else "Edit Post")
            dlg.configure(fg_color="#0D0D14")
            dlg.geometry("720x640")
            dlg.resizable(True, True)
            dlg.attributes("-topmost", True)

            _ck.Frame(dlg, fg_color=BLUE_ACC, height=4).pack(fill="x")
            _wrap = _ck.Frame(dlg, fg_color="#0D0D14")
            _wrap.pack(fill="both", expand=True)
            _esb = _ck.Scrollbar(_wrap, orient="vertical")
            _esb.pack(side="right", fill="y")
            _ecv = tk.Canvas(_wrap, bg="#0D0D14", highlightthickness=0,
                             yscrollcommand=_esb.set)
            _ecv.pack(side="left", fill="both", expand=True)
            _esb.config(command=_ecv.yview)
            ed = _ck.Frame(_ecv, fg_color="#0D0D14", padx=20, pady=14)
            _ewin = _ecv.create_window((0, 0), window=ed, anchor="nw")
            ed.bind("<Configure>", lambda e: _ecv.configure(
                scrollregion=_ecv.bbox("all")))
            _ecv.bind("<Configure>", lambda e: _ecv.itemconfig(_ewin, width=e.width))
            _ecv.bind("<MouseWheel>", lambda e: _ecv.yview_scroll(
                int(-1 * (e.delta / 120)), "units"))

            _ck.Label(ed, text="Judul", fg_color="#0D0D14", text_color=MUT,
                     font=("Segoe UI", 8)).pack(anchor="w")
            title_var = tk.StringVar(value=post.get("title", "") if post else "")
            _ck.Entry(ed, textvariable=title_var, fg_color="#16162a", text_color=FG, insertbackground=FG,
                     relief="flat", font=("Segoe UI", 11), bd=6).pack(
                fill="x", pady=(2, 8))

            _ck.Label(ed, text="Ringkasan (tampil di daftar)", fg_color="#0D0D14", text_color=MUT,
                     font=("Segoe UI", 8)).pack(anchor="w")
            sum_var = tk.StringVar(value=post.get("summary", "") if post else "")
            _ck.Entry(ed, textvariable=sum_var, fg_color="#16162a", text_color=FG, insertbackground=FG,
                     relief="flat", font=("Segoe UI", 9), bd=6).pack(
                fill="x", pady=(2, 8))

            _ck.Label(ed, text="Isi Artikel", fg_color="#0D0D14", text_color=MUT,
                     font=("Segoe UI", 8)).pack(anchor="w")
            fmt_bar = _ck.Frame(ed, fg_color="#1c1c2e")
            fmt_bar.pack(fill="x", pady=(2, 0))
            content_box = _ck.Text(ed, fg_color="#16162a", text_color=FG, insertbackground=FG,
                                  relief="flat", font=("Segoe UI", 10),
                                  bd=6, wrap="word", height=9)
            content_box.pack(fill="both", expand=True, pady=(0, 8))
            if post:
                content_box.insert("1.0", post.get("content", ""))

            def _wrap_sel(prefix, suffix=""):
                try:
                    sel = content_box.get(tk.SEL_FIRST, tk.SEL_LAST)
                    content_box.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    content_box.insert(tk.INSERT, prefix + sel + (suffix or prefix))
                except tk.TclError:
                    content_box.insert(tk.INSERT, prefix + (suffix or prefix))
                content_box.focus_set()

            def _insert_link():
                try:
                    sel = content_box.get(tk.SEL_FIRST, tk.SEL_LAST)
                    content_box.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    content_box.insert(tk.INSERT, "[{}](url)".format(sel))
                except tk.TclError:
                    content_box.insert(tk.INSERT, "[teks](url)")
                content_box.focus_set()

            for lbl, cmd in [
                ("B",  lambda: _wrap_sel("**")),
                ("I",  lambda: _wrap_sel("*")),
                ("`",  lambda: _wrap_sel("`")),
                ("H1", lambda: _wrap_sel("# ", "")),
                ("H2", lambda: _wrap_sel("## ", "")),
                ("\U0001f517", _insert_link),
            ]:
                _ck.Button(fmt_bar, text=lbl, fg_color="#222236", text_color=FG,
                          font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                          padx=9, pady=3, cursor="hand2",
                          command=cmd).pack(side="left", padx=(0, 2), pady=3)
            _ck.Label(fmt_bar, text="Markdown", fg_color="#1c1c2e", text_color="#4A4A6A",
                     font=("Segoe UI", 7)).pack(side="right", padx=8)

            # ── Media section ─────────────────────────────────────────────────
            media_list = list(post.get("media") or []) if post else []

            media_hdr = _ck.Frame(ed, fg_color="#0D0D14")
            media_hdr.pack(fill="x")
            _ck.Label(media_hdr, text="Media (Foto & Video)", fg_color="#0D0D14", text_color=MUT, font=("Segoe UI", 8)).pack(side="left")
            upload_status = tk.StringVar(value="")
            _ck.Label(media_hdr, textvariable=upload_status, fg_color="#0D0D14", text_color=BLUE_ACC, font=("Segoe UI", 8)).pack(side="right")

            media_frame = _ck.Frame(ed, fg_color="#0D0D14")
            media_frame.pack(fill="x", pady=(4, 0))

            def _refresh_media_ui():
                for w in media_frame.winfo_children():
                    w.destroy()
                for i, item in enumerate(media_list):
                    mtype = item.get("type", "image")
                    url   = item.get("url", "")
                    cap   = item.get("caption", "")
                    icon  = "\U0001f5bc" if mtype == "image" else "▶"
                    row = _ck.Frame(media_frame, fg_color="#16162a")
                    row.pack(fill="x", pady=(0, 3))
                    _ck.Label(row, text=icon, fg_color="#16162a",
                             font=("Segoe UI", 10)).pack(side="left", padx=(6, 4))
                    _ck.Label(row, text=(url[:52] + "..." if len(url) > 52 else url), fg_color="#16162a", text_color=FG,
                             font=("Segoe UI", 8)).pack(side="left")
                    cap_var = tk.StringVar(value=cap)
                    cap_e = _ck.Entry(row, textvariable=cap_var, width=16, fg_color="#1E1E38", text_color=MUT, insertbackground=FG,
                                     relief="flat", font=("Segoe UI", 8), bd=4)
                    cap_e.pack(side="left", padx=(6, 0))
                    def _save_cap(e, idx=i, cv=cap_var):
                        if idx < len(media_list):
                            media_list[idx]["caption"] = cv.get()
                    cap_e.bind("<FocusOut>", _save_cap)
                    cap_e.bind("<Return>",   _save_cap)
                    _ck.Button(row, text="✕", fg_color="#3A0A0A", text_color="#FF6060",
                              font=("Segoe UI", 8), relief="flat", bd=0,
                              padx=6, cursor="hand2",
                              command=lambda idx=i: (_remove_media(idx))).pack(
                                  side="right", padx=4)

            def _remove_media(idx):
                if 0 <= idx < len(media_list):
                    media_list.pop(idx)
                    _refresh_media_ui()

            def _add_image_url():
                url_dlg = ctk.CTkToplevel(dlg)
                url_dlg.withdraw()
                url_dlg.title("URL Gambar")
                url_dlg.configure(fg_color="#0D0D14")
                url_dlg.geometry("440x100")
                url_dlg.attributes("-topmost", True)
                _ck.Label(url_dlg, text="Masukkan URL gambar:", fg_color="#0D0D14", text_color=FG, font=("Segoe UI", 9)).pack(
                    anchor="w", padx=16, pady=(12, 4))
                uv = tk.StringVar()
                ue = _ck.Entry(url_dlg, textvariable=uv, fg_color="#16162a", text_color=FG,
                              insertbackground=FG, relief="flat",
                              font=("Segoe UI", 10), bd=6)
                ue.pack(fill="x", padx=16)
                ue.focus_set()
                def _ok(e=None):
                    u = uv.get().strip()
                    if u:
                        media_list.append({"type": "image", "url": u, "caption": ""})
                        _refresh_media_ui()
                    url_dlg.destroy()
                ue.bind("<Return>", _ok)
                _ck.Button(url_dlg, text="Tambah", fg_color=BLUE_ACC, text_color="white",
                          relief="flat", bd=0, padx=12, pady=4,
                          font=("Segoe UI", 9, "bold"),
                          command=_ok).pack(anchor="e", padx=16, pady=8)
                url_dlg.update()
                url_dlg.deiconify()
                url_dlg.grab_set()

            def _add_image_file():
                path = _fd.askopenfilename(
                    parent=dlg, title="Pilih Gambar",
                    filetypes=[("Image", "*.jpg *.jpeg *.png *.gif *.webp *.bmp")])
                if not path:
                    return
                upload_status.set("Mengupload…")
                def _bg():
                    from modules.blog import upload_image
                    from auth.firebase_auth import get_valid_token
                    token = get_valid_token()
                    url = upload_image(path, token) if token else None
                    if dlg.winfo_exists():
                        if url:
                            media_list.append({"type": "image", "url": url, "caption": ""})
                            dlg.after(0, lambda: (_refresh_media_ui(),
                                                  upload_status.set("✓ Selesai")))
                        else:
                            dlg.after(0, lambda: upload_status.set("Upload gagal"))
                _thr.Thread(target=_bg, daemon=True).start()

            def _add_video_url():
                url_dlg = ctk.CTkToplevel(dlg)
                url_dlg.withdraw()
                url_dlg.title("URL Video")
                url_dlg.configure(fg_color="#0D0D14")
                url_dlg.geometry("440x100")
                url_dlg.attributes("-topmost", True)
                _ck.Label(url_dlg, text="Masukkan URL video (YouTube, dll):", fg_color="#0D0D14", text_color=FG, font=("Segoe UI", 9)).pack(
                    anchor="w", padx=16, pady=(12, 4))
                uv = tk.StringVar()
                ue = _ck.Entry(url_dlg, textvariable=uv, fg_color="#16162a", text_color=FG,
                              insertbackground=FG, relief="flat",
                              font=("Segoe UI", 10), bd=6)
                ue.pack(fill="x", padx=16)
                ue.focus_set()
                def _ok(e=None):
                    u = uv.get().strip()
                    if u:
                        media_list.append({"type": "video", "url": u, "caption": ""})
                        _refresh_media_ui()
                    url_dlg.destroy()
                ue.bind("<Return>", _ok)
                _ck.Button(url_dlg, text="Tambah", fg_color="#7C3AED", text_color="white",
                          relief="flat", bd=0, padx=12, pady=4,
                          font=("Segoe UI", 9, "bold"),
                          command=_ok).pack(anchor="e", padx=16, pady=8)
                url_dlg.update()
                url_dlg.deiconify()
                url_dlg.grab_set()

            btn_row_media = _ck.Frame(ed, fg_color="#0D0D14")
            btn_row_media.pack(fill="x", pady=(6, 8))
            for lbl, cmd, bg_c in [
                ("\U0001f5bc  Gambar URL",  _add_image_url,  "#1D4E8F"),
                ("\U0001f4c2  Upload File", _add_image_file, BLUE_ACC),
                ("▶  Tambah Video",    _add_video_url,  "#7C3AED"),
            ]:
                _ck.Button(btn_row_media, text=lbl, fg_color=bg_c, text_color="white",
                          font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                          padx=10, pady=5, cursor="hand2",
                          command=cmd).pack(side="left", padx=(0, 6))

            _refresh_media_ui()

            sub_row = _ck.Frame(ed, fg_color="#0D0D14")
            sub_row.pack(anchor="e", pady=(4, 0))

            def _submit():
                title   = title_var.get().strip()
                summary = sum_var.get().strip()
                content = content_box.get("1.0", "end").strip()
                if not title or not content:
                    return
                def _bg():
                    from auth.firebase_auth import get_valid_token
                    token = get_valid_token()
                    if token:
                        if post:
                            from modules.blog import update_post
                            update_post(post["_id"], title, content,
                                        summary, token, media_list)
                        else:
                            from modules.blog import create_post
                            create_post(title, content, summary,
                                        ADMIN, token, media_list)
                    if self._root:
                        self._root.after(0, lambda: _thr.Thread(
                            target=_load_posts, daemon=True).start())
                dlg.destroy()
                _thr.Thread(target=_bg, daemon=True).start()

            btn_lbl = "Simpan Perubahan" if post else "Publikasikan"
            _ck.Button(sub_row, text=btn_lbl, fg_color=BLUE_ACC, text_color="white",
                      font=("Segoe UI", 9, "bold"), padx=16, pady=6,
                      relief="flat", cursor="hand2",
                      command=_submit).pack(side="left", padx=(0, 8))
            _ck.Button(sub_row, text="Batal", fg_color="#1c1c2e", text_color=MUT,
                      font=("Segoe UI", 9), padx=12, pady=6,
                      relief="flat", cursor="hand2",
                      command=dlg.destroy).pack(side="left")
            dlg.update()
            dlg.deiconify()
            dlg.grab_set()

        _show_empty()
        _thr.Thread(target=_load_posts, daemon=True).start()
        return f

    def _pg_history(self):
        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Activity History")
        c = _card(f)
        c.pack(fill="both", expand=True, padx=20, pady=(8, 20))
        t = _tree(c, [
            ("time",   "Time",   160),
            ("task",   "Task",   200),
            ("result", "Result", 220),
            ("ok",     "Status",  60),
        ])
        for e in self._ud.activity:
            t.insert("", "end", values=(
                e["time"], e["task"], e["result"],
                "OK" if e.get("ok") else "FAIL",
            ))
        def _clear_history():
            self._ud.activity.clear()
            self._ud.save()
            t.delete(*t.get_children())

        _ck.Button(c, text="Clear All",
                   command=_clear_history).pack(anchor="e", pady=(8, 0))
        return f

    # ================================================================
    #  SETTINGS PAGE
    # ================================================================

    # ================================================================
    #  Backup helpers
    # ================================================================

    def _backup_now(self, last_lbl):
        """Run create_backup() in a thread and update the label + toast."""
        def _run():
            from utils.backup import AutoBackup
            ab   = AutoBackup()
            path = ab.create_backup()
            if path:
                label = ab.last_backup_label()
                self._root.after(0, lambda: last_lbl.configure(
                    text=f"Last backup: {label}"))
                self._root.after(0, lambda: self._show_toast(
                    "Backup saved!", kind="success"))
            else:
                self._root.after(0, lambda: self._show_toast(
                    "Backup failed – check logs.", kind="error"))
        threading.Thread(target=_run, daemon=True).start()

    def _restore_backup_dialog(self):
        """Show a Toplevel listing available backups; restore on selection."""
        from utils.backup import AutoBackup
        ab      = AutoBackup()
        backups = ab.list_backups()

        if not backups:
            self._show_alert("Restore", "No backups found.")
            return

        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Restore from Backup")
        dlg.configure(fg_color=BG)
        dlg.resizable(False, False)
        dlg.update()
        dlg.deiconify()
        dlg.grab_set()

        _lbl(dlg, "Select a backup to restore:", fg_color=BG,
             font=("Segoe UI", 10, "bold")).pack(padx=20, pady=(16, 8))

        lb_frame = _ck.Frame(dlg, fg_color=BG)
        lb_frame.pack(padx=20, fill="both", expand=True)

        lb = tk.Listbox(lb_frame, bg=CARD, fg=FG, selectbackground=ACC,
                        font=("Segoe UI", 9), relief="flat",
                        width=36, height=min(len(backups), 8))
        lb.pack(side="left", fill="both", expand=True)
        sb = _ck.Scrollbar(lb_frame, orient="vertical", command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.configure(yscrollcommand=sb.set)

        for b in backups:
            size_kb = b["size"] // 1024
            lb.insert(tk.END, f"  {b['name']}  ({size_kb} KB)")
        lb.selection_set(0)

        def _do_restore():
            idx = lb.curselection()
            if not idx:
                return
            chosen = backups[idx[0]]
            dlg.destroy()
            if not self._confirm_dialog(
                    "Konfirmasi Restore",
                    "Restore dari {}?\nData saat ini akan ditimpa.".format(chosen["name"]),
                    confirm_text="Ya, Restore", accent=YEL):
                return
            def _run():
                ok = ab.restore_backup(chosen["path"])
                kind = "success" if ok else "error"
                msg  = "Restore complete!" if ok else "Restore failed – check logs."
                self._root.after(0, lambda: self._show_toast(msg, kind=kind))
            threading.Thread(target=_run, daemon=True).start()

        btn_row = _ck.Frame(dlg, fg_color=BG)
        btn_row.pack(padx=20, pady=12, anchor="e")
        _ck.Button(btn_row, text="Cancel",
                   command=dlg.destroy).pack(side="left", padx=(0, 8))
        _ck.Button(btn_row, text="Restore", fg_color=ACC, text_color=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat",
                  padx=10, pady=4, cursor="hand2",
                  command=_do_restore).pack(side="left")

    def _pg_settings(self):
        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Settings")

        # Scrollable container for all settings cards
        _ssb = _ck.Scrollbar(f, orient="vertical")
        _ssb.pack(side="right", fill="y")
        _scv = tk.Canvas(f, bg=BG, highlightthickness=0, yscrollcommand=_ssb.set)
        _scv.pack(side="left", fill="both", expand=True)
        _ssb.config(command=_scv.yview)
        _sbody = _ck.Frame(_scv, fg_color=BG)
        _swin = _scv.create_window((0, 0), window=_sbody, anchor="nw")
        _sbody.bind("<Configure>", lambda e: _scv.configure(
            scrollregion=_scv.bbox("all")))
        _scv.bind("<Configure>", lambda e: _scv.itemconfig(_swin, width=e.width))
        _scv.bind("<MouseWheel>", lambda e: _scv.yview_scroll(
            int(-1 * (e.delta / 120)), "units"))

        # ---- Tema Aplikasi card ---------------------------------------
        tc = _card(_sbody, "Tema Aplikasi")
        tc.pack(fill="x", padx=20, pady=(8, 0))

        _cur_theme = self.config.get("ui.theme", "dark")
        _theme_var = tk.StringVar(value=_cur_theme)

        theme_row = _ck.Frame(tc, fg_color=CARD)
        theme_row.pack(anchor="w", pady=(0, 10))
        for _lbl_t, _val_t in [("🌙  Dark", "dark"), ("☀️  Light", "light")]:
            _ck.Radiobutton(
                theme_row, text=_lbl_t, variable=_theme_var, value=_val_t, fg_color=CARD, text_color=FG, selectcolor=CARD2,
                activebackground=CARD, activeforeground=ACC,
                font=("Segoe UI", 10)
            ).pack(side="left", padx=(0, 24))

        def _apply_theme():
            sel = _theme_var.get()
            if sel == self.config.get("ui.theme", "dark"):
                self._show_toast("Tema sudah aktif.", kind="info")
                return
            # Save to config.json
            self.config.set("ui.theme", sel)
            self.config.save()
            cfg_path = os.path.join(_ROOT, "config.json")
            try:
                with open(cfg_path, encoding="utf-8") as _fp:
                    _cfg = json.load(_fp)
                _cfg.setdefault("ui", {})["theme"] = sel
                with open(cfg_path, "w", encoding="utf-8") as _fp:
                    json.dump(_cfg, _fp, indent=2)
            except Exception:
                pass
            if self._confirm_dialog(
                    "Restart Diperlukan",
                    "Perubahan tema berlaku setelah restart.\nRestart Synthex sekarang?",
                    confirm_text="Restart", cancel_text="Nanti"):
                import subprocess as _sp
                _sp.Popen([sys.executable] + sys.argv)
                import os as _os2; _os2._exit(0)

        _ck.Button(tc, text="Terapkan Tema", fg_color=ACC, text_color=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=12, pady=5, cursor="hand2",
                  command=_apply_theme).pack(anchor="w")

        # ---- Backup & Restore card ------------------------------------
        from utils.backup import AutoBackup
        _ab = AutoBackup()

        bc = _card(_sbody, "Backup & Restore")
        bc.pack(fill="x", padx=20, pady=(8, 0))

        info_row = _ck.Frame(bc, fg_color=CARD)
        info_row.pack(fill="x", pady=(0, 8))
        last_lbl = _lbl(info_row,
                        f"Last backup: {_ab.last_backup_label()}", text_color=MUT, fg_color=CARD, font=("Segoe UI", 9))
        last_lbl.pack(side="left")
        _lbl(info_row, "  |  Auto-backup: Daily", text_color=MUT, fg_color=CARD, font=("Segoe UI", 9)).pack(side="left")

        btn_row_b = _ck.Frame(bc, fg_color=CARD)
        btn_row_b.pack(anchor="w")
        _ck.Button(btn_row_b, text="Backup Now", fg_color=ACC, text_color=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
                  command=lambda: self._backup_now(last_lbl)).pack(
                      side="left", padx=(0, 10))
        _ck.Button(btn_row_b, text="Restore from Backup",
                   command=self._restore_backup_dialog).pack(side="left")

        # ---- Rekening API card ----------------------------------------
        rak = _card(_sbody, "Rekening API")
        rak.pack(fill="x", padx=20, pady=(12, 0))

        _rak_row = _ck.Frame(rak, fg_color=CARD)
        _rak_row.pack(anchor="w", fill="x")
        _rak_has_key = bool(self.config.get("rekening_api_key", ""))
        _ck.Label(_rak_row, text="[*]", fg_color=CARD, text_color=GRN if _rak_has_key else MUT,
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 8))
        _rak_info = _ck.Frame(_rak_row, fg_color=CARD)
        _rak_info.pack(side="left")
        _ck.Label(_rak_info, text="API Validasi Rekening", fg_color=CARD, text_color=FG, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        _ck.Label(_rak_info,
                 text="Aktif — disediakan oleh Synthex" if _rak_has_key else "Tidak aktif", fg_color=CARD, text_color=GRN if _rak_has_key else RED,
                 font=("Segoe UI", 9)).pack(anchor="w")

        # ---- Google Accounts card ------------------------------------
        self._build_google_accounts_card(_sbody)

        # ---- AI card --------------------------------------------------
        from modules.ai_client import PROVIDER_LABELS, PROVIDER_NAMES
        aic = _card(_sbody, "🤖 AI Integration")
        aic.pack(fill="x", padx=20, pady=(8, 0))

        _ai_provider_var = tk.StringVar(
            value=self.config.get("ai.provider", "openai"))
        _ai_key_var = tk.StringVar(
            value=self.config.get("ai.api_key", ""))
        _ai_model_var = tk.StringVar(
            value=self.config.get("ai.model", ""))
        _ai_tokens_var = tk.StringVar(
            value=str(self.config.get("ai.max_tokens", 800)))
        _ai_sys_var = tk.StringVar(
            value=self.config.get("ai.system_prompt",
                "You are a helpful automation assistant. Answer concisely."))

        # Provider row
        pr_row = _ck.Frame(aic, fg_color=CARD)
        pr_row.pack(fill="x", pady=(0, 6))
        _ck.Label(pr_row, text="Provider:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))
        _prov_disp = [PROVIDER_LABELS[PROVIDER_NAMES.index(
            self.config.get("ai.provider", "openai")
            if self.config.get("ai.provider", "openai") in PROVIDER_NAMES
            else "openai")]]
        _prov_mb = _ck.Combobox(pr_row, values=PROVIDER_LABELS,
                                state="readonly", width=24,
                                font=("Segoe UI", 9))
        _prov_mb.set(_prov_disp[0])
        _prov_mb.pack(side="left")

        def _on_prov_change(*_):
            idx = PROVIDER_LABELS.index(_prov_mb.get())
            _ai_provider_var.set(PROVIDER_NAMES[idx])
        _prov_mb.bind("<<ComboboxSelected>>", _on_prov_change)

        # API Key row
        key_row = _ck.Frame(aic, fg_color=CARD)
        key_row.pack(fill="x", pady=(0, 6))
        _ck.Label(key_row, text="API Key:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))
        _key_entry = _ck.Entry(key_row, textvariable=_ai_key_var, fg_color=CARD2, text_color=FG, insertbackground=FG,
                              relief="flat", font=("Segoe UI", 9), show="*",
                              width=34)
        _key_entry.pack(side="left")
        _show_key = [False]
        def _toggle_show():
            _show_key[0] = not _show_key[0]
            _key_entry.configure(show="" if _show_key[0] else "*")
        _ck.Button(key_row, text="👁", fg_color=CARD2, text_color=MUT,
                  relief="flat", bd=0, font=("Segoe UI", 9),
                  padx=4, cursor="hand2",
                  command=_toggle_show).pack(side="left", padx=(4, 0))

        # Model + max tokens row
        mod_row = _ck.Frame(aic, fg_color=CARD)
        mod_row.pack(fill="x", pady=(0, 6))
        _ck.Label(mod_row, text="Model (opsional):", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))
        _ck.Entry(mod_row, textvariable=_ai_model_var, fg_color=CARD2, text_color=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 9),
                 width=22).pack(side="left")
        _ck.Label(mod_row, text="  Max tokens:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 4))
        _ck.Entry(mod_row, textvariable=_ai_tokens_var, fg_color=CARD2, text_color=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 9), width=6).pack(side="left")

        # System prompt
        _ck.Label(aic, text="System Prompt default:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))
        _sys_txt = _ck.Text(aic, fg_color=CARD2, text_color=FG, insertbackground=FG,
                           relief="flat", font=("Segoe UI", 9),
                           height=2, wrap="word")
        _sys_txt.insert("1.0", _ai_sys_var.get())
        _sys_txt.pack(fill="x", pady=(0, 8))

        # Buttons row
        ai_btn_row = _ck.Frame(aic, fg_color=CARD)
        ai_btn_row.pack(anchor="w", pady=(0, 4))
        _ai_status = tk.StringVar(value="")
        _ck.Label(aic, textvariable=_ai_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w")

        def _save_ai():
            self.config.set("ai.provider", _ai_provider_var.get())
            self.config.set("ai.api_key",  _ai_key_var.get().strip())
            self.config.set("ai.model",    _ai_model_var.get().strip())
            try:
                self.config.set("ai.max_tokens", int(_ai_tokens_var.get()))
            except ValueError:
                pass
            self.config.set("ai.system_prompt", _sys_txt.get("1.0", "end").strip())
            self.config.save()
            _ai_status.set("✓ Tersimpan")

        def _test_ai():
            _save_ai()
            _ai_status.set("Menguji koneksi AI…")
            def _bg():
                try:
                    from modules.ai_client import call_ai
                    resp = call_ai(
                        prompt="Reply with exactly: SYNTHEX_OK",
                        provider=self.config.get("ai.provider", "openai"),
                        api_key=self.config.get("ai.api_key", ""),
                        model=self.config.get("ai.model", ""),
                        system="",
                        max_tokens=20,
                    )
                    msg = "✓ Terhubung! Response: {}".format(resp[:60])
                except Exception as e:
                    msg = "✗ Gagal: {}".format(str(e)[:80])
                if self._root:
                    self._root.after(0, lambda m=msg: _ai_status.set(m))
            threading.Thread(target=_bg, daemon=True).start()

        _ck.Button(ai_btn_row, text="💾 Simpan", fg_color=ACC, text_color="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
                  command=_save_ai).pack(side="left", padx=(0, 8))
        _ck.Button(ai_btn_row, text="🔌 Test Koneksi", fg_color=CARD2, text_color=FG, font=("Segoe UI", 9),
                  relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
                  command=_test_ai).pack(side="left")

        # ---- Update card ----------------------------------------------
        upc = _card(_sbody, "Pembaruan Aplikasi")
        upc.pack(fill="x", padx=20, pady=(8, 0))
        _cur_ver = self.config.get("app.version", "?")
        _upd_status = tk.StringVar(value="Versi saat ini: v{}".format(_cur_ver))
        _upd_lbl = _ck.Label(upc, textvariable=_upd_status, fg_color=CARD, text_color=MUT,
                            font=("Segoe UI", 9))
        _upd_lbl.pack(anchor="w", pady=(0, 6))
        _upd_bar_frame = _ck.Frame(upc, fg_color=CARD)
        _upd_bar_frame.pack(anchor="w", fill="x", pady=(0, 4))
        _upd_prog = ttk.Progressbar(_upd_bar_frame, mode="determinate",
                                    length=200, maximum=100)

        def _do_check_update(auto=False):
            _upd_status.set("Memeriksa pembaruan…")
            def _bg():
                from modules.updater import get_latest_release, is_newer
                rel = get_latest_release()
                if not rel:
                    if self._root:
                        self._root.after(0, lambda: _upd_status.set(
                            "Tidak bisa cek — periksa koneksi internet."))
                    return
                tag = rel["tag"]
                local = self.config.get("app.version", "0")
                if not is_newer(tag, local):
                    if self._root:
                        self._root.after(0, lambda: _upd_status.set(
                            "✓ Kamu sudah pakai versi terbaru (v{})".format(local)))
                    return
                # Newer version available
                if auto:
                    if self._root:
                        self._root.after(0, lambda t=tag: _prompt_update(t, rel["url"]))
                    return
                if self._root:
                    self._root.after(0, lambda t=tag, u=rel["url"]: _prompt_update(t, u))
            threading.Thread(target=_bg, daemon=True).start()

        def _prompt_update(tag, url):
            _upd_status.set("Versi baru tersedia: {} — unduh sekarang?".format(tag))
            if self._show_confirm("Update Tersedia",
                    "Versi {} sudah tersedia.\n"
                    "Unduh dan install sekarang?\n\n"
                    "Synthex akan restart otomatis setelah selesai.".format(tag)):
                _do_download(url, tag)

        def _do_download(url, tag):
            _upd_status.set("Mengunduh {}…".format(tag))
            _upd_prog.pack(side="left", padx=(0, 8))
            _upd_prog["value"] = 0

            def _prog(ratio):
                if self._root:
                    self._root.after(0, lambda r=ratio: _upd_prog.configure(
                        value=int(r * 100)))

            def _bg():
                from modules.updater import download_and_replace
                ok = download_and_replace(url, progress_cb=_prog)
                if self._root:
                    if ok:
                        self._root.after(0, lambda: _upd_status.set(
                            "✓ Selesai! Synthex akan restart sekarang…"))
                        self._root.after(1500, self._root.destroy)
                    else:
                        self._root.after(0, lambda: _upd_status.set(
                            "Gagal mengunduh. Coba lagi atau unduh manual dari GitHub."))
                        self._root.after(0, _upd_prog.pack_forget)
            threading.Thread(target=_bg, daemon=True).start()

        _ck.Button(upc, text="🔄 Cek Pembaruan", fg_color=ACC, text_color="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
                  command=_do_check_update).pack(anchor="w")

        # Auto-check update on first open of settings (silent)
        threading.Thread(target=lambda: _do_check_update(auto=True),
                         daemon=True).start()

        # ---- Appearance card -----------------------------------------
        apc = _card(_sbody, "Tampilan")
        apc.pack(fill="x", padx=20, pady=(12, 0))
        _cur_theme = self.config.get("ui.theme", "dark")
        _theme_lbl = _ck.Label(apc,
            text="Tema saat ini: {}".format("Gelap 🌙" if _cur_theme == "dark" else "Terang ☀️"), fg_color=CARD, text_color=FG, font=("Segoe UI", 9))
        _theme_lbl.pack(anchor="w", pady=(0, 6))
        def _toggle_theme():
            new_t = "light" if self.config.get("ui.theme", "dark") == "dark" else "dark"
            self.config.set("ui.theme", new_t)
            self.config.save()
            _theme_lbl.configure(
                text="Tema saat ini: {}".format("Gelap 🌙" if new_t == "dark" else "Terang ☀️"))
            self._show_alert("Tema Diubah",
                "Tema berhasil disimpan ke '{}'.\nRestart Synthex untuk menerapkan tema baru.".format(
                    new_t), kind="info")
        _ck.Button(apc, text="Toggle Gelap / Terang", fg_color=ACC, text_color="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
                  command=_toggle_theme).pack(anchor="w")

        # ---- Account card ---------------------------------------------
        ac = _card(_sbody, "Account")
        ac.pack(fill="x", padx=20, pady=(12, 0))
        _lbl(ac, "Email: {}".format(self._email or "-"), fg_color=CARD).pack(
            anchor="w")
        btn_row = _ck.Frame(ac, fg_color=CARD)
        btn_row.pack(anchor="w", pady=(8, 0))
        _ck.Button(btn_row, text="Logout",
                   command=self._logout).pack(side="left", padx=(0, 10))
        _ck.Button(btn_row, text="Setup Guide", fg_color=ACC, text_color=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
                  command=self._launch_onboarding).pack(side="left")
        lc = _card(_sbody, "System Log")
        lc.pack(fill="x", padx=20, pady=(12, 20))
        self._lw = _ck.ScrolledText(
            lc, fg_color=BG, text_color=FG, insertbackground=FG,
            font=("Consolas", 9), relief="flat", state="disabled")
        self._lw.pack(fill="both", expand=True)
        for tag, clr in [("info", FG), ("warn", YEL),
                         ("error", RED), ("debug", MUT)]:
            self._lw.tag_configure(tag, foreground=clr)
        h = _TkLogHandler(self._lw)
        h.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(h)
        return f

    # ================================================================
    #  INBOX PAGE  (DM — all users)
    # ================================================================

    def _pg_inbox(self):
        import threading as _thr
        from datetime import datetime as _dt

        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "📬 Inbox",
                  "Percakapan langsung dengan Admin Synthex")

        email = self._email or ""
        token = self._token or ""

        # ── Main layout: messages top, input bottom ───────────────────────────
        main = _ck.Frame(f, fg_color=BG)
        main.pack(fill="both", expand=True, padx=18, pady=(0, 12))

        # Messages area (scrollable canvas)
        msg_sb = _ck.Scrollbar(main, orient="vertical")
        msg_sb.pack(side="right", fill="y")
        msg_cv = tk.Canvas(main, bg=BG, highlightthickness=0,
                           yscrollcommand=msg_sb.set)
        msg_cv.pack(side="left", fill="both", expand=True)
        msg_sb.config(command=msg_cv.yview)

        msg_inner = _ck.Frame(msg_cv, fg_color=BG)
        _mwid = msg_cv.create_window((0, 0), window=msg_inner, anchor="nw")
        msg_inner.bind("<Configure>",
                       lambda e: msg_cv.configure(scrollregion=msg_cv.bbox("all")))
        msg_cv.bind("<Configure>",
                    lambda e: msg_cv.itemconfig(_mwid, width=e.width))
        def _blog_scroll(e, _cv=msg_cv):
            try:
                if _cv.winfo_exists() and _cv.winfo_ismapped():
                    _cv.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass
        msg_cv.bind_all("<MouseWheel>", _blog_scroll)

        # Status / loading label
        _status = tk.StringVar(value="Memuat pesan…")
        status_lbl = _ck.Label(msg_inner, textvariable=_status, fg_color=BG, text_color=MUT, font=("Segoe UI", 9))
        status_lbl.pack(pady=20)

        def _render_messages(msgs):
            for w in msg_inner.winfo_children():
                w.destroy()
            if not msgs:
                _ck.Label(msg_inner,
                         text="Belum ada pesan dari Admin.\nPesan akan muncul di sini.", fg_color=BG, text_color=MUT, font=("Segoe UI", 10),
                         justify="center").pack(pady=60)
                return

            for m in msgs:
                is_master = (m.get("from", "") == self.MASTER_EMAIL)
                ts = m.get("ts", 0)
                try:
                    t_str = _dt.fromtimestamp(ts).strftime("%d %b  %H:%M")
                except Exception:
                    t_str = ""

                row = _ck.Frame(msg_inner, fg_color=BG, pady=4)
                row.pack(fill="x", padx=12)

                if is_master:
                    # Admin message — left side, purple tint
                    bubble_bg = "#1E1B4B"
                    name_clr  = "#A78BFA"
                    side      = "left"
                    name_txt  = "👑 Admin"
                else:
                    # User reply — right side, dark green tint
                    bubble_bg = "#052e16"
                    name_clr  = "#34D399"
                    side      = "right"
                    name_txt  = "Kamu"

                wrap_row = _ck.Frame(row, fg_color=BG)
                wrap_row.pack(anchor="w" if side == "left" else "e")

                bubble = _ck.Frame(wrap_row, fg_color=bubble_bg, padx=12, pady=8)
                bubble.pack(side="left" if side == "left" else "right")

                _ck.Label(bubble, text=name_txt, fg_color=bubble_bg, text_color=name_clr,
                         font=("Segoe UI", 7, "bold")).pack(anchor="w")
                _ck.Label(bubble, text=m.get("message", ""), fg_color=bubble_bg, text_color=FG,
                         font=("Segoe UI", 10), wraplength=420,
                         justify="left").pack(anchor="w", pady=(2, 0))
                _ck.Label(bubble, text=t_str, fg_color=bubble_bg, text_color=MUT,
                         font=("Segoe UI", 7)).pack(anchor="e", pady=(2, 0))

            # Scroll to bottom
            msg_cv.update_idletasks()
            msg_cv.yview_moveto(1.0)

        def _load():
            try:
                from modules.master_config import get_dm, mark_all_dm_read
                msgs = get_dm(email, token)
                if self._root:
                    self._root.after(0, lambda m=msgs: _render_messages(m))
                # Mark all read + clear badge
                mark_all_dm_read(email, token)
                if self._root:
                    self._root.after(0, lambda: self._set_inbox_badge(0))
            except Exception as ex:
                if self._root:
                    self._root.after(0, lambda: _status.set("Gagal memuat: {}".format(ex)))

        # ── Input area ────────────────────────────────────────────────────────
        sep = _ck.Frame(f, fg_color="#1c1c2e", height=1)
        sep.pack(fill="x", padx=18)

        inp_area = _ck.Frame(f, fg_color=BG, padx=18, pady=10)
        inp_area.pack(fill="x")

        inp_box = _ck.Text(inp_area, fg_color=CARD2, text_color=FG, insertbackground=FG,
                          relief="flat", font=("Segoe UI", 10), height=3,
                          wrap="word", bd=8)
        inp_box.pack(side="left", fill="x", expand=True, padx=(0, 10))
        inp_box.insert("1.0", "")

        def _send_reply(event=None):
            msg = inp_box.get("1.0", "end").strip()
            if not msg:
                return "break"
            inp_box.delete("1.0", "end")
            def _bg():
                try:
                    from modules.master_config import reply_dm, get_dm
                    reply_dm(email, msg, token)
                    msgs = get_dm(email, token)
                    if self._root:
                        self._root.after(0, lambda m=msgs: _render_messages(m))
                except Exception:
                    pass
            _thr.Thread(target=_bg, daemon=True).start()
            return "break"

        inp_box.bind("<Return>", lambda e: _send_reply() if not (e.state & 0x1) else None)

        btn_col = _ck.Frame(inp_area, fg_color=BG)
        btn_col.pack(side="right")
        _ck.Button(btn_col, text="📨 Kirim", fg_color=ACC, text_color="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", bd=0, padx=16, pady=10, cursor="hand2",
                  command=_send_reply).pack(fill="x")
        _ck.Label(btn_col, text="Enter = kirim\nShift+Enter = baris baru", fg_color=BG, text_color=MUT, font=("Segoe UI", 7)).pack(pady=(4, 0))

        # Refresh button
        def _refresh():
            _status.set("Memuat…")
            for w in msg_inner.winfo_children():
                w.destroy()
            _thr.Thread(target=_load, daemon=True).start()

        _ck.Button(f, text="🔄 Refresh", fg_color=CARD2, text_color=FG, font=("Segoe UI", 8),
                  relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                  command=_refresh).place(relx=1.0, x=-30, y=10, anchor="ne")

        _thr.Thread(target=_load, daemon=True).start()
        return f

    # ================================================================
    #  MASTER PANEL PAGE
    # ================================================================

    def _pg_master(self):
        import threading as _thr
        from datetime import datetime as _dt

        f = _ck.Frame(self._content, fg_color=BG)

        _email_now = self._email
        if _email_now != self.MASTER_EMAIL:
            _ck.Label(f, text="Akses ditolak.", fg_color=BG, text_color=RED,
                     font=("Segoe UI", 14, "bold")).pack(pady=40)
            return f

        def _tok():
            from auth.firebase_auth import get_valid_token
            tok = get_valid_token()
            if not tok:
                self.logger.warning("master panel: token kosong, Firebase calls akan gagal")
            return tok

        # ── Header crown bar ─────────────────────────────────────────────────
        hdr = _ck.Frame(f, fg_color="#0D0D1F", padx=20, pady=14)
        hdr.pack(fill="x")
        _ck.Label(hdr, text="\U0001f451", fg_color="#0D0D1F", text_color="#F59E0B",
                 font=("Segoe UI", 22)).pack(side="left", padx=(0, 12))
        hdr_txt = _ck.Frame(hdr, fg_color="#0D0D1F")
        hdr_txt.pack(side="left")
        _ck.Label(hdr_txt, text="Master Panel", fg_color="#0D0D1F", text_color=FG,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        _ck.Label(hdr_txt, text=self.MASTER_EMAIL, fg_color="#0D0D1F", text_color="#7C3AED",
                 font=("Segoe UI", 8)).pack(anchor="w")
        _ck.Frame(f, fg_color="#7C3AED", height=2).pack(fill="x")

        # ── Scrollable body ──────────────────────────────────────────────────
        _msb = _ck.Scrollbar(f, orient="vertical")
        _msb.pack(side="right", fill="y")
        _mcv = tk.Canvas(f, bg=BG, highlightthickness=0, yscrollcommand=_msb.set)
        _mcv.pack(side="left", fill="both", expand=True)
        _msb.config(command=_mcv.yview)
        body = _ck.Frame(_mcv, fg_color=BG)
        _mwid = _mcv.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: _mcv.configure(
            scrollregion=_mcv.bbox("all")))
        _mcv.bind("<Configure>", lambda e: _mcv.itemconfig(_mwid, width=e.width))
        _mcv.bind("<MouseWheel>", lambda e: _mcv.yview_scroll(
            int(-1 * (e.delta / 120)), "units"))


        # ── Card + section helpers ───────────────────────────────────────────
        def _hex_blend(hex_a, hex_b, t):
            ar, ag, ab = int(hex_a[1:3], 16), int(hex_a[3:5], 16), int(hex_a[5:7], 16)
            br, bg2, bb = int(hex_b[1:3], 16), int(hex_b[3:5], 16), int(hex_b[5:7], 16)
            return "#{:02x}{:02x}{:02x}".format(
                int(ar + (br - ar) * t), int(ag + (bg2 - ag) * t),
                int(ab + (bb - ab) * t))

        def _mk(parent, title, icon, accent):
            wrap = _ck.Frame(parent, fg_color=BG)
            wrap.pack(fill="x", padx=16, pady=(0, 10))
            _ck.Frame(wrap, fg_color=accent, width=4).pack(side="left", fill="y")
            inner = _ck.Frame(wrap, fg_color=CARD, padx=16, pady=14)
            inner.pack(side="left", fill="both", expand=True)
            hrow = _ck.Frame(inner, fg_color=CARD)
            hrow.pack(fill="x", pady=(0, 10))
            bdg_bg = _hex_blend(CARD, accent, 0.22)
            bdg = _ck.Frame(hrow, fg_color=bdg_bg, padx=8, pady=4)
            bdg.pack(side="left", padx=(0, 10))
            _ck.Label(bdg, text=icon, fg_color=bdg_bg, text_color=accent,
                     font=("Segoe UI", 14)).pack()
            _ck.Label(hrow, text=title, fg_color=CARD, text_color=FG,
                     font=("Segoe UI", 11, "bold")).pack(side="left", anchor="w")
            return inner

        def _sect(parent, label):
            row = _ck.Frame(parent, fg_color=BG)
            row.pack(fill="x", padx=16, pady=(16, 6))
            _ck.Label(row, text=label.upper(), fg_color=BG, text_color="#5B5B8A",
                     font=("Segoe UI", 7, "bold")).pack(side="left")
            _ck.Frame(row, fg_color="#2A2A4A", height=1).pack(
                side="left", fill="x", expand=True, padx=(8, 0), pady=5)

        def _btn(parent, text, bg, text_color="white", cmd=None, **kw):
            defaults = dict(font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                            padx=14, pady=6, cursor="hand2")
            defaults.update(kw)
            return _ck.Button(parent, text=text, fg_color=bg, text_color=text_color, command=cmd, **defaults)

        # ══════════════════════════════════════════════════════════════════════
        # STATS BAR
        # ══════════════════════════════════════════════════════════════════════
        stats_row = _ck.Frame(body, fg_color=BG)
        stats_row.pack(fill="x", padx=16, pady=(16, 4))
        _sb = {}
        for col, (icon, key, lbl, clr) in enumerate([
            ("\U0001f465", "users",  "Total Sesi",  GRN),
            ("\U0001f7e2", "online", "Online Now",  "#22D3EE"),
            ("\U0001f6ab", "banned", "Dibanned",    RED),
            ("\U0001f4ac", "dm",     "DM Baru",     PRP),
        ]):
            box = _ck.Frame(stats_row, fg_color=CARD, padx=12, pady=10)
            box.grid(row=0, column=col, padx=(0, 8), sticky="nsew")
            stats_row.columnconfigure(col, weight=1)
            _ck.Label(box, text=icon, fg_color=CARD, text_color=clr,
                     font=("Segoe UI", 18)).pack()
            v = _ck.Label(box, text="—", fg_color=CARD, text_color=clr,
                         font=("Segoe UI", 20, "bold"))
            v.pack()
            _ck.Label(box, text=lbl, fg_color=CARD, text_color=MUT,
                     font=("Segoe UI", 7)).pack()
            _sb[key] = v

        def _load_stats_bar():
            from modules.master_config import (get_all_sessions, get_online_count,
                                               get_banned_list, get_all_dm_threads)
            tok = _tok() or ""
            users   = get_all_sessions(tok)
            online  = get_online_count(tok)
            banned  = get_banned_list(tok)
            threads = get_all_dm_threads(tok)
            dm_new  = sum(t["unread"] for t in threads)
            def _u():
                _sb["users"].config(text=str(len(users)))
                _sb["online"].config(text=str(online))
                _sb["banned"].config(text=str(len(banned)))
                _sb["dm"].config(text=str(dm_new))
            if self._root:
                self._root.after(0, _u)
        _thr.Thread(target=_load_stats_bar, daemon=True).start()

        # ══════════════════════════════════════════════════════════════════════
        # WHO'S ONLINE
        # ══════════════════════════════════════════════════════════════════════
        _sect(body, "Who's Online")
        _wo_card = _mk(body, "User Aktif Sekarang", "\U0001f7e2", "#22D3EE")

        _wo_status = tk.StringVar(value="Memuat…")
        _ck.Label(_wo_card, textvariable=_wo_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))

        _wo_list_frame = _ck.Frame(_wo_card, fg_color=CARD)
        _wo_list_frame.pack(fill="x")

        def _render_online(users):
            for w in _wo_list_frame.winfo_children():
                w.destroy()
            if not users:
                _ck.Label(_wo_list_frame, text="Tidak ada user online saat ini.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 9)).pack(anchor="w")
                return
            for u in users:
                row = _ck.Frame(_wo_list_frame, fg_color=CARD2, pady=5, padx=10)
                row.pack(fill="x", pady=(0, 3))
                _ck.Label(row, text="\U0001f7e2", fg_color=CARD2, text_color="#22D3EE",
                         font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))
                _ck.Label(row, text=u["email"], fg_color=CARD2, text_color=FG,
                         font=("Segoe UI", 9, "bold")).pack(side="left")
                secs = int(time.time() - u.get("last_seen", time.time()))
                if secs < 60:
                    ago = "baru saja"
                elif secs < 3600:
                    ago = "{}m lalu".format(secs // 60)
                else:
                    ago = "{}j lalu".format(secs // 3600)
                _ck.Label(row, text=ago, fg_color=CARD2, text_color=MUT,
                         font=("Segoe UI", 8)).pack(side="right")

        _wo_refresh_id = [None]

        def _refresh_online():
            def _bg():
                from modules.chat import fetch_online_users
                users = fetch_online_users(_tok() or "", stale_sec=120)
                def _ui():
                    _wo_status.set("Online: {}  •  Refresh otomatis tiap 30 detik".format(len(users)))
                    _render_online(users)
                    _wo_refresh_id[0] = body.after(30000, _refresh_online)
                if self._root:
                    self._root.after(0, _ui)
            _thr.Thread(target=_bg, daemon=True).start()

        _refresh_online()

        def _stop_wo_refresh():
            if _wo_refresh_id[0]:
                try: body.after_cancel(_wo_refresh_id[0])
                except Exception: pass
        _wo_card.bind("<Destroy>", lambda e: _stop_wo_refresh())

        _btn(_wo_card, "\U0001f504 Refresh Sekarang", "#22D3EE", "#000",
             cmd=lambda: (_stop_wo_refresh(), _refresh_online())).pack(anchor="w", pady=(8, 0))

        # ══════════════════════════════════════════════════════════════════════
        # APP CONTROL
        # ══════════════════════════════════════════════════════════════════════
        _sect(body, "App Control")

        # ── Maintenance Mode ─────────────────────────────────────────────────
        mnt = _mk(body, "Maintenance Mode", "\U0001f527", RED)
        _ck.Label(mnt, text="Aktifkan untuk memblokir semua user masuk ke app.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 8))
        _mnt_en = tk.BooleanVar(value=False)
        mnt_row = _ck.Frame(mnt, fg_color=CARD)
        mnt_row.pack(fill="x", pady=(0, 6))
        _ck.Checkbutton(mnt_row, text="MAINTENANCE AKTIF (user diblokir)",
                       variable=_mnt_en, fg_color=CARD, text_color=RED, selectcolor=CARD2,
                       activebackground=CARD,
                       font=("Segoe UI", 9, "bold")).pack(side="left")
        _ck.Label(mnt, text="Pesan yang ditampilkan ke user:", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 2))
        _mnt_msg = tk.StringVar()
        _ck.Entry(mnt, textvariable=_mnt_msg, fg_color=CARD2, text_color=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 10),
                 bd=6).pack(fill="x", pady=(0, 8))
        _mnt_status = tk.StringVar(value="Memuat…")
        _ck.Label(mnt, textvariable=_mnt_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))

        def _load_mnt():
            from modules.master_config import get_maintenance
            d = get_maintenance(_tok() or "")
            def _f():
                _mnt_en.set(bool(d.get("enabled", False)))
                _mnt_msg.set(d.get("message",
                                   "Sedang dalam maintenance. Coba lagi nanti."))
                _mnt_status.set("Dimuat dari Firebase.")
            if self._root:
                self._root.after(0, _f)

        def _save_mnt():
            _mnt_status.set("Menyimpan…")
            def _bg():
                from modules.master_config import set_maintenance
                ok = set_maintenance(_mnt_en.get(), _mnt_msg.get(), _tok())
                state = "AKTIF" if _mnt_en.get() else "NONAKTIF"
                m = "✓ Maintenance {}!".format(state) if ok else "✗ Gagal."
                if self._root:
                    self._root.after(0, lambda: _mnt_status.set(m))
            _thr.Thread(target=_bg, daemon=True).start()

        _btn(mnt, "\U0001f4be Simpan Maintenance", RED, cmd=_save_mnt).pack(anchor="w")
        _thr.Thread(target=_load_mnt, daemon=True).start()

        # ── Force Update ─────────────────────────────────────────────────────
        fu = _mk(body, "Force Update / Min Version", "\U0001f4e6", "#F59E0B")
        _ck.Label(fu, text="User dengan versi lebih lama akan dipaksa update.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 8))
        fu_row = _ck.Frame(fu, fg_color=CARD)
        fu_row.pack(fill="x", pady=(0, 6))
        _fu_ver = tk.StringVar()
        _ck.Label(fu_row, text="Min Version:", fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 9)).pack(side="left")
        _ck.Entry(fu_row, textvariable=_fu_ver, fg_color=CARD2, text_color=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 10),
                 bd=6, width=12).pack(side="left", padx=6)
        _fu_status = tk.StringVar(value="Memuat…")
        _ck.Label(fu, textvariable=_fu_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        def _load_fu():
            from modules.master_config import get_min_version
            v = get_min_version(_tok() or "")
            if self._root:
                self._root.after(0, lambda: (
                    _fu_ver.set(v),
                    _fu_status.set("Min version saat ini: {}".format(v))))

        def _set_fu():
            v = _fu_ver.get().strip()
            if not v:
                return
            _fu_status.set("Menyimpan…")
            def _bg():
                from modules.master_config import set_min_version
                ok = set_min_version(v, _tok())
                m = ("✓ Min version diset ke {}!".format(v) if ok
                     else "✗ Gagal.")
                if self._root:
                    self._root.after(0, lambda: _fu_status.set(m))
            _thr.Thread(target=_bg, daemon=True).start()

        _btn(fu_row, "✔ Set", "#F59E0B", text_color="black",
             cmd=_set_fu).pack(side="left")
        _thr.Thread(target=_load_fu, daemon=True).start()

        # ── Announcement Bar ─────────────────────────────────────────────────
        ann = _mk(body, "Announcement Bar", "\U0001f4e3", "#0EA5E9")
        _ck.Label(ann, text="Tampilkan banner pesan di atas app semua user.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))
        _ann_en = tk.BooleanVar(value=False)
        ann_r1 = _ck.Frame(ann, fg_color=CARD)
        ann_r1.pack(fill="x", pady=(0, 4))
        _ck.Label(ann_r1, text="Aktif:", fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 9)).pack(side="left")
        _ck.Checkbutton(ann_r1, variable=_ann_en, fg_color=CARD, text_color=FG,
                       selectcolor=CARD2, activebackground=CARD,
                       font=("Segoe UI", 9)).pack(side="left", padx=4)
        _ann_clr = tk.StringVar(value="#B45309")
        _clr_opts = ["#B45309", "#1E40AF", "#065F46", "#7C2D12",
                     "#6B21A8", "#BE123C"]
        ann_r2 = _ck.Frame(ann, fg_color=CARD)
        ann_r2.pack(fill="x", pady=(0, 4))
        _ck.Label(ann_r2, text="Warna:", fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 9)).pack(side="left")
        ann_clr_m = tk.OptionMenu(ann_r2, _ann_clr, *_clr_opts)
        ann_clr_m.config(bg=CARD2, fg=FG, relief="flat",
                         highlightthickness=0, font=("Segoe UI", 9),
                         activebackground=ACC)
        ann_clr_m.pack(side="left", padx=4)
        ann_txt = _ck.Entry(ann, fg_color=CARD2, text_color=FG, insertbackground=FG,
                           relief="flat", font=("Segoe UI", 10), bd=6)
        ann_txt.pack(fill="x", pady=(0, 6))
        _ann_status = tk.StringVar(value="")
        _ck.Label(ann, textvariable=_ann_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        def _set_ann():
            txt = ann_txt.get().strip()
            if not txt:
                _ann_status.set("✗ Teks tidak boleh kosong.")
                return
            _ann_status.set("Menyimpan…")
            def _bg():
                from modules.master_config import set_announcement
                ok = set_announcement(txt, _ann_clr.get(), _ann_en.get(), _tok())
                if self._root:
                    self._root.after(0, lambda: _ann_status.set(
                        "✓ Announcement diupdate!" if ok else "✗ Gagal."))
            _thr.Thread(target=_bg, daemon=True).start()

        def _load_ann():
            import requests, certifi
            tok = _tok()
            if not tok:
                return
            RTDB = "https://synthex-yohn18-default-rtdb.asia-southeast1.firebasedatabase.app"
            try:
                r = requests.get(
                    "{}/master_config/announcement.json?auth={}".format(RTDB, tok),
                    timeout=8, verify=certifi.where())
                d = r.json() if r.ok else None
            except Exception:
                d = None
            if d and isinstance(d, dict):
                def _fill():
                    ann_txt.delete(0, "end")
                    ann_txt.insert(0, d.get("text", ""))
                    _ann_clr.set(d.get("color", "#B45309"))
                    _ann_en.set(bool(d.get("enabled", False)))
                    _ann_status.set("Dimuat dari Firebase.")
                if self._root:
                    self._root.after(0, _fill)

        _btn(ann, "\U0001f4be Simpan Announcement", "#0EA5E9",
             cmd=_set_ann).pack(anchor="w")
        _thr.Thread(target=_load_ann, daemon=True).start()

        # ── Remote Config Toggles ─────────────────────────────────────────────
        rc = _mk(body, "Remote Config — Toggle Fitur", "⚙️", "#6366F1")
        _ck.Label(rc, text="Toggle on/off fitur untuk SEMUA user secara realtime.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 8))
        _RC_LABELS = {
            "rekening_enabled": "\U0001f4b3 Cek Rekening",
            "chat_enabled":     "\U0001f4ac Chat",
            "blog_enabled":     "\U0001f4f0 Blog",
            "remote_enabled":   "\U0001f5a5️ Remote Control",
            "monitor_enabled":  "\U0001f4ca Monitor",
            "spy_enabled":      "\U0001f441️ Spy",
        }
        _rc_vars = {k: tk.BooleanVar(value=True) for k in _RC_LABELS}
        rc_grid = _ck.Frame(rc, fg_color=CARD)
        rc_grid.pack(fill="x", pady=(0, 8))
        for i, (k, lbl) in enumerate(_RC_LABELS.items()):
            r_f = _ck.Frame(rc_grid, fg_color=CARD)
            r_f.grid(row=i // 2, column=i % 2, sticky="w", padx=8, pady=2)
            _ck.Checkbutton(r_f, text=lbl, variable=_rc_vars[k], fg_color=CARD, text_color=FG, selectcolor=CARD2,
                           activebackground=CARD,
                           font=("Segoe UI", 9)).pack(side="left")
        _rc_status = tk.StringVar(value="Memuat…")
        _ck.Label(rc, textvariable=_rc_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        def _load_rc():
            from modules.master_config import get_remote_config
            cfg = get_remote_config(_tok() or "")
            def _fill():
                for k, var in _rc_vars.items():
                    var.set(cfg.get(k, True))
                _rc_status.set("Remote config dimuat.")
            if self._root:
                self._root.after(0, _fill)

        def _save_rc():
            cfg = {k: v.get() for k, v in _rc_vars.items()}
            _rc_status.set("Menyimpan…")
            def _bg():
                from modules.master_config import set_remote_config
                ok = set_remote_config(cfg, _tok())
                if self._root:
                    self._root.after(0, lambda: _rc_status.set(
                        "✓ Remote config disimpan!" if ok else "✗ Gagal."))
            _thr.Thread(target=_bg, daemon=True).start()

        _btn(rc, "\U0001f4be Simpan Remote Config", "#6366F1",
             cmd=_save_rc).pack(anchor="w")
        _thr.Thread(target=_load_rc, daemon=True).start()

        # ══════════════════════════════════════════════════════════════════════
        # KONTEN & RELEASE
        # ══════════════════════════════════════════════════════════════════════
        _sect(body, "Konten & Release")

        # ── Changelog Editor ─────────────────────────────────────────────────
        cl = _mk(body, "Changelog / Release Notes", "\U0001f4dd", "#8B5CF6")
        _ck.Label(cl, text="Popup akan muncul ke user saat versi berubah.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))
        cl_vrow = _ck.Frame(cl, fg_color=CARD)
        cl_vrow.pack(fill="x", pady=(0, 4))
        _ck.Label(cl_vrow, text="Versi:", fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 9)).pack(side="left")
        _cl_ver = tk.StringVar()
        _ck.Entry(cl_vrow, textvariable=_cl_ver, fg_color=CARD2, text_color=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 9),
                 bd=6, width=12).pack(side="left", padx=6)
        _ck.Label(cl, text="Release notes:", fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 2))
        cl_txt = _ck.Text(cl, fg_color=CARD2, text_color=FG, insertbackground=FG,
                         relief="flat", font=("Segoe UI", 9),
                         height=5, wrap="word")
        cl_txt.pack(fill="x", pady=(0, 6))
        _cl_status = tk.StringVar(value="Memuat…")
        _ck.Label(cl, textvariable=_cl_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        def _load_cl():
            from modules.master_config import get_changelog
            d = get_changelog(_tok() or "")
            if d:
                def _fill():
                    _cl_ver.set(d.get("version", ""))
                    cl_txt.delete("1.0", "end")
                    cl_txt.insert("1.0", d.get("notes", ""))
                    _cl_status.set("Changelog terakhir dimuat.")
                if self._root:
                    self._root.after(0, _fill)
            else:
                if self._root:
                    self._root.after(0, lambda: _cl_status.set("Belum ada changelog."))

        def _pub_cl():
            ver = _cl_ver.get().strip()
            notes = cl_txt.get("1.0", "end").strip()
            if not ver or not notes:
                _cl_status.set("✗ Versi dan notes wajib diisi.")
                return
            _cl_status.set("Mempublish…")
            def _bg():
                from modules.master_config import set_changelog
                ok = set_changelog(ver, notes, _tok())
                if self._root:
                    self._root.after(0, lambda: _cl_status.set(
                        "✓ Changelog v{} dipublish!".format(ver)
                        if ok else "✗ Gagal."))
            _thr.Thread(target=_bg, daemon=True).start()

        _btn(cl, "\U0001f4e4 Publish Changelog", "#8B5CF6",
             cmd=_pub_cl).pack(anchor="w")
        _thr.Thread(target=_load_cl, daemon=True).start()

        # ── Firebase Templates Sync ───────────────────────────────────────────
        tpl = _mk(body, "Firebase Templates Sync", "\U0001f4cb", GRN)
        _ck.Label(tpl,
                 text="Push template lokal ke Firebase → semua user dapat template"
                      " terbaru tanpa rebuild.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8),
                 wraplength=500, justify="left").pack(anchor="w", pady=(0, 8))
        _tpl_count = _ck.Label(tpl, text="", fg_color=CARD, text_color=FG,
                              font=("Segoe UI", 9, "bold"))
        _tpl_count.pack(anchor="w", pady=(0, 4))
        _tpl_status = tk.StringVar(value="")
        _ck.Label(tpl, textvariable=_tpl_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))

        def _count_local():
            import json
            p = os.path.join(_ROOT, "data", "templates.json")
            try:
                with open(p, encoding="utf-8") as fh:
                    n = len(json.load(fh))
            except Exception:
                n = 0
            if self._root:
                self._root.after(0, lambda: _tpl_count.config(
                    text="{} template lokal tersedia".format(n)))

        def _push_templates():
            _tpl_status.set("Mengirim ke Firebase…")
            def _bg():
                import json
                from modules.master_config import set_firebase_templates
                p = os.path.join(_ROOT, "data", "templates.json")
                try:
                    with open(p, encoding="utf-8") as fh:
                        tpls = json.load(fh)
                except Exception as e:
                    if self._root:
                        self._root.after(0, lambda: _tpl_status.set(
                            "✗ Gagal baca lokal: {}".format(e)))
                    return
                ok = set_firebase_templates(tpls, _tok())
                msg = ("✓ {} template dipush ke Firebase!".format(len(tpls))
                       if ok else "✗ Gagal push.")
                if self._root:
                    self._root.after(0, lambda: _tpl_status.set(msg))
            _thr.Thread(target=_bg, daemon=True).start()

        def _pull_templates():
            _tpl_status.set("Mengambil dari Firebase…")
            def _bg():
                import json
                from modules.master_config import get_firebase_templates
                tpls = get_firebase_templates(_tok())
                if not tpls:
                    if self._root:
                        self._root.after(0, lambda: _tpl_status.set(
                            "✗ Tidak ada template di Firebase."))
                    return
                p = os.path.join(_ROOT, "data", "templates.json")
                try:
                    with open(p, "w", encoding="utf-8") as fh:
                        json.dump(tpls, fh, indent=2, ensure_ascii=False)
                    msg = "✓ {} template ditarik & disimpan lokal!".format(len(tpls))
                except Exception as e:
                    msg = "✗ Gagal simpan lokal: {}".format(e)
                if self._root:
                    self._root.after(0, lambda: (
                        _tpl_status.set(msg), _count_local()))
            _thr.Thread(target=_bg, daemon=True).start()

        tpl_btns = _ck.Frame(tpl, fg_color=CARD)
        tpl_btns.pack(anchor="w")
        _btn(tpl_btns, "\U0001f4e4 Push ke Firebase", GRN, text_color="black",
             cmd=_push_templates).pack(side="left", padx=(0, 8))
        _btn(tpl_btns, "\U0001f4e5 Pull dari Firebase", CARD2, text_color=FG,
             cmd=_pull_templates).pack(side="left")
        _thr.Thread(target=_count_local, daemon=True).start()

        # ══════════════════════════════════════════════════════════════════════
        # USER MANAGEMENT
        # ══════════════════════════════════════════════════════════════════════
        _sect(body, "User Management")

        # ── Whitelist ─────────────────────────────────────────────────────────
        wl = _mk(body, "Whitelist Akses", "\U0001f511", "#0EA5E9")
        _ck.Label(wl, text="Aktifkan whitelist → hanya email terdaftar yang bisa login.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))
        _wl_en = tk.BooleanVar(value=False)
        wl_r = _ck.Frame(wl, fg_color=CARD)
        wl_r.pack(fill="x", pady=(0, 4))
        _ck.Checkbutton(wl_r, text="Whitelist Aktif", variable=_wl_en, fg_color=CARD, text_color=FG, selectcolor=CARD2,
                       activebackground=CARD,
                       font=("Segoe UI", 9, "bold")).pack(side="left")
        _ck.Label(wl, text="Daftar email (satu per baris):", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 2))
        wl_txt = _ck.Text(wl, fg_color=CARD2, text_color=FG, insertbackground=FG,
                         relief="flat", font=("Segoe UI", 9),
                         height=5, wrap="none")
        wl_txt.pack(fill="x", pady=(0, 6))
        _wl_status = tk.StringVar(value="Memuat…")
        _ck.Label(wl, textvariable=_wl_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        def _load_wl():
            from modules.master_config import get_whitelist
            d = get_whitelist(_tok() or "")
            def _fill():
                _wl_en.set(d.get("enabled", False))
                emails = [k.replace(",", ".").replace("@at@", "@")
                          for k in d.get("emails", {}).keys()]
                wl_txt.delete("1.0", "end")
                wl_txt.insert("1.0", "\n".join(emails))
                _wl_status.set("Whitelist dimuat ({} email).".format(len(emails)))
            if self._root:
                self._root.after(0, _fill)

        def _save_wl():
            emails = [e.strip() for e in wl_txt.get("1.0", "end").splitlines()
                      if e.strip()]
            _wl_status.set("Menyimpan…")
            def _bg():
                from modules.master_config import set_whitelist
                ok = set_whitelist(_wl_en.get(), emails, _tok())
                if self._root:
                    self._root.after(0, lambda: _wl_status.set(
                        "✓ Whitelist disimpan ({} email)!".format(len(emails))
                        if ok else "✗ Gagal."))
            _thr.Thread(target=_bg, daemon=True).start()

        _btn(wl, "\U0001f4be Simpan Whitelist", "#0EA5E9",
             cmd=_save_wl).pack(anchor="w")
        _thr.Thread(target=_load_wl, daemon=True).start()

        # ── Kick / Ban ────────────────────────────────────────────────────────
        kb = _mk(body, "Kick / Ban User", "\U0001f6ab", RED)
        _ck.Label(kb, text="Kick = paksa logout. Ban = blokir login permanen.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))
        kb_ir = _ck.Frame(kb, fg_color=CARD)
        kb_ir.pack(fill="x", pady=(0, 6))
        _kb_email = tk.StringVar()
        _ck.Label(kb_ir, text="Email:", fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 9)).pack(side="left")
        _ck.Entry(kb_ir, textvariable=_kb_email, fg_color=CARD2, text_color=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 9),
                 bd=6, width=28).pack(side="left", padx=6)
        _kb_status = tk.StringVar(value="")
        _ck.Label(kb, textvariable=_kb_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        def _do_kick():
            em = _kb_email.get().strip()
            if not em:
                _kb_status.set("✗ Email kosong.")
                return
            _kb_status.set("Kicking {}…".format(em))
            def _bg():
                from modules.master_config import kick_user
                ok = kick_user(em, _tok())
                if self._root:
                    self._root.after(0, lambda: _kb_status.set(
                        "✓ {} di-kick!".format(em) if ok
                        else "✗ Gagal kick."))
            _thr.Thread(target=_bg, daemon=True).start()

        def _do_ban():
            em = _kb_email.get().strip()
            if not em:
                _kb_status.set("✗ Email kosong.")
                return
            _kb_status.set("Banning {}…".format(em))
            def _bg():
                from modules.master_config import ban_user, kick_user as ku
                tok = _tok()
                ban_user(em, tok)
                ku(em, tok)
                if self._root:
                    self._root.after(0, lambda: _kb_status.set(
                        "✓ {} di-ban & di-kick!".format(em)))
            _thr.Thread(target=_bg, daemon=True).start()

        def _do_unban():
            em = _kb_email.get().strip()
            if not em:
                _kb_status.set("✗ Email kosong.")
                return
            _kb_status.set("Unbanning {}…".format(em))
            def _bg():
                from modules.master_config import unban_user
                ok = unban_user(em, _tok())
                if self._root:
                    self._root.after(0, lambda: _kb_status.set(
                        "✓ {} di-unban!".format(em) if ok
                        else "✗ Gagal unban."))
            _thr.Thread(target=_bg, daemon=True).start()

        kb_btns = _ck.Frame(kb, fg_color=CARD)
        kb_btns.pack(fill="x", pady=(0, 8))
        _ck.Button(kb_btns, text="\U0001f462 Kick", fg_color="#92400E", text_color="white",
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=12, pady=5, cursor="hand2",
                  command=_do_kick).pack(side="left", padx=(0, 6))
        _ck.Button(kb_btns, text="\U0001f6ab Ban + Kick", fg_color=RED, text_color="white",
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=12, pady=5, cursor="hand2",
                  command=_do_ban).pack(side="left", padx=(0, 6))
        _ck.Button(kb_btns, text="✅ Unban", fg_color=GRN, text_color="white",
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=12, pady=5, cursor="hand2",
                  command=_do_unban).pack(side="left")
        _ck.Label(kb, text="Daftar user yang di-ban:", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 2))
        kb_list = _ck.Frame(kb, fg_color=CARD)
        kb_list.pack(fill="x")

        def _load_banned():
            from modules.master_config import get_banned_list
            banned = get_banned_list(_tok() or "")
            def _upd():
                for w in kb_list.winfo_children():
                    w.destroy()
                if not banned:
                    _ck.Label(kb_list, text="Tidak ada user yang di-ban.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8),
                             padx=6).pack(anchor="w")
                    return
                for em in banned:
                    row = _ck.Frame(kb_list, fg_color=CARD)
                    row.pack(fill="x", pady=1)
                    _ck.Label(row, text="\U0001f6ab {}".format(em), fg_color=CARD, text_color=RED,
                             font=("Segoe UI", 8)).pack(side="left")
                    _ck.Button(row, text="Unban", fg_color=CARD2, text_color=FG,
                              font=("Segoe UI", 7), relief="flat", bd=0,
                              padx=6, pady=2, cursor="hand2",
                              command=lambda e=em: (
                                  _kb_email.set(e), _do_unban())
                              ).pack(side="right")
            if self._root:
                self._root.after(0, _upd)

        _ck.Button(kb, text="\U0001f504 Refresh Banned List", fg_color=CARD2, text_color=FG, font=("Segoe UI", 8),
                  relief="flat", bd=0, padx=10, pady=3, cursor="hand2",
                  command=lambda: _thr.Thread(
                      target=_load_banned, daemon=True).start()
                  ).pack(anchor="w", pady=(6, 4))
        _thr.Thread(target=_load_banned, daemon=True).start()

        # ── Online Users ──────────────────────────────────────────────────────
        ou = _mk(body, "User Online Sekarang", "\U0001f465", "#22D3EE")
        _ou_status = tk.StringVar(value="Memuat…")
        _ck.Label(ou, textvariable=_ou_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))
        ou_frame = _ck.Frame(ou, fg_color=CARD)
        ou_frame.pack(fill="x")

        def _load_users():
            from modules.chat import fetch_online_users
            from auth.firebase_auth import get_valid_token
            tok = get_valid_token()
            if not tok:
                return
            users = fetch_online_users(tok, stale_sec=120)
            def _upd():
                for w in ou_frame.winfo_children():
                    w.destroy()
                _ou_status.set("{} user online (aktif < 2 menit):".format(len(users)))
                for u in users:
                    em = u.get("email", "")
                    ts = u.get("last_seen", 0)
                    try:
                        t_str = _dt.fromtimestamp(ts).strftime("%H:%M:%S")
                    except Exception:
                        t_str = "-"
                    row = _ck.Frame(ou_frame, fg_color=CARD, padx=10, pady=4)
                    row.pack(fill="x")
                    _ck.Label(row, text="●", fg_color=CARD, text_color=GRN,
                             font=("Segoe UI", 9)).pack(side="left")
                    _ck.Label(row, text=em, fg_color=CARD, text_color=FG,
                             font=("Segoe UI", 9, "bold")).pack(
                        side="left", padx=(6, 0))
                    _ck.Label(row, text="last seen {}".format(t_str), fg_color=CARD, text_color=MUT,
                             font=("Segoe UI", 8)).pack(side="right")
                if not users:
                    _ck.Label(ou_frame,
                             text="Tidak ada user lain yang online.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 9),
                             padx=10, pady=6).pack(anchor="w")
            if self._root:
                self._root.after(0, _upd)

        _ck.Button(ou, text="\U0001f504 Refresh", fg_color=CARD2, text_color=FG, font=("Segoe UI", 8),
                  relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                  command=lambda: _thr.Thread(
                      target=_load_users, daemon=True).start()
                  ).pack(anchor="w", pady=(0, 8))
        _thr.Thread(target=_load_users, daemon=True).start()

        # ── Statistics ────────────────────────────────────────────────────────
        st = _mk(body, "Statistik Pengguna", "\U0001f4ca", "#A78BFA")
        _sl = {}
        st_grid = _ck.Frame(st, fg_color=CARD)
        st_grid.pack(fill="x", pady=(0, 8))
        for col, (icon, key, lbl, clr) in enumerate([
            ("\U0001f465", "sessions", "Total Sesi", GRN),
            ("\U0001f7e2", "online2",  "Online Now", "#22D3EE"),
            ("\U0001f6ab", "banned2",  "Dibanned",   RED),
        ]):
            box = _ck.Frame(st_grid, fg_color=CARD2, padx=16, pady=12)
            box.grid(row=0, column=col, padx=6, sticky="nsew")
            st_grid.columnconfigure(col, weight=1)
            _ck.Label(box, text=icon, fg_color=CARD2, text_color=clr,
                     font=("Segoe UI", 20)).pack()
            v = _ck.Label(box, text="…", fg_color=CARD2, text_color=clr,
                         font=("Segoe UI", 18, "bold"))
            v.pack()
            _ck.Label(box, text=lbl, fg_color=CARD2, text_color=MUT,
                     font=("Segoe UI", 7)).pack()
            _sl[key] = v
        _st_status = tk.StringVar(value="Memuat statistik…")
        _ck.Label(st, textvariable=_st_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        def _load_stats():
            from modules.master_config import (get_all_sessions, get_online_count,
                                               get_banned_list)
            tok = _tok() or ""
            sess   = get_all_sessions(tok)
            online = get_online_count(tok)
            banned = get_banned_list(tok)
            def _upd():
                _sl["sessions"].config(text=str(len(sess)))
                _sl["online2"].config(text=str(online))
                _sl["banned2"].config(text=str(len(banned)))
                _st_status.set("Diperbarui. {} sesi, {} online, {} banned.".format(
                    len(sess), online, len(banned)))
            if self._root:
                self._root.after(0, _upd)

        _ck.Button(st, text="\U0001f504 Refresh Statistik", fg_color=CARD2, text_color=FG, font=("Segoe UI", 8),
                  relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                  command=lambda: _thr.Thread(
                      target=_load_stats, daemon=True).start()
                  ).pack(anchor="w")
        _thr.Thread(target=_load_stats, daemon=True).start()

        # ══════════════════════════════════════════════════════════════════════
        # KOMUNIKASI
        # ══════════════════════════════════════════════════════════════════════
        _sect(body, "Komunikasi")

        # ── Broadcast ─────────────────────────────────────────────────────────
        bc = _mk(body, "Broadcast ke Semua User", "\U0001f4e2", PRP)
        _ck.Label(bc, text="Pesan broadcast akan muncul di Chat semua user yang online.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))
        bc_txt = _ck.Text(bc, fg_color=CARD2, text_color=FG, insertbackground=FG,
                         relief="flat", font=("Segoe UI", 10),
                         height=3, wrap="word")
        bc_txt.pack(fill="x", pady=(0, 8))
        _bc_status = tk.StringVar(value="")
        _ck.Label(bc, textvariable=_bc_status, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        def _send_bc():
            msg = bc_txt.get("1.0", "end").strip()
            if not msg:
                return
            _bc_status.set("Mengirim…")
            def _bg():
                from modules.master_config import send_broadcast
                from auth.firebase_auth import get_valid_token
                tok = get_valid_token()
                ok = send_broadcast(msg, tok) if tok else False
                if self._root:
                    self._root.after(0, lambda: (
                        _bc_status.set(
                            "✓ Broadcast terkirim!" if ok else "✗ Gagal."),
                        bc_txt.delete("1.0", "end") if ok else None))
            _thr.Thread(target=_bg, daemon=True).start()

        _btn(bc, "\U0001f4e2 Kirim Broadcast", PRP, cmd=_send_bc,
             font=("Segoe UI", 10, "bold"), pady=8).pack(anchor="w")

        # ── DM Conversations ──────────────────────────────────────────────────
        dm = _mk(body, "DM — Percakapan dengan User", "\U0001f4ac", ACC)
        _ck.Label(dm, text="Pilih user → lihat percakapan → balas.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 8))
        dm_split = _ck.Frame(dm, fg_color=CARD)
        dm_split.pack(fill="x")
        dm_left = _ck.Frame(dm_split, fg_color="#0D0D18", width=200)
        dm_left.pack(side="left", fill="y", padx=(0, 8))
        dm_left.pack_propagate(False)
        _ck.Label(dm_left, text="Inbox", fg_color="#0D0D18", text_color=MUT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=8, pady=(6, 2))
        thread_frame = _ck.Frame(dm_left, fg_color="#0D0D18")
        thread_frame.pack(fill="both", expand=True)
        dm_right = _ck.Frame(dm_split, fg_color=CARD2)
        dm_right.pack(side="left", fill="both", expand=True)
        _conv_title = tk.StringVar(value="← Pilih percakapan")
        _ck.Label(dm_right, textvariable=_conv_title, fg_color=CARD2, text_color=ACC,
                 font=("Segoe UI", 9, "bold"), anchor="w", padx=10,
                 pady=6).pack(fill="x")
        _ck.Frame(dm_right, fg_color="#1c1c2e", height=1).pack(fill="x")
        conv_sb = _ck.Scrollbar(dm_right, orient="vertical")
        conv_sb.pack(side="right", fill="y")
        conv_cv = tk.Canvas(dm_right, bg=CARD2, highlightthickness=0,
                            height=220, yscrollcommand=conv_sb.set)
        conv_cv.pack(side="top", fill="both", expand=True)
        conv_sb.config(command=conv_cv.yview)
        conv_inner = _ck.Frame(conv_cv, fg_color=CARD2)
        _cwid = conv_cv.create_window((0, 0), window=conv_inner, anchor="nw")
        conv_inner.bind("<Configure>",
                        lambda e: conv_cv.configure(
                            scrollregion=conv_cv.bbox("all")))
        conv_cv.bind("<Configure>",
                     lambda e: conv_cv.itemconfig(_cwid, width=e.width))
        _ck.Frame(dm_right, fg_color="#1c1c2e", height=1).pack(fill="x")
        dm_ir = _ck.Frame(dm_right, fg_color=CARD2, padx=8, pady=6)
        dm_ir.pack(fill="x")
        dm_inp = _ck.Text(dm_ir, fg_color="#0D0D18", text_color=FG, insertbackground=FG,
                         relief="flat", font=("Segoe UI", 9),
                         height=2, wrap="word", bd=6)
        dm_inp.pack(side="left", fill="x", expand=True, padx=(0, 6))
        _dm_sel = [None]
        _dm_st = tk.StringVar(value="")
        _ck.Label(dm_right, textvariable=_dm_st, fg_color=CARD2, text_color=MUT,
                 font=("Segoe UI", 7)).pack(anchor="w", padx=8)

        def _render_conv(msgs, target):
            for w in conv_inner.winfo_children():
                w.destroy()
            if not msgs:
                _ck.Label(conv_inner, text="Belum ada pesan.", fg_color=CARD2, text_color=MUT, font=("Segoe UI", 9), pady=20).pack()
                return
            for m in msgs:
                is_me = (m.get("from", "") == self.MASTER_EMAIL)
                ts = m.get("ts", 0)
                try:
                    t_str = _dt.fromtimestamp(ts).strftime("%H:%M")
                except Exception:
                    t_str = ""
                row = _ck.Frame(conv_inner, fg_color=CARD2, pady=2)
                row.pack(fill="x", padx=6)
                bub_bg = "#1E1B4B" if is_me else "#052e16"
                bub = _ck.Frame(row, fg_color=bub_bg, padx=8, pady=5)
                bub.pack(anchor="w" if is_me else "e")
                prefix = "\U0001f451 " if is_me else "↩ "
                _ck.Label(bub, text="{}{}".format(prefix, m.get("message", "")), fg_color=bub_bg, text_color=FG, font=("Segoe UI", 9),
                         wraplength=300, justify="left").pack(anchor="w")
                _ck.Label(bub, text=t_str, fg_color=bub_bg, text_color=MUT,
                         font=("Segoe UI", 7)).pack(anchor="e")
            conv_cv.update_idletasks()
            conv_cv.yview_moveto(1.0)

        def _load_conv(em):
            _dm_sel[0] = em
            _conv_title.set("\U0001f4ac {}".format(em))
            def _bg():
                from modules.master_config import get_dm
                msgs = get_dm(em, _tok())
                if self._root:
                    self._root.after(0,
                                     lambda m=msgs, e=em: _render_conv(m, e))
            _thr.Thread(target=_bg, daemon=True).start()

        def _send_dm():
            to = _dm_sel[0]
            msg = dm_inp.get("1.0", "end").strip()
            if not to or not msg:
                _dm_st.set("Pilih user dan tulis pesan dulu.")
                return
            dm_inp.delete("1.0", "end")
            _dm_st.set("Mengirim…")
            def _bg():
                from modules.master_config import send_dm as sdm, get_dm
                ok = sdm(to, msg, _tok())
                msgs = get_dm(to, _tok()) if ok else None
                def _u():
                    if msgs is not None:
                        _render_conv(msgs, to)
                    _dm_st.set("✓ Terkirim!" if ok else "✗ Gagal.")
                if self._root:
                    self._root.after(0, _u)
            _thr.Thread(target=_bg, daemon=True).start()

        _ck.Button(dm_ir, text="\U0001f4e8 Kirim", fg_color=ACC, text_color="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
                  command=_send_dm).pack(side="right")
        _dm_ts = tk.StringVar(value="Memuat thread…")
        _ck.Label(dm_left, textvariable=_dm_ts, fg_color="#0D0D18", text_color=MUT,
                 font=("Segoe UI", 7), wraplength=180).pack(
            anchor="w", padx=8)

        def _load_threads():
            from modules.master_config import get_all_dm_threads
            threads = get_all_dm_threads(_tok() or "")
            def _render():
                for w in thread_frame.winfo_children():
                    w.destroy()
                if not threads:
                    _ck.Label(thread_frame, text="Belum ada percakapan.", fg_color="#0D0D18", text_color=MUT, font=("Segoe UI", 8),
                             padx=8, pady=8).pack(anchor="w")
                    _dm_ts.set("")
                    return
                _dm_ts.set("{} percakapan".format(len(threads)))
                for t in threads:
                    em   = t["email"]
                    unrd = t["unread"]
                    last = (t["last_message"][:28] + "…"
                            if len(t["last_message"]) > 28
                            else t["last_message"])
                    btn_bg = "#1A1A30" if unrd == 0 else "#2A1A3A"
                    trow = _ck.Frame(thread_frame, fg_color=btn_bg, pady=5,
                                    padx=8, cursor="hand2")
                    trow.pack(fill="x", pady=1)
                    _ck.Label(trow, text=em.split("@")[0], fg_color=btn_bg, text_color=FG if unrd == 0 else "#A78BFA",
                             font=("Segoe UI", 8,
                                   "bold" if unrd else "normal"),
                             anchor="w").pack(anchor="w")
                    if unrd:
                        _ck.Label(trow, text="● {} baru".format(unrd), fg_color=btn_bg, text_color="#E11D48",
                                 font=("Segoe UI", 7)).pack(anchor="w")
                    _ck.Label(trow, text=last or "(kosong)", fg_color=btn_bg, text_color=MUT, font=("Segoe UI", 7),
                             anchor="w").pack(anchor="w")
                    trow.bind("<Button-1>", lambda e, em=em: _load_conv(em))
                    for w in trow.winfo_children():
                        w.bind("<Button-1>", lambda e, em=em: _load_conv(em))
            if self._root:
                self._root.after(0, _render)

        _ck.Button(dm_left, text="\U0001f504", fg_color="#0D0D18", text_color=MUT, font=("Segoe UI", 8),
                  relief="flat", bd=0, padx=6, pady=2, cursor="hand2",
                  command=lambda: _thr.Thread(
                      target=_load_threads, daemon=True).start()
                  ).pack(anchor="e", padx=4)
        _thr.Thread(target=_load_threads, daemon=True).start()

        # ══════════════════════════════════════════════════════════════════════
        # SISTEM
        # ══════════════════════════════════════════════════════════════════════
        _sect(body, "Sistem")

        # ── Firebase Rules ────────────────────────────────────────────────────
        rl = _mk(body, "Firebase Security Rules", "\U0001f512", GRN)
        _rules_st = tk.StringVar(value="Auto-deploy rules saat master login aktif.")
        _ck.Label(rl, textvariable=_rules_st, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8), wraplength=580,
                 justify="left").pack(anchor="w", pady=(0, 6))

        def _deploy_rules():
            _rules_st.set("Mendeploy rules ke Firebase…")
            def _bg():
                from auth.rules_deployer import deploy_rules
                ok, msg = deploy_rules()
                if self._root:
                    self._root.after(0, lambda m=msg: _rules_st.set(m))
            _thr.Thread(target=_bg, daemon=True).start()

        _ck.Button(rl, text="\U0001f512 Deploy Firebase Rules", fg_color="#1A3A1A", text_color=GRN, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
                  command=_deploy_rules).pack(anchor="w")
        _thr.Thread(target=lambda: (
            __import__("time").sleep(1),
            self._root.after(0, _deploy_rules) if self._root else None
        ), daemon=True).start()

        # ── Rekening API URL ──────────────────────────────────────────────────
        rek = _mk(body, "Rekening API URL", "\U0001f517", "#F59E0B")
        _url_st = tk.StringVar(value="Memuat URL dari Firebase…")
        _ck.Label(rek, textvariable=_url_st, fg_color=CARD, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))
        _url_var = tk.StringVar()
        url_row = _ck.Frame(rek, fg_color=CARD)
        url_row.pack(fill="x", pady=(0, 8))
        _ck.Entry(url_row, textvariable=_url_var, fg_color=CARD2, text_color=FG,
                 insertbackground=FG, relief="flat",
                 font=("Segoe UI", 10), bd=6).pack(
            side="left", fill="x", expand=True, padx=(0, 8))

        def _load_url():
            from modules.master_config import get_rekening_url
            from auth.firebase_auth import get_valid_token
            tok = get_valid_token()
            if not tok:
                return
            url = get_rekening_url(tok)
            if self._root:
                self._root.after(0, lambda u=url: (
                    _url_var.set(u),
                    _url_st.set("URL saat ini (dari Firebase):")))

        def _save_url():
            new_url = _url_var.get().strip()
            if not new_url.startswith("http"):
                self._show_alert("Error", "URL harus diawali http/https",
                                 kind="error")
                return
            _url_st.set("Menyimpan…")
            def _bg():
                from modules.master_config import set_rekening_url
                from auth.firebase_auth import get_valid_token
                tok = get_valid_token()
                ok = set_rekening_url(new_url, tok) if tok else False
                msg = ("✓ URL berhasil diupdate!" if ok
                       else "✗ Gagal menyimpan ke Firebase.")
                if self._root:
                    self._root.after(0, lambda m=msg: _url_st.set(m))
            _thr.Thread(target=_bg, daemon=True).start()

        _btn(url_row, "\U0001f4be Simpan", "#F59E0B", text_color="black",
             cmd=_save_url).pack(side="left")
        _thr.Thread(target=_load_url, daemon=True).start()
        _ck.Label(rek,
                 text="URL ini dipakai SEMUA user untuk validasi rekening.\n"
                      "Ganti di sini → langsung berlaku tanpa update app.", fg_color=CARD, text_color=MUT, font=("Segoe UI", 8),
                 justify="left").pack(anchor="w")

        return f

    # ================================================================
    #  URL open
    # ================================================================

    def _open_url(self):
        url = self._url.get().strip()
        if url and self.engine:
            threading.Thread(
                target=self.engine.open_url, args=(url,),
                daemon=True).start()

    # ================================================================
    #  SPY actions
    # ================================================================

    def _toggle_spy(self):
        if not self._spy_active:
            self._spy_active = True
            self._spy_btn.configure(text="DISABLE SPY", fg_color=RED)
            self._spy_status_lbl.configure(
                text="Active - Hover over elements in Chrome", text_color=GRN)
            if self.engine and self.engine.browser:
                try:
                    self.engine.browser.inject_spy_overlay()
                except Exception as e:
                    self.logger.warning("inject_spy_overlay: {}".format(e))
            self._poll_spy()
        else:
            self._spy_active = False
            self._spy_btn.configure(text="ENABLE SPY", fg_color=ACC)
            self._spy_status_lbl.configure(text="Inactive", text_color=MUT)
            if self._spy_poll_id:
                self._root.after_cancel(self._spy_poll_id)
                self._spy_poll_id = None
            if self.engine and self.engine.browser:
                try:
                    self.engine.browser.remove_spy_overlay()
                except Exception:
                    pass
            for var in self._spy_fields.values():
                var.set("-")

    def _poll_spy(self):
        if not self._spy_active:
            return
        try:
            if self.engine and self.engine.browser:
                info = self.engine.browser.get_spy_element()
                if info and info.get("tagName"):
                    self._update_spy_fields(info)
                    self._spy_current_info = info
        except Exception:
            pass
        self._spy_poll_id = self._root.after(500, self._poll_spy)

    def _update_spy_fields(self, info):
        tag = info.get("tagName", "")
        type_map = {
            "button": "Button",  "input": "Input",
            "a": "Link",         "img": "Image",
            "select": "Dropdown","textarea": "Textarea",
            "span": "Text",      "div": "Div",
            "p": "Paragraph",    "h1": "Heading",
            "h2": "Heading",     "h3": "Heading",
        }
        self._spy_fields["type"].set(type_map.get(tag, tag.upper() or "-"))
        self._spy_fields["text"].set(info.get("text", "") or "-")
        self._spy_fields["id"].set(info.get("id", "") or "-")
        self._spy_fields["css_selector"].set(
            info.get("css_selector", info.get("selector", "")) or "-")
        self._spy_fields["xpath"].set(info.get("xpath", "") or "-")
        self._spy_fields["value"].set(info.get("value", "") or "-")
        pos = info.get("position", {})
        self._spy_fields["position"].set(
            "X: {}, Y: {}".format(
                pos.get("x", info.get("x", 0)),
                pos.get("y", info.get("y", 0))))

    def _open_floating_spy(self):
        from ui.spy_window import FloatingSpyWindow
        if self._floating_spy and self._floating_spy.is_alive:
            return
        browser = (self.engine.browser
                   if self.engine and self.engine.browser else None)
        if browser:
            try:
                browser.inject_spy_overlay()
            except Exception:
                pass
        self._floating_spy = FloatingSpyWindow(
            self._root, browser,
            on_capture=self._on_spy_capture)

    def _open_floating_spy_for_macro(self, on_sel_callback):
        """Open spy with USE IN MACRO callback wired to on_sel_callback."""
        from ui.spy_window import FloatingSpyWindow
        if self._floating_spy and self._floating_spy.is_alive:
            # Update the callback on the existing spy window
            self._floating_spy.on_use_in_macro = lambda sel, xp, txt: on_sel_callback(sel, xp, txt)
            return
        browser = (self.engine.browser
                   if self.engine and self.engine.browser else None)

        def _on_macro(sel, xp, txt):
            on_sel_callback(sel, xp, txt)

        self._floating_spy = FloatingSpyWindow(
            self._root, browser,
            on_capture=self._on_spy_capture,
            on_use_in_macro=_on_macro)

    def _on_spy_capture(self, info):
        tag = info.get("tagName", "")
        type_map = {
            "button": "Button", "input": "Input", "a": "Link",
            "img": "Image", "select": "Dropdown", "textarea": "Textarea",
        }
        # Pakai nama dari entry kalau sudah ada (dari floating spy),
        # baru tanya kalau belum ada
        name = info.get("name") or self._ask_input(
            "Simpan Elemen", "Nama untuk elemen ini:")
        if not name:
            return
        # Hindari duplikat nama
        existing = [e.get("name") for e in self._ud.elements]
        if name in existing:
            return
        elem_type = type_map.get(tag, tag.upper() if tag else "Coord")
        self._ud.elements.append({
            "name":     name,
            "type":     elem_type,
            "selector": info.get("css_selector", info.get("selector", "")),
            "xpath":    info.get("xpath", ""),
            "text":     info.get("text", ""),
            "id":       info.get("id", ""),
            "x":        info.get("x", ""),
            "y":        info.get("y", ""),
        })
        self._ud.save()
        self._refresh_spy_elements_tree()
        self._sv.set("Elemen '{}' disimpan.".format(name))

    def _save_spy_element(self):
        info = self._spy_current_info
        if not info or not info.get("tagName"):
            self._show_alert("Spy",
                             "No element selected.\nEnable Spy and hover over an element.",
                             "warning")
            return
        self._on_spy_capture(info)

    def _refresh_spy_elements_tree(self):
        if not self._spy_elements_tree:
            return
        for row in self._spy_elements_tree.get_children():
            self._spy_elements_tree.delete(row)
        for elem in self._ud.elements:
            self._spy_elements_tree.insert("", "end", values=(
                elem.get("name",""),
                elem.get("type",""),
                elem.get("selector",""),
            ))

    def _fetch_spy_element_value(self):
        sel = self._spy_elements_tree.selection()
        if not sel:
            return
        idx = self._spy_elements_tree.index(sel[0])
        if idx >= len(self._ud.elements):
            return
        selector = self._ud.elements[idx].get("selector","")
        if not selector or not self.engine:
            return
        def _fetch():
            try:
                text = self.engine.browser.get_text(selector)
                self._root.after(0, lambda t=text: self._show_alert(
                    "Element Value", "Current value:\n{}".format(t)))
            except Exception as e:
                from utils.error_handler import friendly_message
                msg = friendly_message(e)
                self._root.after(0, lambda m=msg, ex=e: self._toast_error(m, ex))
        threading.Thread(target=_fetch, daemon=True).start()

    def _scrape_spy_to_sheet(self):
        sel = self._spy_elements_tree.selection()
        if not sel:
            self._show_alert("Scrape ke Sheet", "Pilih elemen terlebih dahulu.", "warning")
            return
        idx = self._spy_elements_tree.index(sel[0])
        if idx >= len(self._ud.elements):
            return
        element  = self._ud.elements[idx]
        selector = element.get("selector", "")
        if not selector or not self.engine:
            self._show_alert("Scrape ke Sheet",
                             "Elemen tidak memiliki selector atau browser belum aktif.",
                             "warning")
            return

        # -- dialog -------------------------------------------------------
        sheets = [s.get("name", "") for s in self._ud.sheets if s.get("name")]
        if not sheets:
            self._show_alert("Scrape ke Sheet",
                             "Belum ada sheet terhubung. Tambahkan di halaman Sheet.",
                             "warning")
            return

        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Scrape ke Sheet")
        dlg.configure(fg_color=BG)
        dlg.resizable(False, False)
        dlg.update()
        dlg.deiconify()
        dlg.grab_set()
        dlg.geometry("340x180+{}+{}".format(
            self._root.winfo_rootx() + 80,
            self._root.winfo_rooty() + 80))

        _lbl(dlg, "Sheet tujuan:", fg_color=BG, font=("Segoe UI", 9)).pack(
            anchor="w", padx=16, pady=(14, 2))
        sheet_var = tk.StringVar(value=sheets[0])
        _ck.Combobox(dlg, textvariable=sheet_var, values=sheets,
                     state="readonly", font=("Segoe UI", 10)).pack(
            fill="x", padx=16)

        _lbl(dlg, "Nama kolom / header (kosongkan = append nilai saja):", fg_color=BG, font=("Segoe UI", 9), text_color=MUT).pack(
            anchor="w", padx=16, pady=(10, 2))
        col_var = tk.StringVar()
        _ck.Entry(dlg, textvariable=col_var,
                  font=("Segoe UI", 10)).pack(fill="x", padx=16)

        def _do_scrape():
            sheet_name = sheet_var.get().strip()
            col_label  = col_var.get().strip()
            dlg.destroy()

            def _worker():
                try:
                    text = self.engine.browser.get_text(selector)
                    vals = [col_label, text] if col_label else [text]
                    from modules.sheets import connector as _sc
                    ok, err = _sc.append_row(self._ud.sheets, sheet_name, vals)
                    if err:
                        self._root.after(0, lambda e=err: self._toast_error(e))
                    else:
                        self._root.after(0, lambda: self._toast_success(
                            "Data berhasil discrape ke Sheet '{}'.".format(sheet_name)))
                except Exception as e:
                    from utils.error_handler import friendly_message
                    msg = friendly_message(e)
                    self._root.after(0, lambda m=msg, ex=e: self._toast_error(m, ex))

            threading.Thread(target=_worker, daemon=True).start()

        btn_row_dlg = _ck.Frame(dlg, fg_color=BG)
        btn_row_dlg.pack(anchor="e", padx=16, pady=(12, 0))
        _ck.Button(btn_row_dlg, text="Scrape",
                   command=_do_scrape).pack(side="left", padx=(0, 6))
        _ck.Button(btn_row_dlg, text="Batal",
                   command=dlg.destroy).pack(side="left")

    def _copy_spy_selector(self):
        sel = self._spy_elements_tree.selection()
        if not sel:
            return
        idx = self._spy_elements_tree.index(sel[0])
        if idx >= len(self._ud.elements):
            return
        selector = self._ud.elements[idx].get("selector","")
        self._root.clipboard_clear()
        self._root.clipboard_append(selector)
        self._sv.set("Selector copied: {}".format(selector))

    def _delete_spy_element(self):
        sel = self._spy_elements_tree.selection()
        if not sel:
            return
        idx = self._spy_elements_tree.index(sel[0])
        if idx >= len(self._ud.elements):
            return
        name = self._ud.elements[idx].get("name","")
        if self._confirm_dialog(
                "Hapus Elemen?",
                "Hapus elemen '{}'?".format(name),
                confirm_text="Ya, Hapus", accent=RED):
            del self._ud.elements[idx]
            self._ud.save()
            self._refresh_spy_elements_tree()

    # ================================================================
    #  Recording
    # ================================================================

    # -- Simple Record --------------------------------------------------

    def _start_simple_rec(self):
        """Open the recorder floating window. Recording only starts inside."""
        if self._rec_toolbar_win:
            try:
                if self._rec_toolbar_win.winfo_exists():
                    self._rec_toolbar_win.lift()
                    return
            except Exception:
                pass
        self._show_rec_toolbar()

    def _do_countdown(self, count, callback):
        """Show a full-screen-style countdown overlay, then call callback."""
        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("")
        dlg.geometry("200x120")
        dlg.configure(fg_color=BG)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        dlg.geometry("200x120+{}+{}".format(sw // 2 - 100, sh // 2 - 60))

        lbl = _ck.Label(dlg, text="Recording starts in", fg_color=BG, text_color=MUT,
                       font=("Segoe UI", 11))
        lbl.pack(pady=(18, 4))
        num = _ck.Label(dlg, text=str(count), fg_color=BG, text_color=ACC,
                       font=("Segoe UI", 40, "bold"))
        num.pack()

        remaining = [count]

        def _tick():
            remaining[0] -= 1
            if remaining[0] > 0:
                num.configure(text=str(remaining[0]))
                dlg.after(1000, _tick)
            else:
                dlg.destroy()
                callback()

        dlg.update()
        dlg.deiconify()
        dlg.after(1000, _tick)

    def _show_rec_toolbar(self):
        """Floating recorder control panel - recording starts/stops from here."""
        import time as _time

        win = ctk.CTkToplevel(self._root)
        win.withdraw()
        win.title("Synthex Recorder")
        win.configure(fg_color="#0D0D14")
        win.resizable(False, False)
        win.attributes("-topmost", True)

        W, H = 292, 120
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        # Default position: top-right corner
        win.geometry("{}x{}+{}+{}".format(W, H, sw - W - 12, 12))
        self._rec_toolbar_win  = win
        self._rec_toggle_fn    = None   # diisi setelah fungsi didefinisikan
        self._rec_pause_fn     = None   # diisi setelah fungsi didefinisikan
        self._rec_unlimited    = False  # mode unlimited repeat

        self._rec_paused   = False
        self._rec_pause_var = tk.StringVar(value="JEDA")

        # ── Close / minimize defined first (used by header buttons) ─────────
        _close_ref = [None]   # forward reference holder

        def _close_recorder():
            # Tutup step editor dulu kalau masih terbuka
            if self._simple_step_editor_win:
                try:
                    self._simple_step_editor_win.grab_release()
                    self._simple_step_editor_win.destroy()
                except Exception:
                    pass
                self._simple_step_editor_win = None
            if self._rec:
                self._stop_simple_rec()
            if self._rec_timer_id:
                try:
                    self._root.after_cancel(self._rec_timer_id)
                except Exception:
                    pass
            self._rec_timer_id    = None
            self._rec_toolbar_win = None
            try:
                win.destroy()
            except Exception:
                pass

        _close_ref[0] = _close_recorder

        def _do_minimize():
            win.withdraw()

        # ── Drag support ─────────────────────────────────────────────────────
        _drag = {"x": 0, "y": 0}
        def _drag_start(e):
            _drag["x"] = e.x_root - win.winfo_x()
            _drag["y"] = e.y_root - win.winfo_y()
        def _drag_move(e):
            win.geometry("+{}+{}".format(
                e.x_root - _drag["x"], e.y_root - _drag["y"]))

        # ── Header (compact 22px) ────────────────────────────────────────────
        hdr = _ck.Frame(win, fg_color=ACC, height=22, cursor="fleur")
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr.bind("<ButtonPress-1>", _drag_start)
        hdr.bind("<B1-Motion>",     _drag_move)

        _ck.Label(hdr, text="  SYNTHEX REC", fg_color=ACC, text_color="#FFFFFF",
                 font=("Segoe UI", 8, "bold")).pack(side="left", pady=3)
        _ck.Button(hdr, text="x", fg_color=ACC, text_color="#FFFFFF",
                  font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                  padx=7, cursor="hand2",
                  activebackground=RED, activeforeground="#FFFFFF",
                  command=lambda: _close_ref[0]()).pack(side="right", fill="y")
        _ck.Button(hdr, text="—", fg_color=ACC, text_color="#FFFFFF",
                  font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                  padx=7, cursor="hand2",
                  activebackground="#8870FF", activeforeground="#FFFFFF",
                  command=_do_minimize).pack(side="right", fill="y")

        # ── Status bar (1 compact line) ──────────────────────────────────────
        dot_var   = tk.StringVar(value="●")
        state_var = tk.StringVar(value="SIAP")
        timer_var = tk.StringVar(value="00:00")
        steps_var = tk.StringVar(value="0 steps")

        st = _ck.Frame(win, fg_color="#0D0D14")
        st.pack(fill="x", padx=8, pady=(4, 2))

        dot_lbl = _ck.Label(st, textvariable=dot_var, fg_color="#0D0D14", text_color=MUT,
                           font=("Segoe UI", 10))
        dot_lbl.pack(side="left")
        _ck.Label(st, textvariable=state_var, fg_color="#0D0D14", text_color=FG,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(4, 0))
        _ck.Label(st, textvariable=timer_var, fg_color="#0D0D14", text_color=MUT,
                 font=("Consolas", 8)).pack(side="right", padx=(0, 2))
        _ck.Label(st, textvariable=steps_var, fg_color="#0D0D14", text_color=MUT,
                 font=("Segoe UI", 8)).pack(side="right", padx=(0, 6))

        _ck.Frame(win, fg_color="#2A2A40", height=1).pack(fill="x", pady=(2, 0))

        # No live preview — keep empty list for compatibility
        self._rec_preview_labels = []

        # ── Helper format action ──────────────────────────────────────────────
        def _fmt_action(a):
            t = a.get("type", "")
            if t == "click":
                btn = a.get("button", "left")
                return "[klik{}] ({},{})".format(
                    "-kanan" if btn == "right" else "", a.get("x","?"), a.get("y","?"))
            if t == "type":
                return "[ketik] \"{}\"".format(str(a.get("text",""))[:22])
            if t in ("key", "key_press"):
                return "[tombol] {}".format(str(a.get("key",""))[:18])
            if t == "scroll":
                arah = "atas" if a.get("amount", 0) > 0 else "bawah"
                return "[scroll-{}] ({},{})".format(arah, a.get("x","?"), a.get("y","?"))
            if t == "move":
                return "[gerak] ({},{})".format(a.get("x","?"), a.get("y","?"))
            return "[{}]".format(t)

        # ── Logic functions ───────────────────────────────────────────────────
        def _update_state_idle():
            dot_var.set("●")
            dot_lbl.configure(text_color=MUT)
            state_var.set("SIAP")
            timer_var.set("00:00")
            steps_var.set("0 langkah")
            btn_rec.configure(text="⏺", fg_color=RED, text_color="#FFFFFF", state="normal")
            btn_pause.configure(text="⏸", fg_color=CARD2, text_color=MUT, state="disabled")
            for nl, tl in self._rec_preview_labels:
                nl.configure(text="")
                tl.configure(text="")

        def _do_actual_record():
            self.logger.info("REC: _do_actual_record START")
            try:
                from modules.macro.simple_recorder import SimpleRecorder
                self.logger.info("REC: creating SimpleRecorder")
                self._simple_recorder = SimpleRecorder()
                self.logger.info("REC: calling start_recording")
                self._simple_recorder.start_recording()
                self.logger.info("REC: start_recording OK, setting rec=True")
                self._rec            = True
                self._rec_start_time = _time.time()
                self._rec_paused     = False
                self._sv.set("Merekam... lakukan aksi yang ingin diulang, lalu tekan CTRL+3.")
                dot_var.set("●")
                dot_lbl.configure(text_color=RED)
                state_var.set("MEREKAM")
                btn_rec.configure(text="⏹", fg_color="#2A1A1A", text_color=RED, state="normal")
                btn_pause.configure(text="⏸", fg_color=YEL, text_color=BG, state="normal")
                self.logger.info("REC: UI updated, calling _tick")
                _tick()
                self.logger.info("REC: _do_actual_record COMPLETE")
            except Exception as _e:
                self.logger.error("Recording start error: %s", _e, exc_info=True)
                _update_state_idle()

        def _start_recording():
            _do_actual_record()   # langsung mulai tanpa countdown (OP Auto Clicker style)

        def _stop_recording():
            if self._rec_timer_id:
                try: self._root.after_cancel(self._rec_timer_id)
                except Exception: pass
            self._stop_simple_rec()
            _update_state_idle()

        def _toggle_recording():
            if not self._rec:
                _start_recording()
            else:
                _stop_recording()

        def _toggle_pause():
            if not self._rec:
                return
            self._rec_paused = not self._rec_paused
            if self._rec_paused:
                dot_var.set("⏸")
                dot_lbl.configure(text_color=YEL)
                state_var.set("DIJEDA")
                btn_pause.configure(text="▶", fg_color=GRN, text_color=BG)
                if self._simple_recorder:
                    self._simple_recorder.pause_recording()
            else:
                dot_var.set("●")
                dot_lbl.configure(text_color=RED)
                state_var.set("MEREKAM")
                btn_pause.configure(text="⏸", fg_color=YEL, text_color=BG)
                if self._simple_recorder:
                    self._simple_recorder.resume_recording()

        def _toggle_unlimited():
            self._rec_unlimited = not self._rec_unlimited
            if self._rec_unlimited:
                btn_unlim.configure(fg_color=ACC, text_color="#FFFFFF")
            else:
                btn_unlim.configure(fg_color=CARD2, text_color=MUT)

        def _play_last():
            if self._rec:
                return
            if not self._recordings_tree:
                return
            sel = self._recordings_tree.selection()
            if not sel:
                return
            idx = self._recordings_tree.index(sel[0])
            if idx >= len(self._ud.recordings):
                return
            # Move to bottom-right corner before playback so it doesn't block
            try:
                win.geometry("+{}+{}".format(sw - W - 12, sh - H - 50))
            except Exception:
                pass
            import copy as _copy
            rec = _copy.deepcopy(self._ud.recordings[idx])
            rec["repeat"] = 999999 if self._rec_unlimited else 1
            if rec.get("rec_type", "smart") == "simple":
                self._play_simple_recording(rec, idx)
            else:
                self._play_selected_recording()

        # Store references for hotkey access — set AFTER all UI is built below
        # (set at bottom of this function)

        # ── 4 equal buttons in single horizontal row ──────────────────────────
        ICON_F = ("Segoe UI Emoji", 15)

        btn_row = _ck.Frame(win, fg_color="#0D0D14", height=52)
        btn_row.pack(fill="x", padx=8, pady=(6, 8))
        btn_row.pack_propagate(False)

        btn_rec = _ck.Button(btn_row, text="⏺", fg_color=RED, text_color="#FFFFFF", font=ICON_F,
                            relief="flat", bd=0, cursor="hand2",
                            activebackground="#CC3050",
                            command=_toggle_recording)
        btn_rec.pack(side="left", fill="both", expand=True, padx=(0, 3))

        btn_pause = _ck.Button(btn_row, text="⏸", fg_color=CARD2, text_color=MUT, font=ICON_F,
                              relief="flat", bd=0, cursor="hand2",
                              state="disabled", activebackground=CARD,
                              command=_toggle_pause)
        btn_pause.pack(side="left", fill="both", expand=True, padx=(0, 3))

        btn_play = _ck.Button(btn_row, text="▶", fg_color="#1A3A2A", text_color=GRN, font=ICON_F,
                             relief="flat", bd=0, cursor="hand2",
                             activebackground="#254D38",
                             command=_play_last)
        btn_play.pack(side="left", fill="both", expand=True, padx=(0, 3))

        btn_unlim = _ck.Button(btn_row, text="∞", fg_color=CARD2, text_color=MUT, font=ICON_F,
                              relief="flat", bd=0, cursor="hand2",
                              activebackground=CARD,
                              command=_toggle_unlimited)
        btn_unlim.pack(side="left", fill="both", expand=True)

        # Set hotkey references AFTER all widgets are created
        self._rec_toggle_fn = _toggle_recording
        self._rec_pause_fn  = _toggle_pause

        # ── Tick ──────────────────────────────────────────────────────────────
        def _tick():
            if not win.winfo_exists():
                return
            if self._rec and not self._rec_paused and self._simple_recorder:
                actions = self._simple_recorder.get_actions()
                n       = len(actions)
                elapsed = _time.time() - self._rec_start_time
                timer_var.set(time.strftime("%M:%S", time.gmtime(elapsed)))
                steps_var.set("{} steps".format(n))
            if self._rec:
                self._rec_timer_id = win.after(400, _tick)

        win.protocol("WM_DELETE_WINDOW", lambda: _close_ref[0]())
        _update_state_idle()
        win.update()
        win.deiconify()

    def _toggle_rec_pause(self):
        # Legacy – pause logic now lives inside _show_rec_toolbar closure.
        self._rec_paused = not self._rec_paused

    def _stop_simple_rec(self):
        """Stop simple recording; toolbar window manages its own lifecycle."""
        self._rec = False
        # Cancel the tick timer if running
        if self._rec_timer_id:
            try:
                self._root.after_cancel(self._rec_timer_id)
            except Exception:
                pass
            self._rec_timer_id = None

        actions = []
        if self._simple_recorder:
            actions = self._simple_recorder.stop_recording()
        self._sv.set("Rekaman dihentikan. {} aksi terekam.".format(len(actions)))

        if actions:
            # Minimize toolbar before opening step editor
            if self._rec_toolbar_win:
                try: self._rec_toolbar_win.withdraw()
                except Exception: pass
            self._show_simple_step_editor(actions)
        else:
            from tkinter import messagebox as _mb
            _mb.showinfo("Simple Record", "Tidak ada aksi yang terekam.",
                         parent=self._root)

    def _show_simple_step_editor(self, actions, edit_idx=None):
        """Macro Step Editor — full-featured redesign with undo/redo, drag-reorder,
        multi-select, copy/paste, inline editing, filter, and bulk delay."""
        import copy
        import uuid as _uuid

        if not actions and edit_idx is None:
            self._show_alert("Rekaman Kosong",
                             "Tidak ada langkah yang terekam.\n"
                             "Coba rekam ulang — pastikan melakukan klik atau ketikan.")
            return

        # Existing recording metadata (if editing)
        existing = (self._ud.recordings[edit_idx]
                    if edit_idx is not None and 0 <= edit_idx < len(self._ud.recordings)
                    else None)

        # ------------------------------------------------------------------ #
        #  Window setup                                                        #
        # ------------------------------------------------------------------ #
        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Macro Step Editor")
        dlg.geometry("980x700")
        dlg.configure(fg_color=BG)
        dlg.resizable(True, True)
        dlg.update()
        dlg.deiconify()
        dlg.grab_set()
        self._simple_step_editor_win = dlg

        def _on_editor_close():
            self._simple_step_editor_win = None
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()
            # Restore recorder toolbar after step editor closes
            if self._rec_toolbar_win:
                try:
                    self._rec_toolbar_win.deiconify()
                    self._rec_toolbar_win.lift()
                except Exception:
                    pass

        dlg.protocol("WM_DELETE_WINDOW", _on_editor_close)

        # ------------------------------------------------------------------ #
        #  State                                                               #
        # ------------------------------------------------------------------ #
        step_data   = list(actions)           # list of dicts (mutable)
        _history    = [copy.deepcopy(step_data)]
        _redo_stack = []
        _clipboard  = []
        _filter_map = []                      # visible-index → original-index
        _filter_var = tk.StringVar(value="Semua")

        def _push_undo():
            _history.append(copy.deepcopy(step_data))
            if len(_history) > 50:
                _history.pop(0)
            _redo_stack.clear()

        def _undo():
            if len(_history) > 1:
                _redo_stack.append(_history.pop())
                step_data.clear()
                step_data.extend(copy.deepcopy(_history[-1]))
                _refresh_tree()

        def _redo():
            if _redo_stack:
                snap = _redo_stack.pop()
                _history.append(snap)
                step_data.clear()
                step_data.extend(copy.deepcopy(snap))
                _refresh_tree()

        # ------------------------------------------------------------------ #
        #  Top bar: Name / Description / Folder                               #
        # ------------------------------------------------------------------ #
        top_bar = _ck.Frame(dlg, fg_color=CARD, padx=12, pady=8)
        top_bar.pack(fill="x", padx=0, pady=0)

        # Single compact row
        _lbl(top_bar, "Nama:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        name_var = tk.StringVar(
            value=existing.get("name", "") if existing else "")
        _ck.Entry(top_bar, textvariable=name_var, fg_color=BG, text_color=FG,
                 insertbackground=FG, font=("Segoe UI", 10),
                 relief="flat", bd=0, width=22).pack(
            side="left", padx=(0, 14), ipady=4)

        _lbl(top_bar, "Deskripsi:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        desc_var = tk.StringVar(
            value=existing.get("description", "") if existing else "")
        _ck.Entry(top_bar, textvariable=desc_var, fg_color=BG, text_color=FG,
                 insertbackground=FG, font=("Segoe UI", 10),
                 relief="flat", bd=0, width=28).pack(
            side="left", padx=(0, 14), ipady=4)

        _lbl(top_bar, "Folder:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        folders = sorted(
            {r.get("folder", "General") for r in self._ud.recordings}
            | {"General", "Work", "Personal"})
        folder_var = tk.StringVar(
            value=existing.get("folder", "General") if existing else "General")
        _ck.Combobox(top_bar, textvariable=folder_var, values=folders,
                     width=14).pack(side="left")

        # Filter combobox on the right side of top bar
        _lbl(top_bar, "  Filter:", text_color=MUT, fg_color=CARD,
             font=("Segoe UI", 9)).pack(side="left", padx=(18, 4))
        filter_cb = _ck.Combobox(top_bar, textvariable=_filter_var,
                                 values=["Semua", "click", "type", "key", "scroll"],
                                 state="readonly", width=8)
        filter_cb.pack(side="left")

        # ------------------------------------------------------------------ #
        #  Toolbar row                                                         #
        # ------------------------------------------------------------------ #
        toolbar = _ck.Frame(dlg, fg_color=SIDE, padx=8, pady=5)
        toolbar.pack(fill="x")

        def _tb_btn(parent, text, cmd, fg_col=FG, width=None):
            kw = {"width": width} if width else {}
            b = _ck.Button(parent, text=text, command=cmd, fg_color=CARD, text_color=fg_col, relief="flat", bd=0,
                          font=("Segoe UI", 9), padx=8, pady=3,
                          activebackground=ACC, activeforeground=BG,
                          cursor="hand2", **kw)
            b.pack(side="left", padx=2)
            return b

        def _tb_sep():
            _ck.Label(toolbar, text="|", fg_color=SIDE, text_color=MUT,
                     font=("Segoe UI", 10)).pack(side="left", padx=4)

        # Add button with dropdown menu
        add_menu = tk.Menu(dlg, tearoff=0, bg=CARD, fg=FG,
                           activebackground=ACC, activeforeground=BG,
                           relief="flat", bd=0)

        def _add_step(stype):
            _push_undo()
            defaults = {
                "click":  {"type": "click",  "x": 0, "y": 0,
                           "button": "left", "delay": 0.5},
                "type":   {"type": "type",   "text": "",      "delay": 0.3},
                "key":    {"type": "key",    "key": "enter",  "delay": 0.3},
                "scroll": {"type": "scroll", "x": 0, "y": 0,
                           "amount": 3,     "delay": 0.3},
            }
            new_step = copy.deepcopy(defaults.get(stype, {"type": stype, "delay": 0.3}))
            sel = st.selection()
            if sel:
                vis_idx = st.index(sel[-1])
                orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
                insert_at = orig_idx + 1
            else:
                insert_at = len(step_data)
            step_data.insert(insert_at, new_step)
            _refresh_tree(keep_sel=insert_at)

        for _t in ["click", "type", "key", "scroll"]:
            add_menu.add_command(
                label=_t.capitalize(),
                command=lambda t=_t: _add_step(t))

        add_btn = _ck.Button(toolbar, text="+ Tambah", fg_color=ACC, text_color=BG, relief="flat", bd=0,
                            font=("Segoe UI", 9, "bold"), padx=10, pady=3,
                            activebackground=PRP, activeforeground=BG,
                            cursor="hand2")
        add_btn.pack(side="left", padx=2)

        def _show_add_menu(e=None):
            add_btn.update_idletasks()
            x = add_btn.winfo_rootx()
            y = add_btn.winfo_rooty() + add_btn.winfo_height()
            add_menu.post(x, y)

        add_btn.configure(command=_show_add_menu)

        def _duplicate_step():
            sel = st.selection()
            if not sel:
                return
            _push_undo()
            vis_idx = st.index(sel[-1])
            orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
            dup = copy.deepcopy(step_data[orig_idx])
            step_data.insert(orig_idx + 1, dup)
            _refresh_tree(keep_sel=orig_idx + 1)

        def _delete_step():
            sel = st.selection()
            if not sel:
                return
            _push_undo()
            # Collect original indices (multi-select), delete highest first
            orig_indices = sorted(
                {(_filter_map[st.index(item)] if _filter_map else st.index(item))
                 for item in sel},
                reverse=True)
            for oi in orig_indices:
                if 0 <= oi < len(step_data):
                    del step_data[oi]
            new_sel = max(0, min(orig_indices[-1], len(step_data) - 1)) \
                if step_data else None
            _refresh_tree(keep_sel=new_sel)

        def _move_up():
            sel = st.selection()
            if not sel:
                return
            vis_idx = st.index(sel[0])
            orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
            if orig_idx > 0:
                _push_undo()
                step_data[orig_idx - 1], step_data[orig_idx] = \
                    step_data[orig_idx], step_data[orig_idx - 1]
                _refresh_tree(keep_sel=orig_idx - 1)

        def _move_down():
            sel = st.selection()
            if not sel:
                return
            vis_idx = st.index(sel[0])
            orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
            if orig_idx < len(step_data) - 1:
                _push_undo()
                step_data[orig_idx + 1], step_data[orig_idx] = \
                    step_data[orig_idx], step_data[orig_idx + 1]
                _refresh_tree(keep_sel=orig_idx + 1)

        def _copy_step():
            sel = st.selection()
            if not sel:
                return
            _clipboard.clear()
            for item in sel:
                vis_idx = st.index(item)
                orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
                if 0 <= orig_idx < len(step_data):
                    _clipboard.append(copy.deepcopy(step_data[orig_idx]))

        def _paste_step():
            if not _clipboard:
                return
            _push_undo()
            sel = st.selection()
            if sel:
                vis_idx = st.index(sel[-1])
                orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
                insert_at = orig_idx + 1
            else:
                insert_at = len(step_data)
            for i, s in enumerate(_clipboard):
                step_data.insert(insert_at + i, copy.deepcopy(s))
            _refresh_tree(keep_sel=insert_at + len(_clipboard) - 1)

        _tb_btn(toolbar, "Duplikat", _duplicate_step)
        _tb_btn(toolbar, "Hapus",    _delete_step,   fg_col=RED)
        _tb_btn(toolbar, "  Up",     _move_up)
        _tb_btn(toolbar, "  Down",   _move_down)

        _tb_sep()

        _tb_btn(toolbar, "Undo", _undo)
        _tb_btn(toolbar, "Redo", _redo)

        _tb_sep()

        # Bulk delay
        _lbl(toolbar, "Bulk Delay:", text_color=MUT, fg_color=SIDE,
             font=("Segoe UI", 9)).pack(side="left", padx=(4, 2))
        bulk_delay_var = tk.IntVar(value=500)
        tk.Spinbox(toolbar, from_=0, to=30000, increment=50, width=6,
                   textvariable=bulk_delay_var, bg=CARD, fg=FG, insertbackground=FG,
                   relief="flat", font=("Segoe UI", 9)).pack(
            side="left", padx=(0, 4), ipady=2)

        def _apply_bulk_delay():
            sel = st.selection()
            if not sel:
                return
            _push_undo()
            try:
                ms = int(bulk_delay_var.get())
            except (ValueError, tk.TclError):
                ms = 0
            d = round(ms / 1000.0, 3)
            for item in sel:
                vis_idx = st.index(item)
                orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
                if 0 <= orig_idx < len(step_data):
                    step_data[orig_idx]["delay"] = d
            first_vis = st.index(sel[0])
            first_orig = _filter_map[first_vis] if _filter_map else first_vis
            _refresh_tree(keep_sel=first_orig)

        _tb_btn(toolbar, "Terapkan", _apply_bulk_delay, fg_col=YEL)

        _tb_sep()

        # Right-aligned counters
        step_count_lbl = _ck.Label(toolbar, text="0 langkah", fg_color=SIDE, text_color=MUT, font=("Segoe UI", 9))
        step_count_lbl.pack(side="right", padx=(4, 8))
        total_dur_lbl = _ck.Label(toolbar, text="Total: 0.0s", fg_color=SIDE, text_color=MUT, font=("Segoe UI", 9))
        total_dur_lbl.pack(side="right", padx=(4, 4))

        # ------------------------------------------------------------------ #
        #  Main area: treeview (65%) + right edit panel (35%)                 #
        # ------------------------------------------------------------------ #
        main_area = _ck.Frame(dlg, fg_color=BG)
        main_area.pack(fill="both", expand=True, padx=0, pady=0)

        # --- LEFT: Treeview ------------------------------------------------ #
        left_frame = _ck.Frame(main_area, fg_color=CARD)
        left_frame.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)

        st = ttk.Treeview(
            left_frame,
            columns=("no", "type", "x", "y", "delay", "bar"),
            show="headings",
            selectmode="extended")

        st.heading("no",    text="#")
        st.heading("type",  text="Type")
        st.heading("x",     text="X")
        st.heading("y",     text="Y")
        st.heading("delay", text="Delay(ms)")
        st.heading("bar",   text="░")

        st.column("no",    width=34,  anchor="center", stretch=False)
        st.column("type",  width=110, anchor="w",      stretch=False)
        st.column("x",     width=60,  anchor="center", stretch=False)
        st.column("y",     width=60,  anchor="center", stretch=False)
        st.column("delay", width=80,  anchor="center", stretch=False)
        st.column("bar",   width=100, anchor="w",      stretch=True)

        # Type color tags
        st.tag_configure("click",  foreground="#FF7080")
        st.tag_configure("type",   foreground="#70C870")
        st.tag_configure("key",    foreground="#7090FF")
        st.tag_configure("scroll", foreground="#F0C060")

        vsb = _ck.Scrollbar(left_frame, orient="vertical", command=st.yview)
        st.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        st.pack(side="left", fill="both", expand=True)

        # --- RIGHT: Edit panel --------------------------------------------- #
        right_frame = _ck.Frame(main_area, fg_color=CARD, width=310)
        right_frame.pack(side="right", fill="y", padx=(4, 8), pady=8)
        right_frame.pack_propagate(False)

        edit_header = _ck.Label(right_frame, text="Pilih langkah untuk diedit", fg_color=CARD, text_color=MUT,
                               font=("Segoe UI", 10, "bold"), anchor="w")
        edit_header.pack(fill="x", padx=10, pady=(10, 6))

        edit_fields = _ck.Frame(right_frame, fg_color=CARD)
        edit_fields.pack(fill="both", expand=True, padx=8)

        # Shared edit-panel variables
        _ep_type   = tk.StringVar(value="click")
        _ep_delay  = tk.IntVar(value=500)
        _ep_x      = tk.IntVar(value=0)
        _ep_y      = tk.IntVar(value=0)
        _ep_button = tk.StringVar(value="left")
        _ep_text   = tk.StringVar(value="")
        _ep_amount = tk.IntVar(value=3)
        _ep_key    = tk.StringVar(value="")

        _edit_widgets = {}   # name → widget reference for later use

        def _ep_lbl(parent, text):
            return _ck.Label(parent, text=text, fg_color=CARD, text_color=MUT,
                            font=("Segoe UI", 9), anchor="w")

        def _build_edit_panel(atype="click"):
            for w in edit_fields.winfo_children():
                w.destroy()
            _edit_widgets.clear()

            # Type row
            r0 = _ck.Frame(edit_fields, fg_color=CARD)
            r0.pack(fill="x", pady=(4, 2))
            _ep_lbl(r0, "Tipe:").pack(anchor="w")
            type_cb = _ck.Combobox(r0, textvariable=_ep_type,
                                   values=["click", "type", "scroll", "key"],
                                   state="readonly", width=14)
            type_cb.pack(fill="x", pady=(2, 0))
            type_cb.bind("<<ComboboxSelected>>",
                         lambda e: _build_edit_panel(_ep_type.get()))
            _edit_widgets["type_cb"] = type_cb

            # Delay row
            r1 = _ck.Frame(edit_fields, fg_color=CARD)
            r1.pack(fill="x", pady=(6, 2))
            _ep_lbl(r1, "Delay (ms):").pack(anchor="w")
            delay_sp = tk.Spinbox(r1, from_=0, to=30000, increment=50,
                                  textvariable=_ep_delay, width=10, bg=BG, fg=FG, insertbackground=FG,
                                  relief="flat", font=("Segoe UI", 9))
            delay_sp.pack(fill="x", pady=(2, 0), ipady=3)
            _edit_widgets["delay_sp"] = delay_sp

            # Type-specific fields
            if atype == "click":
                for lbl_t, var, name in [("X:", _ep_x, "x_sp"),
                                          ("Y:", _ep_y, "y_sp")]:
                    rf = _ck.Frame(edit_fields, fg_color=CARD)
                    rf.pack(fill="x", pady=(4, 2))
                    _ep_lbl(rf, lbl_t).pack(anchor="w")
                    sp = tk.Spinbox(rf, from_=-9999, to=9999, textvariable=var,
                                    width=10, bg=BG, fg=FG,
                                    insertbackground=FG, relief="flat",
                                    font=("Segoe UI", 9))
                    sp.pack(fill="x", pady=(2, 0), ipady=3)
                    _edit_widgets[name] = sp
                rb = _ck.Frame(edit_fields, fg_color=CARD)
                rb.pack(fill="x", pady=(4, 2))
                _ep_lbl(rb, "Button:").pack(anchor="w")
                btn_cb = _ck.Combobox(rb, textvariable=_ep_button,
                                      values=["left", "right", "middle"],
                                      state="readonly", width=10)
                btn_cb.pack(fill="x", pady=(2, 0))
                _edit_widgets["btn_cb"] = btn_cb

            elif atype == "type":
                rt = _ck.Frame(edit_fields, fg_color=CARD)
                rt.pack(fill="x", pady=(4, 2))
                _ep_lbl(rt, "Teks:").pack(anchor="w")
                txt_e = _ck.Entry(rt, textvariable=_ep_text, fg_color=BG, text_color=FG, insertbackground=FG,
                                 font=("Segoe UI", 9), relief="flat", bd=0)
                txt_e.pack(fill="x", pady=(2, 0), ipady=4)
                _edit_widgets["txt_e"] = txt_e

            elif atype == "scroll":
                for lbl_t, var, name in [("X:", _ep_x, "sx_sp"),
                                          ("Y:", _ep_y, "sy_sp")]:
                    rf = _ck.Frame(edit_fields, fg_color=CARD)
                    rf.pack(fill="x", pady=(4, 2))
                    _ep_lbl(rf, lbl_t).pack(anchor="w")
                    sp = tk.Spinbox(rf, from_=-9999, to=9999, textvariable=var,
                                    width=10, bg=BG, fg=FG,
                                    insertbackground=FG, relief="flat",
                                    font=("Segoe UI", 9))
                    sp.pack(fill="x", pady=(2, 0), ipady=3)
                    _edit_widgets[name] = sp
                ra = _ck.Frame(edit_fields, fg_color=CARD)
                ra.pack(fill="x", pady=(4, 2))
                _ep_lbl(ra, "Jumlah:").pack(anchor="w")
                amt_sp = tk.Spinbox(ra, from_=-100, to=100, textvariable=_ep_amount,
                                    width=10, bg=BG, fg=FG,
                                    insertbackground=FG, relief="flat",
                                    font=("Segoe UI", 9))
                amt_sp.pack(fill="x", pady=(2, 0), ipady=3)
                _edit_widgets["amt_sp"] = amt_sp

            elif atype == "key":
                rk = _ck.Frame(edit_fields, fg_color=CARD)
                rk.pack(fill="x", pady=(4, 2))
                _ep_lbl(rk, "Key:").pack(anchor="w")
                key_e = _ck.Entry(rk, textvariable=_ep_key, fg_color=BG, text_color=FG, insertbackground=FG,
                                 font=("Segoe UI", 9), relief="flat", bd=0)
                key_e.pack(fill="x", pady=(2, 0), ipady=4)
                _ep_lbl(rk, "mis. enter, ctrl, f5").pack(anchor="w")
                _edit_widgets["key_e"] = key_e

            # Test Step + Apply buttons
            btn_sep = _ck.Frame(edit_fields, fg_color=MUT, height=1)
            btn_sep.pack(fill="x", pady=(14, 6))

            def _test_one_step():
                sel = st.selection()
                if not sel:
                    return
                vis_idx = st.index(sel[0])
                orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
                if 0 <= orig_idx < len(step_data):
                    tmp = {
                        "name":   "Test Step",
                        "steps":  [step_data[orig_idx]],
                        "speed":  1.0,
                        "repeat": 1,
                        "silent_mode": False,
                    }
                    self._play_simple_recording(tmp, -1)

            _ck.Button(edit_fields, text="Test Step", fg_color=CARD, text_color=BLUE, relief="flat", bd=0,
                      font=("Segoe UI", 9), padx=8, pady=4,
                      activebackground=BLUE, activeforeground=BG,
                      cursor="hand2",
                      command=_test_one_step).pack(fill="x", pady=(0, 4))

            def _apply_edit():
                sel = st.selection()
                if not sel:
                    return
                _push_undo()
                vis_idx = st.index(sel[0])
                orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
                if orig_idx >= len(step_data):
                    return
                atp = _ep_type.get()
                try:
                    d = round(int(_ep_delay.get()) / 1000.0, 3)
                except (ValueError, tk.TclError):
                    d = 0.0
                act = {"type": atp, "delay": d}
                if atp == "click":
                    try:
                        act["x"] = int(_ep_x.get())
                        act["y"] = int(_ep_y.get())
                    except (ValueError, tk.TclError):
                        act["x"] = act["y"] = 0
                    act["button"] = _ep_button.get()
                elif atp == "type":
                    act["text"] = _ep_text.get()
                elif atp == "scroll":
                    try:
                        act["x"] = int(_ep_x.get())
                        act["y"] = int(_ep_y.get())
                        act["amount"] = int(_ep_amount.get())
                    except (ValueError, tk.TclError):
                        act["x"] = act["y"] = act["amount"] = 0
                elif atp == "key":
                    act["key"] = _ep_key.get()
                step_data[orig_idx] = act
                _refresh_tree(keep_sel=orig_idx)

            _ck.Button(edit_fields, text="Terapkan", fg_color=GRN, text_color=BG, relief="flat", bd=0,
                      font=("Segoe UI", 9, "bold"), padx=8, pady=4,
                      activebackground="#3A9F70", activeforeground=BG,
                      cursor="hand2",
                      command=_apply_edit).pack(fill="x")

        _build_edit_panel("click")

        # ------------------------------------------------------------------ #
        #  Refresh / populate tree                                             #
        # ------------------------------------------------------------------ #
        def _refresh_total():
            total_s = sum(a.get("delay", 0) for a in step_data)
            if total_s < 60:
                txt = "{:.1f}s".format(total_s)
            else:
                m = int(total_s) // 60
                s = int(total_s) % 60
                txt = "{}m {}s".format(m, s)
            total_dur_lbl.configure(text="Total: {}".format(txt))

        def _refresh_tree(keep_sel=None):
            # Compute filter
            filt = _filter_var.get()
            _filter_map.clear()
            for i, a in enumerate(step_data):
                if filt == "Semua" or a.get("type", "") == filt:
                    _filter_map.append(i)

            for row in st.get_children():
                st.delete(row)

            for vis_i, orig_i in enumerate(_filter_map):
                a = step_data[orig_i]
                atype    = a.get("type", "")
                x_val    = a.get("x", "-") if atype in ("click", "scroll") else "-"
                y_val    = a.get("y", "-") if atype in ("click", "scroll") else "-"
                delay_s  = a.get("delay", 0)
                delay_ms = int(round(delay_s * 1000))
                filled   = min(10, int(delay_s * 10))
                empty    = max(0, 10 - filled)
                bar      = "\u2593" * filled + "\u2591" * empty
                tag      = atype if atype in ("click", "type", "key", "scroll") else ""
                st.insert("", "end",
                          values=(orig_i + 1, atype, x_val, y_val, delay_ms, bar),
                          tags=(tag,) if tag else ())

            step_count_lbl.configure(
                text="{} langkah".format(len(step_data)))
            _refresh_total()

            if keep_sel is not None:
                # Map original index back to visible index
                try:
                    vis = _filter_map.index(keep_sel)
                    ch = st.get_children()
                    if vis < len(ch):
                        st.selection_set(ch[vis])
                        st.see(ch[vis])
                except ValueError:
                    pass

        filter_cb.bind("<<ComboboxSelected>>", lambda e: _refresh_tree())
        _refresh_tree()

        # ------------------------------------------------------------------ #
        #  Drag-to-reorder                                                     #
        # ------------------------------------------------------------------ #
        _drag = {"src": None, "src_idx": None}

        def _on_drag_start(e):
            item = st.identify_row(e.y)
            if item:
                _drag["src"] = item
                _drag["src_idx"] = st.index(item)
                st.configure(cursor="fleur")

        def _on_drag_motion(e):
            tgt = st.identify_row(e.y)
            if tgt and _drag["src"] and tgt != _drag["src"]:
                tgt_vis = st.index(tgt)
                src_vis = _drag["src_idx"]
                if src_vis != tgt_vis and src_vis is not None:
                    src_orig = _filter_map[src_vis] if _filter_map else src_vis
                    tgt_orig = _filter_map[tgt_vis] if _filter_map else tgt_vis
                    _push_undo()
                    step_data.insert(tgt_orig, step_data.pop(src_orig))
                    _drag["src_idx"] = tgt_vis
                    _refresh_tree(keep_sel=tgt_orig)

        def _on_drag_end(e):
            _drag["src"] = None
            st.configure(cursor="")

        st.bind("<ButtonPress-1>",  _on_drag_start)
        st.bind("<B1-Motion>",      _on_drag_motion)
        st.bind("<ButtonRelease-1>", _on_drag_end)

        # ------------------------------------------------------------------ #
        #  Double-click on delay cell → inline edit popup                     #
        # ------------------------------------------------------------------ #
        def _on_dbl_click(e):
            region = st.identify_region(e.x, e.y)
            col    = st.identify_column(e.x)
            item   = st.identify_row(e.y)
            if region != "cell" or col != "#5" or not item:
                return
            vis_idx  = st.index(item)
            orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
            if orig_idx >= len(step_data):
                return

            # Small popup entry
            x0, y0, x1, y1 = st.bbox(item, "#5")
            popup = ctk.CTkToplevel(dlg)
            popup.withdraw()
            popup.geometry("{}x{}+{}+{}".format(
                x1 - x0, y1 - y0,
                st.winfo_rootx() + x0,
                st.winfo_rooty() + y0))
            popup.configure(fg_color=ACC)

            cur_ms = int(round(step_data[orig_idx].get("delay", 0) * 1000))
            popup_var = tk.StringVar(value=str(cur_ms))
            popup_e = _ck.Entry(popup, textvariable=popup_var, fg_color=BG, text_color=FG, insertbackground=FG,
                               font=("Segoe UI", 9), relief="flat",
                               justify="center")
            popup_e.pack(fill="both", expand=True, padx=1, pady=1)
            popup_e.select_range(0, "end")
            popup_e.focus_set()

            def _commit(e=None):
                try:
                    ms = int(popup_var.get())
                    _push_undo()
                    step_data[orig_idx]["delay"] = round(ms / 1000.0, 3)
                    _refresh_tree(keep_sel=orig_idx)
                except ValueError:
                    pass
                popup.destroy()

            popup_e.bind("<Return>",  _commit)
            popup_e.bind("<Escape>",  lambda e: popup.destroy())
            popup_e.bind("<FocusOut>", lambda e: popup.destroy())
            popup.update()
            popup.deiconify()

        st.bind("<Double-ButtonPress-1>", _on_dbl_click)

        # ------------------------------------------------------------------ #
        #  Treeview selection → populate edit panel                           #
        # ------------------------------------------------------------------ #
        def _on_step_sel(event=None):
            sel = st.selection()
            if not sel:
                edit_header.configure(text="Pilih langkah untuk diedit", text_color=MUT)
                return
            vis_idx  = st.index(sel[0])
            orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
            if orig_idx >= len(step_data):
                return
            a     = step_data[orig_idx]
            atype = a.get("type", "click")
            edit_header.configure(
                text="Edit Step #{} ({})".format(orig_idx + 1, atype), text_color=ACC)
            _ep_type.set(atype)
            _ep_delay.set(int(round(a.get("delay", 0) * 1000)))
            if atype in ("click", "scroll"):
                _ep_x.set(a.get("x", 0))
                _ep_y.set(a.get("y", 0))
            if atype == "click":
                _ep_button.set(a.get("button", "left"))
            elif atype == "type":
                _ep_text.set(a.get("text", ""))
            elif atype == "scroll":
                _ep_amount.set(a.get("amount", 3))
            elif atype == "key":
                _ep_key.set(a.get("key", ""))
            _build_edit_panel(atype)

        st.bind("<<TreeviewSelect>>", _on_step_sel)

        # ------------------------------------------------------------------ #
        #  Bottom bar: playback settings + action buttons                     #
        # ------------------------------------------------------------------ #
        bottom = _ck.Frame(dlg, fg_color=SIDE, padx=12, pady=8)
        bottom.pack(fill="x", side="bottom")

        left_bottom = _ck.Frame(bottom, fg_color=SIDE)
        left_bottom.pack(side="left", fill="y")

        _lbl(left_bottom, "Speed:", text_color=MUT, fg_color=SIDE,
             font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        speed_var = tk.DoubleVar(
            value=float(existing.get("speed", 1.0)) if existing else 1.0)
        _ck.Combobox(left_bottom, textvariable=speed_var,
                     values=[0.25, 0.5, 1.0, 1.5, 2.0],
                     state="readonly", width=5).pack(side="left", padx=(0, 14))

        _lbl(left_bottom, "Ulangi:", text_color=MUT, fg_color=SIDE,
             font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        repeat_var = tk.IntVar(
            value=int(existing.get("repeat", 1)) if existing else 1)
        repeat_sp = tk.Spinbox(left_bottom, from_=1, to=999999, width=6,
                               textvariable=repeat_var, bg=CARD, fg=FG, insertbackground=FG,
                               relief="flat", font=("Segoe UI", 9))
        repeat_sp.pack(side="left", padx=(0, 14), ipady=2)

        silent_var = tk.BooleanVar(
            value=bool(existing.get("silent_mode", False)) if existing else False)
        _ck.Checkbutton(left_bottom, text="Silent Mode",
                       variable=silent_var, fg_color=SIDE, text_color=FG,
                       activebackground=SIDE, activeforeground=FG,
                       selectcolor=CARD,
                       font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))

        unlimited_var = tk.BooleanVar(value=False)

        def _toggle_unlimited():
            if unlimited_var.get():
                repeat_var.set(999999)
                repeat_sp.configure(state="disabled")
            else:
                repeat_var.set(1)
                repeat_sp.configure(state="normal")

        _ck.Checkbutton(left_bottom, text="Loop Tak Terbatas",
                       variable=unlimited_var, command=_toggle_unlimited, fg_color=SIDE, text_color=FG,
                       activebackground=SIDE, activeforeground=FG,
                       selectcolor=CARD,
                       font=("Segoe UI", 9)).pack(side="left")

        right_bottom = _ck.Frame(bottom, fg_color=SIDE)
        right_bottom.pack(side="right", fill="y")

        warn_lbl = _ck.Label(right_bottom,
                            text="Belum tersimpan", fg_color=SIDE, text_color=YEL,
                            font=("Segoe UI", 8))
        warn_lbl.pack(side="left", padx=(0, 12))

        # ------------------------------------------------------------------ #
        #  Save + Test Run + Cancel                                            #
        # ------------------------------------------------------------------ #
        def _save():
            name = name_var.get().strip()
            if not name:
                name = self._ask_rec_name(dlg, "")
            if not name:
                return
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if edit_idx is not None and 0 <= edit_idx < len(self._ud.recordings):
                self._ud.recordings[edit_idx].update({
                    "name":        name,
                    "description": desc_var.get().strip(),
                    "folder":      folder_var.get() or "General",
                    "steps":       list(step_data),
                    "step_count":  len(step_data),
                    "speed":       float(speed_var.get()),
                    "repeat":      int(repeat_var.get()),
                    "silent_mode": bool(silent_var.get()),
                    "modified":    now_str,
                })
            else:
                self._ud.recordings.append({
                    "id":          str(_uuid.uuid4()),
                    "name":        name,
                    "description": desc_var.get().strip(),
                    "folder":      folder_var.get() or "General",
                    "rec_type":    "simple",
                    "steps":       list(step_data),
                    "step_count":  len(step_data),
                    "last_run":    "-",
                    "duration":    "-",
                    "created":     now_str,
                    "modified":    now_str,
                    "speed":       float(speed_var.get()),
                    "repeat":      int(repeat_var.get()),
                    "silent_mode": bool(silent_var.get()),
                })
            self._ud.save()
            self._refresh_recordings_tree()
            dlg.destroy()
            # Restore recorder toolbar after saving
            if self._rec_toolbar_win:
                try:
                    self._rec_toolbar_win.deiconify()
                    self._rec_toolbar_win.lift()
                except Exception:
                    pass
            self._sv.set(
                "Rekaman '{}' disimpan ({} langkah).".format(name, len(step_data)))

        def _test_run():
            if not step_data:
                self._show_alert("Test Run", "Tidak ada langkah.")
                return
            try:
                spd = float(speed_var.get())
            except (ValueError, tk.TclError):
                spd = 1.0
            tmp_rec = {
                "name":        "Test Run",
                "steps":       list(step_data),
                "speed":       spd,
                "repeat":      1,
                "silent_mode": bool(silent_var.get()),
            }
            self._play_simple_recording(tmp_rec, -1)

        lbl_save = ("SIMPAN PERUBAHAN"
                    if (edit_idx is not None and
                        0 <= (edit_idx or -1) < len(self._ud.recordings))
                    else "SIMPAN REKAMAN")
        _ck.Button(right_bottom, text=lbl_save, fg_color=GRN, text_color="#FFFFFF",
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=16, pady=6, cursor="hand2",
                  activebackground="#3A9F70", activeforeground="#FFFFFF",
                  command=_save).pack(side="left", padx=(0, 6))

        _ck.Button(right_bottom, text="Test Run", fg_color=CARD, text_color=FG, relief="flat", bd=0,
                  font=("Segoe UI", 9), padx=10, pady=6, cursor="hand2",
                  activebackground=ACC, activeforeground=BG,
                  command=_test_run).pack(side="left", padx=(0, 6))

        _ck.Button(right_bottom, text="Batal", fg_color=CARD, text_color=MUT, relief="flat", bd=0,
                  font=("Segoe UI", 9), padx=10, pady=6, cursor="hand2",
                  activebackground=RED, activeforeground=BG,
                  command=_on_editor_close).pack(side="left")

        # ------------------------------------------------------------------ #
        #  Keyboard shortcuts                                                  #
        # ------------------------------------------------------------------ #
        dlg.bind("<Delete>",    lambda e: _delete_step())
        dlg.bind("<Control-z>", lambda e: _undo())
        dlg.bind("<Control-y>", lambda e: _redo())
        dlg.bind("<Control-d>", lambda e: _duplicate_step())
        dlg.bind("<Control-c>", lambda e: _copy_step())
        dlg.bind("<Control-v>", lambda e: _paste_step())
        dlg.bind("<Control-a>", lambda e: st.selection_set(st.get_children()))

    # -- Smart Record ---------------------------------------------------

    def _start_smart_rec(self):
        """Open step editor to create / edit automation steps manually."""
        if self._step_editor_open:
            return
        self._show_step_editor([])

    # -- Smart Record toggle (legacy, kept for direct browser recording) ----

    def _toggle_rec(self):
        self._rec = not self._rec
        if self._rbtn:
            self._rbtn.configure(
                text="Stop" if self._rec else "Start Recording")
        if self._rec:
            def _start():
                try:
                    if self.engine and self.engine.browser:
                        self.engine.browser.start_browser_recording()
                except Exception as e:
                    self.logger.error("start_browser_recording: {}".format(e))
            threading.Thread(target=_start, daemon=True).start()
            self._sv.set(
                "Recording... Perform actions in Chrome, then click Stop.")
        else:
            def _stop():
                events = []
                try:
                    if self.engine and self.engine.browser:
                        self.engine.browser.stop_browser_recording()
                        events = self.engine.browser.get_recording_events()
                except Exception as e:
                    self.logger.error("stop_browser_recording: {}".format(e))
                self._root.after(
                    100, lambda evs=events: self._show_step_editor(evs))
            threading.Thread(target=_stop, daemon=True).start()
            self._sv.set("Recording stopped. Opening step editor...")

    def _show_step_editor(self, events_or_steps, edit_idx=None):
        steps = []
        for ev in events_or_steps:
            s = _event_to_step(ev)
            if s:
                steps.append(s)

        # Friendly display names for step types
        _TYPE_LABEL = {
            "Open URL":        "Buka Website",
            "Click":           "Klik Elemen",
            "Type":            "Ketik Teks",
            "Wait":            "Tunggu (detik)",
            "Extract":         "Ambil Teks",
            "Screenshot":      "Ambil Gambar",
            "Click Element":   "Klik Elemen",
            "Type Text":       "Ketik Teks",
            "Extract Text":    "Ambil Teks",
            "Take Screenshot": "Ambil Gambar",
        }
        _TYPE_HINT = {
            "Open URL":        "Masukkan URL lengkap, contoh: https://google.com",
            "Click":           "CSS selector atau XPath elemen yang diklik",
            "Type":            "Format: SELECTOR | teks yang diketik",
            "Wait":            "Durasi tunggu dalam detik, contoh: 2",
            "Extract":         "CSS selector elemen yang teksnya diambil",
            "Screenshot":      "Nama file (opsional), contoh: hasil.png",
        }
        _FRIENDLY_TYPES = [
            "Buka Website", "Klik Elemen", "Ketik Teks",
            "Tunggu (detik)", "Ambil Teks", "Ambil Gambar",
        ]
        _FRIENDLY_TO_ENG = {v: k for k, v in _TYPE_LABEL.items()
                            if k in STEP_TYPES}
        _ENG_TO_FRIENDLY = {k: v for k, v in _TYPE_LABEL.items()
                            if k in STEP_TYPES}

        def _friendly(t):
            return _TYPE_LABEL.get(t, t)

        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Editor Langkah Rekaman")
        dlg.configure(fg_color=BG)
        dlg.resizable(True, True)
        self._step_editor_open = True

        def _on_editor_close():
            self._step_editor_open = False
            try:
                dlg.destroy()
            except Exception:
                pass

        dlg.protocol("WM_DELETE_WINDOW", _on_editor_close)

        # Header
        hdr_f = _ck.Frame(dlg, fg_color=BG)
        hdr_f.pack(fill="x", padx=20, pady=(16, 4))
        _lbl(hdr_f, "Editor Langkah Rekaman",
             font=("Segoe UI", 13, "bold"), fg_color=BG).pack(anchor="w")
        step_count_var = tk.StringVar(
            value="{} langkah   |   Klik baris untuk edit, lalu klik Perbarui".format(
                len(steps)))
        _lbl(hdr_f, "", text_color=MUT, fg_color=BG, font=("Segoe UI", 9),
             textvariable=step_count_var).pack(anchor="w", pady=(2, 0))

        # Panduan cepat
        guide = _ck.Frame(dlg, fg_color="#1A2A1A", padx=12, pady=8)
        guide.pack(fill="x", padx=20, pady=(0, 6))
        _ck.Label(guide, text="Cara pakai: ", fg_color="#1A2A1A", text_color=GRN,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        _ck.Label(guide,
                 text="Pilih baris di tabel -> Edit tipe & nilai di bawah -> Klik [Perbarui]. "
                      "Klik [+ Tambah] untuk langkah baru.", fg_color="#1A2A1A", text_color=FG,
                 font=("Segoe UI", 8), wraplength=580, justify="left").pack(
            side="left", fill="x", expand=True)

        lf = _ck.Frame(dlg, fg_color=CARD, padx=8, pady=8)
        lf.pack(fill="both", expand=True, padx=20, pady=(0, 6))

        st = ttk.Treeview(lf, columns=("no", "type", "value"),
                          show="headings", selectmode="browse")
        st.heading("no",    text="#")
        st.heading("type",  text="Jenis Aksi")
        st.heading("value", text="Nilai / Target")
        st.column("no",    width=36, anchor="center")
        st.column("type",  width=130)
        st.column("value", width=420)
        vsb = _ck.Scrollbar(lf, orient="vertical", command=st.yview)
        st.configure(yscrollcommand=vsb.set)
        st.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        step_data = list(steps)

        def refresh():
            step_count_var.set(
                "{} langkah   |   Klik baris untuk edit, lalu klik Perbarui".format(
                    len(step_data)))
            for row in st.get_children():
                st.delete(row)
            for i, s in enumerate(step_data, 1):
                st.insert("", "end",
                          values=(i, _friendly(s["type"]), s.get("value", "")))

        refresh()

        # Edit form
        form = _ck.Frame(dlg, fg_color=CARD, padx=14, pady=10)
        form.pack(fill="x", padx=20, pady=(0, 4))

        type_var = tk.StringVar(value=_FRIENDLY_TYPES[0])
        val_var  = tk.StringVar()
        hint_var = tk.StringVar(value="Pilih jenis aksi untuk melihat petunjuk")

        r1 = _ck.Frame(form, fg_color=CARD)
        r1.pack(fill="x", pady=(0, 4))
        _lbl(r1, "Jenis Aksi:", text_color=MUT, fg_color=CARD, width=12, anchor="w").pack(side="left")
        type_cb = _ck.Combobox(r1, textvariable=type_var,
                               values=_FRIENDLY_TYPES,
                               state="readonly", width=18)
        type_cb.pack(side="left", padx=(0, 8))
        hint_lbl = _ck.Label(r1, textvariable=hint_var, fg_color=CARD, text_color=MUT, font=("Segoe UI", 8),
                            anchor="w")
        hint_lbl.pack(side="left", fill="x", expand=True)

        def _update_hint(*_):
            eng = _FRIENDLY_TO_ENG.get(type_var.get(), type_var.get())
            hint_var.set(_TYPE_HINT.get(eng, ""))
        type_cb.bind("<<ComboboxSelected>>", _update_hint)

        r2 = _ck.Frame(form, fg_color=CARD)
        r2.pack(fill="x")
        _lbl(r2, "Nilai / Target:", text_color=MUT, fg_color=CARD, width=12, anchor="w").pack(
            side="left")
        _ck.Entry(r2, textvariable=val_var,
                  font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True)

        def on_sel(event):
            s = st.selection()
            if s:
                i = st.index(s[0])
                if i < len(step_data):
                    eng = step_data[i]["type"]
                    type_var.set(_ENG_TO_FRIENDLY.get(eng, eng))
                    val_var.set(step_data[i].get("value", ""))
                    _update_hint()
        st.bind("<<TreeviewSelect>>", on_sel)

        def _get_eng_type():
            return _FRIENDLY_TO_ENG.get(type_var.get(), type_var.get())

        def upd():
            s = st.selection()
            if not s:
                return
            i = st.index(s[0])
            if i < len(step_data):
                step_data[i] = {"type": _get_eng_type(), "value": val_var.get()}
                refresh()

        def add():
            step_data.append({"type": _get_eng_type(), "value": val_var.get()})
            refresh()

        def delete():
            s = st.selection()
            if not s:
                return
            i = st.index(s[0])
            if i < len(step_data):
                del step_data[i]
                refresh()

        def move_up():
            s = st.selection()
            if not s:
                return
            i = st.index(s[0])
            if i > 0:
                step_data[i - 1], step_data[i] = step_data[i], step_data[i - 1]
                refresh()

        def move_down():
            s = st.selection()
            if not s:
                return
            i = st.index(s[0])
            if i < len(step_data) - 1:
                step_data[i + 1], step_data[i] = step_data[i], step_data[i + 1]
                refresh()

        btn_row = _ck.Frame(form, fg_color=CARD)
        btn_row.pack(fill="x", pady=(8, 0))
        for txt, cmd, col in [
            ("Perbarui",  upd,       ACC),
            ("+ Tambah",  add,       GRN),
            ("Hapus",     delete,    RED),
            ("Naik",      move_up,   MUT),
            ("Turun",     move_down, MUT),
        ]:
            _ck.Button(btn_row, text=txt, fg_color=col if col != MUT else CARD, text_color=BG if col != MUT else FG,
                      font=("Segoe UI", 9), relief="flat", bd=0,
                      padx=10, pady=5, cursor="hand2",
                      command=cmd).pack(side="left", padx=(0, 4))

        def save_rec():
            name = self._ask_rec_name(dlg, "")
            if not name:
                return
            folder = (self._rec_folder_var.get()
                      if self._rec_folder_var else "General")
            if edit_idx is not None and 0 <= edit_idx < len(self._ud.recordings):
                self._ud.recordings[edit_idx].update({
                    "steps":      list(step_data),
                    "step_count": len(step_data),
                })
            else:
                self._ud.recordings.append({
                    "name":       name,
                    "rec_type":   "smart",
                    "folder":     folder,
                    "steps":      list(step_data),
                    "step_count": len(step_data),
                    "last_run":   "-",
                    "duration":   "-",
                    "created":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
            self._ud.save()
            self._refresh_recordings_tree()
            self._step_editor_open = False
            dlg.destroy()
            self._sv.set(
                "Rekaman '{}' disimpan ({} langkah).".format(name, len(step_data)))

        sr = _ck.Frame(dlg, fg_color=BG)
        sr.pack(fill="x", padx=20, pady=(0, 16))
        _ck.Button(sr, text="Simpan Rekaman", fg_color=ACC, text_color=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=16, pady=8, cursor="hand2",
                  command=save_rec).pack(side="left")
        _ck.Button(sr, text="Batal",
                   command=_on_editor_close).pack(side="left", padx=(8, 0))

        # Centre on screen, force render, bring to front
        dlg.update_idletasks()
        w, h = 720, 580
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry("{}x{}+{}+{}".format(
            w, h, (sw - w) // 2, (sh - h) // 2))
        dlg.update()
        dlg.deiconify()
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()

    def _play_selected_recording(self):
        if not self._recordings_tree:
            return
        sel = self._recordings_tree.selection()
        if not sel:
            self._show_alert("Mainkan", "Pilih rekaman dari daftar terlebih dahulu.")
            return
        idx = self._recordings_tree.index(sel[0])
        if idx >= len(self._ud.recordings):
            return
        rec   = self._ud.recordings[idx]
        steps = rec.get("steps", [])
        if not steps:
            self._show_alert("Mainkan", "Rekaman ini tidak memiliki langkah apapun.")
            return

        # Route to simple or smart playback
        if rec.get("rec_type", "smart") == "simple":
            self._play_simple_recording(rec, idx)
            return

        engine_steps = [
            {"type":  _STEP_TO_ENGINE.get(
                s.get("type",""), s.get("type","")),
             "value": s.get("value","")}
            for s in steps
        ]

        self._playback_stop.clear()
        self._playback_pause.clear()
        total      = len(engine_steps)
        start_time = time.time()
        win        = self._show_playback_window(total, rec.get("name",""))

        def on_step(i, ok, msg):
            while self._playback_pause.is_set():
                if self._playback_stop.is_set():
                    break
                time.sleep(0.1)
            if self._playback_stop.is_set():
                raise RuntimeError("Playback stopped by user.")
            t = steps[i].get("type","")  if i < len(steps) else ""
            v = steps[i].get("value","")[:28] if i < len(steps) else ""
            desc = "Step {}: {} - {}".format(i+1, t, v)
            self._root.after(
                0, lambda d=desc:
                self._update_playback_window(win, i+1, total, d))

        self._playback_running = True

        def _run():
            ok_count = 0
            try:
                if self.engine and self.engine.browser:
                    results = self.engine.browser.run_sequence(
                        engine_steps, on_step=on_step)
                    ok_count = sum(1 for r in results if r.get("success"))
            except Exception as e:
                self.logger.error("Playback error: {}".format(e))
            self._playback_running = False
            duration = "{:.1f}s".format(time.time() - start_time)
            self._ud.recordings[idx]["last_run"] = \
                datetime.now().strftime("%Y-%m-%d %H:%M")
            self._ud.recordings[idx]["duration"] = duration
            self._ud.log("Play: {}".format(rec.get("name","")),
                         "{}/{} steps OK".format(ok_count, total))
            self._ud.save()
            self._root.after(0, lambda: [
                self._close_playback_window(win),
                self._refresh_recordings_tree(),
                self._sv.set("Done: {}/{} steps successful.".format(
                    ok_count, total)),
            ])
        threading.Thread(target=_run, daemon=True).start()

    def _show_playback_window(self, total, name=""):
        win = ctk.CTkToplevel(self._root)
        win.withdraw()
        win.title("Playing...")
        win.geometry("220x195")
        win.configure(fg_color=CARD)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        sw = self._root.winfo_screenwidth()
        win.geometry("220x195+{}+40".format(sw - 240))
        def _on_playback_close():
            self._playback_stop.set()
        win.protocol("WM_DELETE_WINDOW", _on_playback_close)

        _lbl(win, (name[:22] or "Playing Recording"), text_color=ACC, fg_color=CARD, font=("Segoe UI", 10, "bold")).pack(
            pady=(12, 4), padx=12)
        step_var = tk.StringVar(value="Step 0 / {}".format(total))
        _ck.Label(win, textvariable=step_var, text_color=FG, fg_color=CARD,
                 font=("Segoe UI", 9)).pack(padx=12)
        desc_var = tk.StringVar(value="Preparing...")
        _ck.Label(win, textvariable=desc_var, text_color=MUT, fg_color=CARD,
                 font=("Segoe UI", 8), wraplength=196,
                 justify="left").pack(padx=12, pady=(2, 6))

        pct_var = tk.StringVar(value="0%")
        _ck.Label(win, textvariable=pct_var, text_color=GRN, fg_color=CARD,
                 font=("Consolas", 9, "bold")).pack(padx=12)
        pb = tk.Canvas(win, width=196, height=10, bg=BG, highlightthickness=0)
        pb.pack(padx=12, pady=(2, 8))
        win._pct_var = pct_var

        btn_row  = _ck.Frame(win, fg_color=CARD)
        btn_row.pack(fill="x", padx=12, pady=(0, 12))
        pause_var = tk.StringVar(value="Pause")

        def toggle_pause():
            if self._playback_pause.is_set():
                self._playback_pause.clear()
                pause_var.set("Pause")
            else:
                self._playback_pause.set()
                pause_var.set("Resume")

        _ck.Button(btn_row, textvariable=pause_var, fg_color=YEL, text_color=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=8, pady=4, command=toggle_pause).pack(
            side="left", padx=(0, 4))
        _ck.Button(btn_row, text="Stop", fg_color=RED, text_color=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=8, pady=4,
                  command=self._playback_stop.set).pack(side="left")

        win._step_var = step_var
        win._desc_var = desc_var
        win._pb_canvas = pb
        win.update()
        win.deiconify()
        return win

    def _update_playback_window(self, win, step, total, desc):
        try:
            if not win.winfo_exists():
                return
            win._step_var.set("Step {} / {}".format(step, total))
            win._desc_var.set(desc[:60])
            pct = step / total if total else 0
            win._pct_var.set("{}%".format(int(pct * 100)))
            win._pb_canvas.delete("pb")
            win._pb_canvas.create_rectangle(
                0, 0, int(196 * pct), 10,
                fill=GRN, outline="", tags="pb")
        except Exception:
            pass

    def _close_playback_window(self, win):
        try:
            if win and win.winfo_exists():
                win.destroy()
        except Exception:
            pass

    def _play_simple_recording(self, rec, idx):
        """Play a simple (pyautogui) recording with a floating progress window.

        Pass idx=-1 for test runs (no saves to user_data).
        """
        from modules.macro.simple_recorder import SimpleRecorder
        steps       = rec.get("steps", [])
        speed       = float(rec.get("speed",  1.0))
        repeat      = int(rec.get("repeat", 1))
        silent_mode = bool(rec.get("silent_mode", False))
        total       = len(steps) * repeat

        self._playback_stop.clear()
        self._playback_pause.clear()
        self._playback_running = True
        start_time = time.time()
        win = self._show_playback_window(total, rec.get("name", ""))

        def _on_step(step_no, _total, desc):
            self._root.after(
                0, lambda s=step_no, d=desc:
                self._update_playback_window(win, s + 1, total, d))

        def _silent_click(x, y, button):
            """Click at (x, y) using ctypes, then restore cursor to original position."""
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            old_x, old_y = pt.x, pt.y
            user32.SetCursorPos(x, y)
            if button == "right":
                user32.mouse_event(8, 0, 0, 0, 0)   # MOUSEEVENTF_RIGHTDOWN
                user32.mouse_event(16, 0, 0, 0, 0)  # MOUSEEVENTF_RIGHTUP
            else:
                user32.mouse_event(2, 0, 0, 0, 0)   # MOUSEEVENTF_LEFTDOWN
                user32.mouse_event(4, 0, 0, 0, 0)   # MOUSEEVENTF_LEFTUP
            user32.SetCursorPos(old_x, old_y)

        def _run():
            recorder = SimpleRecorder()
            try:
                recorder.play_recording(
                    steps, speed=speed, repeat=repeat,
                    on_step=_on_step,
                    stop_event=self._playback_stop,
                    pause_event=self._playback_pause,
                    silent_mode=silent_mode,
                    silent_click_fn=_silent_click if silent_mode else None)
            except Exception as e:
                self.logger.error("Simple playback error: {}".format(e))
                self._root.after(0, lambda err=str(e): self._update_playback_window(
                    win, 0, total, "ERROR: {}".format(err[:50])))
            self._playback_running = False
            duration = "{:.1f}s".format(time.time() - start_time)
            stopped = self._playback_stop.is_set()
            if 0 <= idx < len(self._ud.recordings):
                self._ud.recordings[idx]["last_run"] = \
                    datetime.now().strftime("%Y-%m-%d %H:%M")
                self._ud.recordings[idx]["duration"] = duration
                self._ud.log("Play: {}".format(rec.get("name", "")),
                             "Simple playback done")
                self._ud.save()
            macro_name = rec.get("name", "Macro")
            def _finish(name=macro_name, dur=duration, did_stop=stopped):
                self._close_playback_window(win)
                self._refresh_recordings_tree()
                if did_stop:
                    self._sv.set("Playback dihentikan.")
                    self._show_toast("⏹ {} dihentikan ({})".format(name, dur), duration=3000)
                else:
                    self._sv.set("Simple playback complete.")
                    self._show_toast("✅ {} selesai ({})".format(name, dur), duration=4000)
            self._root.after(0, _finish)

        threading.Thread(target=_run, daemon=True).start()

    def _refresh_recordings_tree(self):
        if not self._recordings_tree:
            return
        for row in self._recordings_tree.get_children():
            self._recordings_tree.delete(row)
        for rec in self._ud.recordings:
            rtype = rec.get("rec_type", "smart")
            tag   = "simple_tag" if rtype == "simple" else "smart_tag"
            self._recordings_tree.insert("", "end", tags=(tag,), values=(
                rec.get("name", ""),
                "Simple" if rtype == "simple" else "Smart",
                rec.get("step_count", len(rec.get("steps", []))),
                rec.get("last_run", "-"),
                rec.get("duration", "-"),
            ))
        # Update counter badge
        n = len(self._ud.recordings)
        if hasattr(self, "_rec_count_lbl") and self._rec_count_lbl:
            try:
                if n == 0:
                    self._rec_count_lbl.configure(text="", fg_color=CARD)
                else:
                    self._rec_count_lbl.configure(
                        text=" {} ".format(n), fg_color=ACC)
            except Exception:
                pass

    def _on_rec_tree_select(self):
        """Update _last_selected_rec_idx when user clicks a recording."""
        if not self._recordings_tree:
            return
        sel = self._recordings_tree.selection()
        if sel:
            idx = self._recordings_tree.index(sel[0])
            if idx < len(self._ud.recordings):
                self._last_selected_rec_idx = idx

    def _edit_selected_recording(self):
        if not self._recordings_tree:
            return
        sel = self._recordings_tree.selection()
        if not sel:
            return
        idx = self._recordings_tree.index(sel[0])
        if idx >= len(self._ud.recordings):
            return
        rec = self._ud.recordings[idx]
        if rec.get("rec_type", "smart") == "simple":
            self._show_simple_step_editor(
                list(rec.get("steps", [])), edit_idx=idx)
        else:
            self._show_step_editor(
                rec.get("steps", []), edit_idx=idx)

    def _delete_selected_recording(self):
        if not self._recordings_tree:
            return
        sel = self._recordings_tree.selection()
        if not sel:
            return
        idx = self._recordings_tree.index(sel[0])
        if idx >= len(self._ud.recordings):
            return
        name = self._ud.recordings[idx].get("name", "")
        # Custom styled confirm dialog
        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Hapus Rekaman")
        dlg.configure(fg_color=BG)
        dlg.resizable(False, False)
        dlg.update()
        dlg.grab_set()
        dlg.attributes("-topmost", True)
        dlg.overrideredirect(False)

        hdr = _ck.Frame(dlg, fg_color=RED, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        _ck.Label(hdr, text="  Hapus Rekaman", fg_color=RED, text_color="white",
                 font=("Segoe UI", 11, "bold")).pack(side="left", pady=10)

        body = _ck.Frame(dlg, fg_color=BG, padx=24, pady=18)
        body.pack(fill="both", expand=True)
        _ck.Label(body,
                 text='Yakin hapus rekaman ini?', fg_color=BG, text_color=FG, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        _ck.Label(body, text='"{}"'.format(name), fg_color=BG, text_color=ACC2, font=("Segoe UI", 10, "italic"),
                 wraplength=320).pack(anchor="w", pady=(4, 12))
        _ck.Label(body, text="Rekaman yang dihapus tidak bisa dipulihkan.", fg_color=BG, text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w")

        result = [False]
        btn_row = _ck.Frame(body, fg_color=BG)
        btn_row.pack(anchor="w", pady=(16, 0))

        def _yes():
            result[0] = True
            dlg.destroy()

        _ck.Button(btn_row, text="Hapus", fg_color=RED, text_color="white",
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=18, pady=7, cursor="hand2",
                  command=_yes).pack(side="left", padx=(0, 8))
        _ck.Button(btn_row, text="Batal", fg_color=CARD, text_color=FG,
                  font=("Segoe UI", 10), relief="flat", bd=0,
                  padx=14, pady=7, cursor="hand2",
                  command=dlg.destroy).pack(side="left")

        dlg.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        w, h = 380, 220
        dlg.geometry("{}x{}+{}+{}".format(w, h, (sw - w) // 2, (sh - h) // 2))
        dlg.deiconify()
        self._root.wait_window(dlg)

        if result[0]:
            del self._ud.recordings[idx]
            self._ud.save()
            self._refresh_recordings_tree()

    def _move_rec_up(self):
        """Move selected recording one position up in the list."""
        if not self._recordings_tree:
            return
        sel = self._recordings_tree.selection()
        if not sel:
            return
        idx = self._recordings_tree.index(sel[0])
        if idx <= 0 or idx >= len(self._ud.recordings):
            return
        recs = self._ud.recordings
        recs[idx - 1], recs[idx] = recs[idx], recs[idx - 1]
        self._ud.save()
        self._refresh_recordings_tree()
        # Re-select the moved item
        children = self._recordings_tree.get_children()
        if idx - 1 < len(children):
            self._recordings_tree.selection_set(children[idx - 1])
            self._recordings_tree.see(children[idx - 1])

    def _move_rec_down(self):
        """Move selected recording one position down in the list."""
        if not self._recordings_tree:
            return
        sel = self._recordings_tree.selection()
        if not sel:
            return
        idx = self._recordings_tree.index(sel[0])
        if idx < 0 or idx >= len(self._ud.recordings) - 1:
            return
        recs = self._ud.recordings
        recs[idx], recs[idx + 1] = recs[idx + 1], recs[idx]
        self._ud.save()
        self._refresh_recordings_tree()
        children = self._recordings_tree.get_children()
        if idx + 1 < len(children):
            self._recordings_tree.selection_set(children[idx + 1])
            self._recordings_tree.see(children[idx + 1])

    def _ask_rec_name(self, parent, current_name=""):
        """
        Show a styled dialog to enter/edit a recording name.
        Returns the entered name string, or "" if cancelled.
        """
        dlg = ctk.CTkToplevel(parent)
        dlg.withdraw()
        dlg.title("Nama Rekaman")
        dlg.configure(fg_color=BG)
        dlg.resizable(False, False)
        dlg.update()
        dlg.grab_set()
        dlg.attributes("-topmost", True)

        # ── Header ────────────────────────────────────────────────────
        hdr = _ck.Frame(dlg, fg_color=ACC, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        _ck.Label(hdr, text="  Simpan Rekaman", fg_color=ACC, text_color="white",
                 font=("Segoe UI", 12, "bold")).pack(side="left", pady=12, padx=4)

        # ── Body ──────────────────────────────────────────────────────
        body = _ck.Frame(dlg, fg_color=BG, padx=24, pady=20)
        body.pack(fill="both", expand=True)

        _ck.Label(body, text="Nama Rekaman", fg_color=BG, text_color=FG,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")

        # Entry with rounded-look border frame
        ef = _ck.Frame(body, fg_color=ACC, padx=1, pady=1)
        ef.pack(fill="x", pady=(4, 2))
        name_entry = _ck.Entry(ef, fg_color=CARD2, text_color=FG, insertbackground=FG,
                              relief="flat", font=("Segoe UI", 11),
                              bd=6)
        name_entry.pack(fill="x")
        if current_name:
            name_entry.insert(0, current_name)
            name_entry.select_range(0, "end")

        _ck.Label(body,
                 text="Contoh: Login Admin, Isi Form Pesanan, Klik Tombol Beli", fg_color=BG, text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 14))

        # ── Buttons ───────────────────────────────────────────────────
        result = [""]
        btn_row = _ck.Frame(body, fg_color=BG)
        btn_row.pack(anchor="w")

        def _save():
            val = name_entry.get().strip()
            if not val:
                name_entry.configure(fg_color="#3A1A1A")
                name_entry.focus_set()
                return
            result[0] = val
            dlg.destroy()

        def _cancel():
            dlg.destroy()

        _ck.Button(btn_row, text="Simpan", fg_color=ACC, text_color="white",
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=20, pady=8, cursor="hand2",
                  command=_save).pack(side="left", padx=(0, 8))
        _ck.Button(btn_row, text="Batal", fg_color=CARD, text_color=FG,
                  font=("Segoe UI", 10), relief="flat", bd=0,
                  padx=14, pady=8, cursor="hand2",
                  command=_cancel).pack(side="left")

        dlg.bind("<Return>", lambda e: _save())
        dlg.bind("<Escape>", lambda e: _cancel())

        dlg.update_idletasks()
        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()
        w, h = 400, 230
        dlg.geometry("{}x{}+{}+{}".format(w, h, (sw - w) // 2, (sh - h) // 2))
        dlg.deiconify()
        name_entry.focus_set()
        parent.wait_window(dlg)
        return result[0]

    # ================================================================
    #  Task actions
    # ================================================================

    def _selected_task_idx(self):
        if not self._tasks_tree:
            return None
        sel = self._tasks_tree.selection()
        if not sel:
            return None
        idx = self._tasks_tree.index(sel[0])
        return idx if idx < len(self._ud.tasks) else None

    def _task_countdown(self, task: dict) -> str:
        """Return human-readable time until next run, or overdue message."""
        from datetime import timezone, timedelta
        stype   = task.get("schedule_type", "manual")
        enabled = task.get("enabled", True)
        if stype == "manual" or not enabled:
            return "Paused" if not enabled else "-"

        # Ask the scheduler for the authoritative next_run_time
        task_id = task.get("id", "")
        if task_id and self.engine and self.engine.scheduler:
            try:
                nrt = self.engine.scheduler.get_job_next_run(task_id)
                if nrt:
                    now     = datetime.now(timezone.utc)
                    delta   = int((nrt - now).total_seconds())
                    if delta < 0:
                        return "Overdue by {}".format(_fmt_duration(-delta))
                    return "Runs in {}".format(_fmt_duration(delta))
            except Exception:
                pass

        # Fallback: calculate manually from last_run + schedule
        now          = datetime.now()
        sval         = task.get("schedule_value", "")
        stime        = task.get("schedule_time", "09:00")
        last_run_str = task.get("last_run", "-")

        try:
            if stype == "interval" and sval:
                from datetime import timedelta as td
                minutes = int(sval)
                if last_run_str and last_run_str != "-":
                    last_dt  = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M")
                    next_dt  = last_dt + td(minutes=minutes)
                else:
                    next_dt = now
                delta = int((next_dt - now).total_seconds())
                if delta < 0:
                    return "Overdue by {}".format(_fmt_duration(-delta))
                return "Runs in {}".format(_fmt_duration(delta))

            elif stype == "daily":
                from datetime import timedelta as td
                h, m     = stime.split(":")
                next_dt  = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
                if next_dt <= now:
                    next_dt += td(days=1)
                delta = int((next_dt - now).total_seconds())
                return "Runs in {}".format(_fmt_duration(delta))

            elif stype == "hourly":
                from datetime import timedelta as td
                next_dt = now.replace(minute=0, second=0, microsecond=0) + td(hours=1)
                delta   = int((next_dt - now).total_seconds())
                return "Runs in {}".format(_fmt_duration(delta))
        except Exception:
            pass
        return "-"

    def _refresh_tasks_tree(self):
        if not self._tasks_tree:
            return
        try:
            if not self._tasks_tree.winfo_exists():
                return
        except Exception:
            return
        for row in self._tasks_tree.get_children():
            self._tasks_tree.delete(row)
        for task in list(self._ud.tasks):
            stype = task.get("schedule_type", "manual")
            sval  = task.get("schedule_value", "")
            stime = task.get("schedule_time", "")
            if stype == "interval" and sval:
                sched = "Every {}m".format(sval)
            elif stype == "daily" and stime:
                sched = "Daily {}".format(stime)
            elif stype == "hourly":
                sched = "Every hour"
            else:
                sched = "Manual"

            enabled     = task.get("enabled", True)
            last_status = task.get("last_status", "-")
            last_run    = task.get("last_run", "-")
            countdown   = self._task_countdown(task)

            # Decorate last run with result indicator
            if last_status == "OK":
                last_run_disp = "[+] {}".format(last_run)
                row_tag = "status_ok"
            elif last_status in ("FAIL", "Error"):
                last_run_disp = "[X] {}".format(last_run)
                row_tag = "status_fail"
            elif last_status == "Running":
                last_run_disp = last_run
                row_tag = "status_running"
            elif not enabled:
                last_run_disp = last_run
                row_tag = "status_paused"
            else:
                last_run_disp = last_run
                row_tag = ""

            self._tasks_tree.insert("", "end", values=(
                task.get("name", ""),
                len(task.get("steps", [])),
                sched,
                countdown,
                last_run_disp,
                last_status,
                "Yes" if enabled else "No",
            ), tags=(row_tag,) if row_tag else ())

    def _tasks_tree_right_click(self, event):
        """Right-click context menu with per-row actions."""
        iid = self._tasks_tree.identify_row(event.y)
        if not iid:
            return
        self._tasks_tree.selection_set(iid)
        menu = tk.Menu(self._root, tearoff=0, bg=CARD, fg=FG,
                       activebackground=ACC, activeforeground=BG,
                       font=("Segoe UI", 10))
        menu.add_command(label="Run Now",      command=self._run_selected_task)
        menu.add_command(label="Edit",         command=lambda: self._mb_open(
            parent=self._mb_list_view.master,
            edit_idx=self._selected_task_idx()))
        menu.add_separator()
        menu.add_command(label="Toggle ON/OFF", command=self._toggle_task_enabled)
        menu.add_command(label="Delete",        command=self._delete_selected_task)
        menu.post(event.x_root, event.y_root)

    def _start_countdown_refresh(self):
        """Refresh countdown timers every 30 s while the tasks tree is alive."""
        def _tick():
            if not self._tasks_tree:
                return
            try:
                if self._tasks_tree.winfo_exists():
                    self._refresh_tasks_tree()
                    self._root.after(30000, _tick)
            except Exception:
                pass
        self._root.after(30000, _tick)

    def _run_task_by_idx(self, idx: int):
        """Run a task by index — called from home page My Tasks quick-run."""
        if idx < 0 or idx >= len(self._ud.tasks):
            return
        task = self._ud.tasks[idx]
        if not self._confirm_run_dialog(task):
            return
        stop_ev = threading.Event()
        self._run_stop_flag = stop_ev
        if task.get("continuous_mode"):
            panel = self._show_continuous_progress_panel(task, stop_ev)
            threading.Thread(target=self._run_continuous_task_thread,
                             args=(task, idx, stop_ev, panel), daemon=True).start()
        else:
            panel = self._show_run_progress_panel(task, stop_ev)
            threading.Thread(target=self._run_task_thread,
                             args=(task, idx, stop_ev, panel), daemon=True).start()

    def _run_selected_task(self):
        if not self._tasks_tree:
            return
        sel = self._tasks_tree.selection()
        if not sel:
            self._show_alert("Run Task", "Select a task first.")
            return
        idx = self._tasks_tree.index(sel[0])
        if idx >= len(self._ud.tasks):
            return
        task = self._ud.tasks[idx]
        if not self._confirm_run_dialog(task):
            return
        stop_ev = threading.Event()
        self._run_stop_flag = stop_ev
        if task.get("continuous_mode"):
            panel = self._show_continuous_progress_panel(task, stop_ev)
            threading.Thread(target=self._run_continuous_task_thread,
                             args=(task, idx, stop_ev, panel),
                             daemon=True).start()
        else:
            panel = self._show_run_progress_panel(task, stop_ev)
            threading.Thread(target=self._run_task_thread,
                             args=(task, idx, stop_ev, panel),
                             daemon=True).start()

    def _confirm_run_dialog(self, task: dict) -> bool:
        """Show a confirmation dialog summarising what the macro will do."""
        steps = task.get("steps", [])
        lines = []
        for i, s in enumerate(steps, 1):
            lines.append("  {}. {}".format(i, _step_label(s)[:60]))
        step_text = "\n".join(lines) if lines else "  (no steps)"
        msg = (
            'This macro will:\n\n'
            + step_text
            + '\n\nAre you sure you want to run it?'
        )

        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Confirm Run")
        dlg.configure(fg_color=BG)
        dlg.resizable(False, False)
        dlg.update()
        dlg.grab_set()
        dlg.attributes("-topmost", True)

        _ck.Label(dlg, text='Run: "{}"'.format(task.get("name", "")), fg_color=BG, text_color=FG, font=("Segoe UI", 12, "bold"),
                 padx=20, pady=(14)).pack(anchor="w")
        _ck.Label(dlg, text=msg, fg_color=BG, text_color=MUT,
                 font=("Segoe UI", 9), justify="left",
                 padx=20).pack(anchor="w")

        result = [False]
        btn_row = _ck.Frame(dlg, fg_color=BG)
        btn_row.pack(fill="x", padx=20, pady=14)

        def _yes():
            result[0] = True
            dlg.destroy()

        def _no():
            dlg.destroy()

        _ck.Button(btn_row, text="Yes, Run", fg_color=GRN, text_color=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=16, pady=7, cursor="hand2",
                  command=_yes).pack(side="left", padx=(0, 8))
        _ck.Button(btn_row, text="Cancel", fg_color=CARD, text_color=FG,
                  font=("Segoe UI", 10), relief="flat", bd=0,
                  padx=16, pady=7, cursor="hand2",
                  command=_no).pack(side="left")

        dlg.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        w, h = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
        dlg.geometry("{}x{}+{}+{}".format(
            max(w, 400), max(h, 200),
            (sw - max(w, 400)) // 2, (sh - max(h, 200)) // 2))
        dlg.deiconify()
        self._root.wait_window(dlg)
        return result[0]

    def _show_run_progress_panel(self, task: dict, stop_flag) -> dict:
        """Show a floating live progress panel. Returns dict of widget refs."""
        steps = task.get("steps", [])
        total = len(steps)

        w = ctk.CTkToplevel(self._root)
        w.withdraw()
        w.title("Running: {}".format(task.get("name", "")))
        w.configure(fg_color=BG)
        w.resizable(False, False)
        w.attributes("-topmost", True)
        w.geometry("440x340")

        _ck.Label(w, text="Running: {}".format(task.get("name", "")), fg_color=BG, text_color=FG, font=("Segoe UI", 11, "bold"),
                 padx=16, pady=10).pack(anchor="w")

        step_lbl = _ck.Label(w, text="Preparing...", fg_color=BG, text_color=ACC, font=("Segoe UI", 10),
                            padx=16, anchor="w")
        step_lbl.pack(fill="x")

        progress_var = tk.DoubleVar(value=0.0)
        pb = ttk.Progressbar(w, variable=progress_var, maximum=total or 1,
                             length=400, mode="determinate")
        pb.pack(padx=16, pady=(6, 0))

        log_frame = _ck.Frame(w, fg_color=BG)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(8, 0))
        log_box = _ck.ScrolledText(
            log_frame, fg_color=CARD, text_color=FG, font=("Consolas", 8),
            relief="flat", height=8, state="disabled")
        log_box.pack(fill="both", expand=True)
        log_box.tag_configure("ok",   foreground=GRN)
        log_box.tag_configure("fail", foreground=RED)
        log_box.tag_configure("info", foreground=MUT)

        btn_row = _ck.Frame(w, fg_color=BG)
        btn_row.pack(fill="x", padx=16, pady=10)

        def _stop():
            stop_flag.set()
            stop_btn.configure(state="disabled", text="Stopping...")

        stop_btn = _ck.Button(btn_row, text="Stop", fg_color=RED, text_color=BG,
                             font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                             padx=12, pady=5, cursor="hand2", command=_stop)
        stop_btn.pack(side="left")

        panel = {
            "window":       w,
            "step_lbl":     step_lbl,
            "progress_var": progress_var,
            "log_box":      log_box,
            "stop_btn":     stop_btn,
            "total":        total,
        }
        w.update()
        w.deiconify()
        return panel

    def _run_task_thread(self, task, idx, stop_flag=None, panel=None):
        self._root.after(0, lambda: self._sv.set(
            "Running: {}...".format(task["name"])))
        # Mark as Running immediately so the tree shows yellow status
        with self._ud_lock:
            if idx < len(self._ud.tasks):
                self._ud.tasks[idx]["last_status"] = "Running"
        self._root.after(0, self._refresh_tasks_tree)
        ok_count, total = 0, len(task.get("steps", []))
        status = "FAIL"
        _exc = None

        def _step_cb(step_num, result, ok):
            tag = "ok" if ok else "fail"
            msg = "Step {}: {}\n".format(step_num + 1, result)
            if panel:
                def _upd(m=msg, t=tag, n=step_num):
                    try:
                        lb = panel["log_box"]
                        lb.configure(state="normal")
                        lb.insert(tk.END, m, t)
                        lb.see(tk.END)
                        lb.configure(state="disabled")
                        panel["progress_var"].set(n + 1)
                    except Exception:
                        pass
                self._root.after(0, _upd)

        def _progress_cb(step_idx, total_steps, step_type):
            if panel:
                lbl_text = "Step {}/{}: {}".format(
                    step_idx + 1, total_steps, step_type.replace("_", " "))
                self._root.after(
                    0, lambda t=lbl_text: panel["step_lbl"].configure(text=t)
                    if panel["window"].winfo_exists() else None)

        results = []
        try:
            if self.engine:
                results = self.engine.run_smart_task(
                    task,
                    progress_cb=_progress_cb,
                    step_callback=_step_cb,
                    stop_flag=stop_flag,
                )
                ok_count = sum(1 for r in results if r.get("ok"))
                total    = len(results)
                status   = "OK" if ok_count == total else "FAIL"
        except Exception as e:
            _exc = e
            self.logger.error("Task '{}' failed: {}".format(task["name"], e))
        with self._ud_lock:
            if idx < len(self._ud.tasks):
                self._ud.tasks[idx]["last_run"]    = \
                    datetime.now().strftime("%Y-%m-%d %H:%M")
                self._ud.tasks[idx]["last_status"] = status
        self._ud.save()

        exc_ref = _exc

        def _update():
            self._refresh_tasks_tree()
            if panel:
                try:
                    panel["stop_btn"].configure(state="disabled")
                    failed_steps = [r for r in results if not r.get("ok")]
                    if failed_steps:
                        panel["step_lbl"].configure(
                            text="⚠ {}/{} step berhasil — {} gagal".format(
                                ok_count, total, len(failed_steps)), text_color=RED)
                        # Add summary of failures to log box
                        lb = panel["log_box"]
                        lb.configure(state="normal")
                        lb.insert(tk.END, "\n─── Step Gagal ───\n", "info")
                        for r in failed_steps:
                            lb.insert(tk.END,
                                "Step {}: [{}] {}\n".format(
                                    r.get("step", 0)+1,
                                    r.get("type","?"),
                                    str(r.get("result",""))[:100]),
                                "fail")
                        lb.see(tk.END)
                        lb.configure(state="disabled")
                        # Keep panel open longer on failure
                        panel["window"].after(
                            8000,
                            lambda: panel["window"].destroy()
                            if panel["window"].winfo_exists() else None)
                    else:
                        panel["step_lbl"].configure(
                            text="✓ Done: {}/{} steps OK".format(ok_count, total), text_color=GRN)
                        panel["window"].after(
                            3000,
                            lambda: panel["window"].destroy()
                            if panel["window"].winfo_exists() else None)
                except Exception:
                    pass
            if status == "OK":
                self._toast_success(
                    "✓ '{}' selesai — {}/{} step berhasil.".format(
                        task["name"], ok_count, total))
                self._sv.set("Task '{}' finished OK.".format(task["name"]))
            else:
                # Build specific error detail from failed steps
                failed_steps = [r for r in results if not r.get("ok")]
                if failed_steps:
                    first = failed_steps[0]
                    step_num  = first.get("step", 0) + 1
                    step_type = first.get("type", "?").replace("_", " ")
                    err_msg   = str(first.get("result", ""))[:120]
                    fail_count = len(failed_steps)
                    detail_lines = "\n".join(
                        "Step {}: [{}] {}".format(
                            r.get("step", 0) + 1,
                            r.get("type", "?"),
                            str(r.get("result", ""))[:80])
                        for r in failed_steps[:5]
                    )
                    msg = "Step {}/{} gagal ({}) → {}".format(
                        step_num, total, step_type, err_msg)
                    if fail_count > 1:
                        msg += " (+{} lainnya)".format(fail_count - 1)
                    self._show_toast(
                        msg, kind="error",
                        details="Task: {}\n\nStep yang gagal:\n{}".format(
                            task["name"], detail_lines))
                elif exc_ref:
                    from utils.error_handler import friendly_message
                    self._toast_error(friendly_message(exc_ref), exc_ref)
                else:
                    self._show_toast(
                        "'{}' gagal: {}/{} step OK".format(
                            task["name"], ok_count, total),
                        kind="error")
                self._sv.set("Task '{}': {}/{} steps OK".format(
                    task["name"], ok_count, total))
            self._ud.log(
                "Task: {}".format(task["name"]),
                "{}/{} steps OK".format(ok_count, total),
                ok=(status == "OK"))

        self._root.after(0, _update)

    # ================================================================
    #  Continuous mode — panel + thread
    # ================================================================

    def _show_continuous_progress_panel(self, task: dict, stop_flag) -> dict:
        """Floating progress window for continuous bulk-order confirmation mode."""
        w = ctk.CTkToplevel(self._root)
        w.withdraw()
        w.title("Bulk Order Confirmation")
        w.configure(fg_color=BG)
        w.resizable(False, False)
        w.attributes("-topmost", True)
        w.geometry("400x530")

        # ── Title row ────────────────────────────────────────────────
        title_frame = _ck.Frame(w, fg_color=CARD, padx=12, pady=10)
        title_frame.pack(fill="x")
        _ck.Label(title_frame,
                 text=task.get("name", "Bulk Order Confirmation"), fg_color=CARD, text_color=FG, font=("Segoe UI", 11, "bold")).pack(side="left")
        loop_lbl = _ck.Label(title_frame, text="[● READY]", fg_color=CARD, text_color=GRN, font=("Segoe UI", 9, "bold"))
        loop_lbl.pack(side="right")

        _ck.Frame(w, fg_color=MUT, height=1).pack(fill="x")

        # ── This loop stats ───────────────────────────────────────────
        loop_frame = _ck.Frame(w, fg_color=BG, padx=14, pady=8)
        loop_frame.pack(fill="x")
        _ck.Label(loop_frame, text="This loop:", fg_color=BG, text_color=MUT, font=("Segoe UI", 8, "bold")).pack(anchor="w")

        stats_vars = {
            "checked":    tk.StringVar(value="Checked: 0 orders"),
            "confirmed":  tk.StringVar(value="Confirmed: 0"),
            "skipped":    tk.StringVar(value="Skipped: 0"),
            "mismatches": tk.StringVar(value="Mismatches: 0"),
        }
        _stat_colors = {
            "checked": FG, "confirmed": GRN, "skipped": FG, "mismatches": RED,
        }
        for key, var in stats_vars.items():
            _ck.Label(loop_frame, textvariable=var, fg_color=BG, text_color=_stat_colors[key],
                     font=("Segoe UI", 9)).pack(anchor="w", padx=(10, 0))

        _ck.Frame(w, fg_color=MUT, height=1).pack(fill="x")

        # ── All-time totals ───────────────────────────────────────────
        totals_frame = _ck.Frame(w, fg_color=BG, padx=14, pady=8)
        totals_frame.pack(fill="x")
        _ck.Label(totals_frame, text="All time totals:", fg_color=BG, text_color=MUT, font=("Segoe UI", 8, "bold")).pack(anchor="w")

        totals_vars = {
            "confirmed_total":   tk.StringVar(value="Confirmed: 0 orders"),
            "mismatches_total":  tk.StringVar(value="Mismatches: 0"),
            "unverified_total":  tk.StringVar(value="Unverified on web: 0"),
        }
        _tot_colors = {
            "confirmed_total": GRN, "mismatches_total": RED, "unverified_total": YEL,
        }
        for key, var in totals_vars.items():
            _ck.Label(totals_frame, textvariable=var, fg_color=BG, text_color=_tot_colors[key],
                     font=("Segoe UI", 9)).pack(anchor="w", padx=(10, 0))

        _ck.Frame(w, fg_color=MUT, height=1).pack(fill="x")

        # ── Live log ──────────────────────────────────────────────────
        log_frame = _ck.Frame(w, fg_color=BG)
        log_frame.pack(fill="both", expand=True, padx=14, pady=(6, 0))
        log_box = _ck.ScrolledText(
            log_frame, fg_color=CARD, text_color=FG, font=("Consolas", 7),
            relief="flat", height=6, state="disabled")
        log_box.pack(fill="both", expand=True)
        log_box.tag_configure("ok",   foreground=GRN)
        log_box.tag_configure("warn", foreground=YEL)
        log_box.tag_configure("fail", foreground=RED)
        log_box.tag_configure("info", foreground=MUT)

        _ck.Frame(w, fg_color=MUT, height=1).pack(fill="x")

        # ── Countdown + buttons ───────────────────────────────────────
        bottom = _ck.Frame(w, fg_color=BG, padx=14, pady=10)
        bottom.pack(fill="x")

        countdown_var = tk.StringVar(value="")
        _ck.Label(bottom, textvariable=countdown_var, fg_color=BG, text_color=ACC, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))

        btn_row = _ck.Frame(bottom, fg_color=BG)
        btn_row.pack(fill="x")

        def _stop():
            stop_flag.set()
            stop_btn.configure(state="disabled", text="Stopping...")

        def _export():
            date_str = datetime.now().strftime("%Y-%m-%d")
            csv_path = os.path.join(_ROOT, "data",
                                    "confirmation_report_{}.csv".format(date_str))
            if os.path.exists(csv_path):
                self._show_alert("Export Report",
                                 "Report saved at:\n{}".format(csv_path))
            else:
                self._show_alert("Export Report", "No report data yet for today.")

        stop_btn = _ck.Button(btn_row, text="STOP", fg_color=RED, text_color=BG,
                             font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                             padx=12, pady=5, cursor="hand2", command=_stop)
        stop_btn.pack(side="left", padx=(0, 8))

        _ck.Button(btn_row, text="Export Report", fg_color=CARD, text_color=FG,
                  font=("Segoe UI", 9), relief="flat", bd=0,
                  padx=12, pady=5, cursor="hand2",
                  command=_export).pack(side="left")

        w.update()
        w.deiconify()
        return {
            "window":        w,
            "loop_lbl":      loop_lbl,
            "stats_vars":    stats_vars,
            "totals_vars":   totals_vars,
            "log_box":       log_box,
            "countdown_var": countdown_var,
            "stop_btn":      stop_btn,
        }

    def _run_continuous_task_thread(self, task, idx, stop_flag=None, panel=None):
        """Background thread for continuous mode task execution."""
        self._root.after(0, lambda: self._sv.set(
            "Running: {} [CONTINUOUS]...".format(task["name"])))
        with self._ud_lock:
            if idx < len(self._ud.tasks):
                self._ud.tasks[idx]["last_status"] = "Running"
        self._root.after(0, self._refresh_tasks_tree)

        def _log(msg, tag="info"):
            if not panel:
                return
            def _upd(m=msg, t=tag):
                try:
                    lb = panel["log_box"]
                    lb.configure(state="normal")
                    lb.insert(tk.END, m + "\n", t)
                    lb.see(tk.END)
                    lb.configure(state="disabled")
                except Exception:
                    pass
            self._root.after(0, _upd)

        def _loop_cb(state):
            phase     = state.get("phase", "")
            loop      = state.get("loop", 0)
            stats     = state.get("stats", {})
            all_time  = state.get("all_time", {})
            remaining = state.get("remaining", 0)

            def _upd():
                if not panel:
                    return
                try:
                    win = panel["window"]
                    if not win.winfo_exists():
                        return
                except Exception:
                    return

                try:
                    sv = panel["stats_vars"]
                    tv = panel["totals_vars"]

                    if phase == "start":
                        panel["loop_lbl"].configure(
                            text="[● RUNNING] Loop #{}".format(loop), text_color=GRN)
                        sv["checked"].set("Checked: 0 orders")
                        sv["confirmed"].set("Confirmed: 0")
                        sv["skipped"].set("Skipped: 0")
                        sv["mismatches"].set("Mismatches: 0")
                        panel["countdown_var"].set("")
                        _log("Loop #{} started".format(loop), "info")

                    elif phase == "end":
                        checked   = stats.get("checked", 0)
                        confirmed = stats.get("confirmed", 0)
                        skipped   = stats.get("skipped", 0)
                        mismatches = stats.get("mismatches", 0)
                        not_found = stats.get("not_found", 0)

                        sv["checked"].set("Checked: {} orders".format(checked))
                        sv["confirmed"].set("Confirmed: {}".format(confirmed))
                        sv["skipped"].set("Skipped: {}".format(skipped))
                        sv["mismatches"].set("Mismatches: {}".format(mismatches))

                        tv["confirmed_total"].set(
                            "Confirmed: {} orders".format(all_time.get("confirmed", 0)))
                        tv["mismatches_total"].set(
                            "Mismatches: {}".format(all_time.get("mismatches", 0)))
                        tv["unverified_total"].set(
                            "Unverified on web: {}".format(
                                all_time.get("unverified_on_web", 0)))

                        if checked == 0:
                            _log("No pending orders. Checking again soon...", "info")
                        else:
                            tag = "ok" if confirmed > 0 else "info"
                            _log(
                                "Loop #{}: Confirmed {}, Skipped {}, "
                                "Mismatches {}, Not found {}".format(
                                    loop, confirmed, skipped, mismatches, not_found),
                                tag)

                    elif phase == "countdown":
                        panel["countdown_var"].set(
                            "Next check in: {}s...".format(remaining))
                        panel["loop_lbl"].configure(
                            text="[◷ WAITING] Loop #{}".format(loop), text_color=MUT)

                except Exception:
                    pass

            self._root.after(0, _upd)

        try:
            if self.engine:
                self.engine.run_continuous_task(
                    task, loop_cb=_loop_cb, stop_flag=stop_flag)
        except Exception as e:
            self.logger.error(
                "Continuous task '{}' failed: {}".format(task["name"], e))
            _log("Fatal error: {}".format(e), "fail")

        with self._ud_lock:
            if idx < len(self._ud.tasks):
                self._ud.tasks[idx]["last_status"] = "Stopped"
                self._ud.tasks[idx]["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._ud.save()

        def _done():
            self._refresh_tasks_tree()
            if panel:
                try:
                    panel["stop_btn"].configure(state="disabled", text="Stopped")
                    panel["loop_lbl"].configure(
                        text="[■ STOPPED]", text_color=MUT)
                    panel["countdown_var"].set("Continuous mode stopped.")
                except Exception:
                    pass
            self._sv.set("Task '{}' stopped.".format(task["name"]))
            self._ud.log(
                "Task: {} [continuous]".format(task["name"]),
                "Continuous mode stopped",
                ok=True)

        self._root.after(0, _done)

    def _delete_selected_task(self):
        if not self._tasks_tree:
            return
        sel = self._tasks_tree.selection()
        if not sel:
            return
        idx = self._tasks_tree.index(sel[0])
        if idx >= len(self._ud.tasks):
            return
        name = self._ud.tasks[idx].get("name","")
        if self._confirm_dialog(
                "Hapus Macro?",
                "Hapus macro '{}'?\nAksi ini tidak bisa dibatalkan.".format(name),
                confirm_text="Ya, Hapus", accent=RED):
            with self._ud_lock:
                if idx < len(self._ud.tasks):
                    task_id = self._ud.tasks[idx].get("id", "")
                    if task_id and self.engine and self.engine.scheduler:
                        try:
                            self.engine.scheduler.remove_job("task_{}".format(task_id))
                        except Exception:
                            pass
                    del self._ud.tasks[idx]
            self._ud.save()
            self._refresh_tasks_tree()

    def _toggle_task_enabled(self):
        if not self._tasks_tree:
            return
        sel = self._tasks_tree.selection()
        if not sel:
            return
        idx = self._tasks_tree.index(sel[0])
        if idx >= len(self._ud.tasks):
            return
        with self._ud_lock:
            if idx < len(self._ud.tasks):
                self._ud.tasks[idx]["enabled"] = not self._ud.tasks[idx].get(
                    "enabled", True)
                task_ref = self._ud.tasks[idx]
            else:
                return
        self._ud.save()
        if self.engine:
            self.engine.register_task(task_ref)
        self._refresh_tasks_tree()

    # ================================================================
    #  Toast notification
    # ================================================================

    def _show_toast(self, message, kind="info", details=None,
                    duration: int = 0, action=None):
        """Animated slide-in toast — bottom-right, stacking, progress bar countdown.
        duration: override ms (0 = auto by kind). action: callable on click."""
        import textwrap, math

        try:
            if not self._root or not self._root.winfo_exists():
                return

            # ── palette ──────────────────────────────────────────────────
            _kind_map = {
                "success": (GRN,  "#1A2E22"),
                "warning": (YEL,  "#2A2010"),
                "error":   (RED,  "#2A1010"),
                "info":    (ACC,  CARD2),
            }
            stripe_col, card_col = _kind_map.get(kind, _kind_map["info"])

            # ── PIL icon ──────────────────────────────────────────────────
            def _make_icon(col, kind_):
                s = 20
                img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
                d = ImageDraw.Draw(img)
                m = s // 2
                if kind_ == "success":
                    d.ellipse([1, 1, s-2, s-2], fill=col)
                    d.line([(5, m), (8, m+4), (15, m-4)], fill="#0A1A10", width=2)
                elif kind_ == "warning":
                    d.polygon([(m, 2), (s-3, s-3), (3, s-3)], fill=col)
                    d.text((m-2, m-3), "!", fill="#1A1000",
                           font=None)
                    d.rectangle([m-1, 8, m+1, 13], fill="#1A1000")
                    d.rectangle([m-1, 15, m+1, 17], fill="#1A1000")
                elif kind_ == "error":
                    d.ellipse([1, 1, s-2, s-2], fill=col)
                    d.line([(6, 6), (14, 14)], fill="#1A0000", width=2)
                    d.line([(14, 6), (6, 14)], fill="#1A0000", width=2)
                else:
                    d.ellipse([1, 1, s-2, s-2], fill=col)
                    d.rectangle([m-1, 8, m+1, 9], fill="#0A0A1A")
                    d.rectangle([m-1, 11, m+1, 16], fill="#0A0A1A")
                return img
            icon_img = _make_icon(stripe_col, kind)

            # ── window ───────────────────────────────────────────────────
            TOAST_W = 320
            w = ctk.CTkToplevel(self._root)
            w.attributes("-topmost", True)
            w.attributes("-alpha", 0.0)
            w.configure(fg_color=card_col)

            # outer frame with border effect
            outer = _ck.Frame(w, fg_color=stripe_col, bd=0)
            outer.pack(fill="both", expand=True)

            inner = _ck.Frame(outer, fg_color=card_col, bd=0)
            inner.pack(fill="both", expand=True, padx=(3, 0))  # 3px left stripe

            # top row: icon + message + close btn
            top = _ck.Frame(inner, fg_color=card_col)
            top.pack(fill="x", padx=(10, 8), pady=(10, 4))

            photo = ImageTk.PhotoImage(icon_img)
            w._icon_photo = photo  # prevent GC
            _ck.Label(top, image=photo, fg_color=card_col).pack(side="left", padx=(0, 8))

            import textwrap
            wrapped = "\n".join(textwrap.wrap(message[:220], width=42))
            _ck.Label(top, text=wrapped, fg_color=card_col, text_color=FG,
                     font=("Segoe UI", 9), justify="left",
                     wraplength=230).pack(side="left", fill="x", expand=True, anchor="w")

            def _dismiss():
                _toast_close(w)

            close_btn = _ck.Label(top, text="✕", fg_color=card_col, text_color=MUT,
                                 font=("Segoe UI", 9), cursor="hand2")
            close_btn.pack(side="right", anchor="n", padx=(4, 0))
            close_btn.bind("<Button-1>", lambda e: _dismiss())
            close_btn.bind("<Enter>", lambda e: close_btn.configure(text_color=FG))
            close_btn.bind("<Leave>", lambda e: close_btn.configure(text_color=MUT))

            # details row
            if details:
                _det = details
                def _show_det():
                    dw = ctk.CTkToplevel(self._root)
                    dw.withdraw()
                    dw.title("Error Details")
                    dw.configure(fg_color=BG)
                    dw.geometry("600x320")
                    st = _ck.ScrolledText(dw, fg_color=CARD, text_color=MUT,
                                                   font=("Consolas", 9), relief="flat")
                    st.pack(fill="both", expand=True, padx=12, pady=12)
                    st.insert(tk.END, _det)
                    st.configure(state="disabled")
                    _ck.Button(dw, text="Close", command=dw.destroy).pack(pady=(0, 10))
                    dw.update()
                    dw.deiconify()
                det_row = _ck.Frame(inner, fg_color=card_col)
                det_row.pack(fill="x", padx=12, pady=(0, 6))
                _ck.Label(det_row, text="Lihat Detail →", fg_color=card_col, text_color=stripe_col, font=("Segoe UI", 8), cursor="hand2").pack(
                    side="left").bind("<Button-1>", lambda e: _show_det())

            # action: make message clickable
            if action:
                for w_ in (top,):
                    w_.configure(cursor="hand2")
                    w_.bind("<Button-1>", lambda e: (_toast_close(w), action()))

            # progress bar canvas
            dur_ms  = duration if duration > 0 else (6000 if kind == "error" else 4000)
            bar_h   = 3
            pb = tk.Canvas(inner, bg=card_col, height=bar_h,
                           highlightthickness=0, bd=0)
            pb.pack(fill="x")
            pb_bar = pb.create_rectangle(0, 0, TOAST_W, bar_h, fill=stripe_col, width=0)

            # ── position ─────────────────────────────────────────────────
            w.update_idletasks()
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            wh = w.winfo_reqheight()

            # clean up dead toasts from stack
            self._toasts = [t for t in self._toasts if t.winfo_exists()]

            # stack above previous toasts
            stack_offset = sum(
                t.winfo_height() + 8
                for t in self._toasts
                if t.winfo_exists()
            )
            base_y = sh - wh - 52 - stack_offset
            final_x = sw - TOAST_W - 16
            start_x = sw + 10  # starts off-screen right

            w.geometry("{}x{}+{}+{}".format(TOAST_W, wh, start_x, base_y))
            self._toasts.append(w)

            # ── helpers ───────────────────────────────────────────────────
            _closed = [False]

            def _toast_close(win):
                if _closed[0]: return
                _closed[0] = True
                def _fade(step=0):
                    if not win.winfo_exists(): return
                    a = max(0.0, 1.0 - step / 8)
                    win.attributes("-alpha", a)
                    if step < 8:
                        win.after(18, _fade, step + 1)
                    else:
                        try: win.destroy()
                        except Exception: pass
                        if win in self._toasts:
                            self._toasts.remove(win)
                _fade()

            # slide-in animation
            def _slide_in(step=0):
                if not w.winfo_exists(): return
                total = 10
                ratio = 1 - (1 - step / total) ** 2  # ease-out
                x = int(start_x + (final_x - start_x) * ratio)
                w.geometry("{}x{}+{}+{}".format(TOAST_W, wh, x, base_y))
                w.attributes("-alpha", min(1.0, step / total * 1.2))
                if step < total:
                    w.after(16, _slide_in, step + 1)
                else:
                    w.attributes("-alpha", 1.0)
                    w.geometry("{}x{}+{}+{}".format(TOAST_W, wh, final_x, base_y))

            # progress bar countdown
            _tick_ms  = 40
            _ticks    = dur_ms // _tick_ms

            def _progress(tick=0):
                if _closed[0] or not w.winfo_exists(): return
                ratio = 1 - tick / _ticks
                bar_w = max(0, int(TOAST_W * ratio))
                pb.coords(pb_bar, 0, 0, bar_w, bar_h)
                if tick < _ticks:
                    w.after(_tick_ms, _progress, tick + 1)
                else:
                    _toast_close(w)

            w.after(20, _slide_in)
            w.after(60, _progress)

        except Exception:
            pass

    def _toast_error(self, friendly_msg, exc=None):
        """Show a red error toast. Pass the original exception for 'Show Details'."""
        from utils.error_handler import full_details
        details = full_details(exc) if exc else None
        self._show_toast(friendly_msg, kind="error", details=details)

    def _toast_success(self, message):
        """Show a green success toast."""
        self._show_toast(message, kind="success")

    def _toast_warning(self, message):
        """Show a yellow warning toast."""
        self._show_toast(message, kind="warning")

    # ================================================================
    #  Logout / tray / hotkey / quit
    # ================================================================

    def _confirm_dialog(self, title, message, confirm_text="Ya",
                        cancel_text="Batal", accent=None):
        """Custom dark-theme confirmation dialog. Returns True if confirmed."""
        accent = accent or RED
        result = tk.BooleanVar(value=False)

        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()  # hide until fully built
        dlg.title("")
        dlg.resizable(False, False)
        dlg.configure(fg_color="#0D0D14")
        dlg.attributes("-topmost", True)

        W, H = 380, 200
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        dlg.geometry("{}x{}+{}+{}".format(W, H, (sw - W) // 2, (sh - H) // 2))

        _ck.Frame(dlg, fg_color=accent, bd=0).place(x=0, y=0, width=W, height=3)
        _ck.Label(dlg, text=title, fg_color="#0D0D14", text_color=FG,
                 font=("Segoe UI", 13, "bold")).pack(pady=(24, 0))
        _ck.Label(dlg, text=message, fg_color="#0D0D14", text_color=MUT,
                 font=("Segoe UI", 9), justify="center",
                 wraplength=330).pack(pady=(8, 14))
        _ck.Frame(dlg, fg_color=CARD, height=1).pack(fill="x", padx=24)

        btn_row = _ck.Frame(dlg, fg_color="#0D0D14")
        btn_row.pack(pady=14)

        def _yes():
            result.set(True)
            dlg.destroy()

        _ck.Button(btn_row, text="  {}  ".format(confirm_text), fg_color=accent, text_color="white",
                  relief="flat", font=("Segoe UI", 10, "bold"),
                  cursor="hand2", command=_yes).pack(side="left", padx=(0, 8))
        _ck.Button(btn_row, text="  {}  ".format(cancel_text), fg_color=CARD2, text_color=FG,
                  relief="flat", font=("Segoe UI", 10),
                  cursor="hand2", command=dlg.destroy).pack(side="left")

        dlg.update()
        dlg.deiconify()
        dlg.grab_set()
        dlg.focus_force()
        dlg.wait_window(dlg)
        return result.get()

    def _show_force_download_dialog(self, tag: str, url: str):
        """Paksa update seperti game — tidak bisa di-close, download in-app, restart otomatis."""
        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Synthex — Update Tersedia")
        dlg.configure(fg_color="#0D0D14")
        dlg.resizable(False, False)
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)  # disable X button
        dlg.attributes("-topmost", True)
        dlg.update()
        dlg.grab_set()
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry("480x300+{}+{}".format((sw - 480) // 2, (sh - 300) // 2))

        # Set ikon Synthex di title bar dialog
        try:
            _ico = _resolve_icon()
            if _ico:
                dlg.iconbitmap(_ico)
        except Exception:
            pass

        _ck.Frame(dlg, fg_color=ACC, height=4).pack(fill="x")
        bd = _ck.Frame(dlg, fg_color="#0D0D14", padx=28, pady=20)
        bd.pack(fill="both", expand=True)

        # Header: logo PIL + judul
        hdr = _ck.Frame(bd, fg_color="#0D0D14")
        hdr.pack(fill="x", anchor="w", pady=(0, 12))
        try:
            from ui.icons import generate_all_icons
            _ico_img = generate_all_icons(28, (108, 74, 255), keys=["settings"])["settings"]
            _ico_ph  = ImageTk.PhotoImage(_ico_img)
            dlg._ico_ph = _ico_ph  # prevent GC
            _ck.Label(hdr, image=_ico_ph, fg_color="#0D0D14").pack(side="left", padx=(0, 10))
        except Exception:
            pass
        title_wrap = _ck.Frame(hdr, fg_color="#0D0D14")
        title_wrap.pack(side="left")
        _ck.Label(title_wrap, text="Synthex  {}  Tersedia".format(tag), fg_color="#0D0D14", text_color=ACC, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        _ck.Label(title_wrap,
                 text="Versi kamu: v{}  →  {}".format(
                     self.config.get("app.version", "?"), tag), fg_color="#0D0D14", text_color=MUT, font=("Segoe UI", 8)).pack(anchor="w")

        _ck.Label(bd, text="Update wajib diinstal sebelum melanjutkan.\nSynthex akan restart otomatis setelah selesai.", fg_color="#0D0D14", text_color=FG, font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(0, 14))

        status_var = tk.StringVar(value="Siap mengunduh…")
        _ck.Label(bd, textvariable=status_var, fg_color="#0D0D14", text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w")

        bar = ttk.Progressbar(bd, mode="determinate", length=400, maximum=100)
        bar.pack(anchor="w", pady=(4, 12))

        btn = _ck.Button(bd, text="⬇  Download & Install Sekarang", fg_color=ACC, text_color="white", font=("Segoe UI", 10, "bold"),
                        relief="flat", bd=0, padx=18, pady=8, cursor="hand2")
        btn.pack(anchor="w")

        def _start_download():
            btn.configure(state="disabled", text="Mengunduh…")
            status_var.set("Mengunduh {}…".format(tag))

            def _prog(ratio):
                if dlg.winfo_exists():
                    dlg.after(0, lambda r=ratio: bar.configure(value=int(r * 100)))

            def _bg():
                from modules.updater import download_and_replace
                ok = download_and_replace(url, progress_cb=_prog)
                if dlg.winfo_exists():
                    if ok:
                        dlg.after(0, lambda: status_var.set("✓ Selesai! Restart dalam 2 detik…"))
                        dlg.after(0, lambda: bar.configure(value=100))
                        dlg.after(2000, self._root.destroy)
                    else:
                        dlg.after(0, lambda: status_var.set("Gagal. Coba lagi atau cek koneksi."))
                        dlg.after(0, lambda: btn.configure(
                            state="normal", text="⬇  Coba Lagi"))

            threading.Thread(target=_bg, daemon=True).start()

        btn.configure(command=_start_download)
        dlg.update()
        dlg.deiconify()
        dlg.focus_force()

    def _show_force_update_dialog(self, min_ver: str):
        """Blocking dialog: user must update, cannot dismiss."""
        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Update Diperlukan")
        dlg.configure(fg_color="#0D0D14")
        dlg.resizable(False, False)
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)  # disable close
        dlg.attributes("-topmost", True)
        dlg.update()
        dlg.grab_set()
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry("440x260+{}+{}".format((sw-440)//2, (sh-260)//2))
        _ck.Frame(dlg, fg_color=RED, height=4).pack(fill="x")
        bd = _ck.Frame(dlg, fg_color="#0D0D14", padx=28, pady=24)
        bd.pack(fill="both", expand=True)
        _ck.Label(bd, text="⚠ Update Wajib", fg_color="#0D0D14", text_color=RED,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        _ck.Label(bd, text="Versi minimum yang diizinkan: v{}".format(min_ver), fg_color="#0D0D14", text_color=FG, font=("Segoe UI", 10)).pack(anchor="w", pady=(8,0))
        _ck.Label(bd, text="Versi kamu saat ini terlalu lama dan tidak bisa digunakan.\n"
                          "Download versi terbaru dari GitHub untuk melanjutkan.", fg_color="#0D0D14", text_color=MUT, font=("Segoe UI", 9), justify="left").pack(
            anchor="w", pady=(6,16))
        def _open_gh():
            import webbrowser
            webbrowser.open("https://github.com/Yohn18/synthex-releases/releases/latest")
        _ck.Button(bd, text="⬇ Download Update", fg_color=ACC, text_color="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", bd=0, padx=18, pady=8, cursor="hand2",
                  command=_open_gh).pack(anchor="w")
        dlg.update()
        dlg.deiconify()

    def _show_changelog_popup(self, cl: dict):
        """Show release notes popup (dismissable)."""
        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Yang Baru di v{}".format(cl.get("version","")))
        dlg.configure(fg_color="#0D0D14")
        dlg.resizable(True, False)
        dlg.attributes("-topmost", True)
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry("480x380+{}+{}".format((sw-480)//2, (sh-380)//2))
        _ck.Frame(dlg, fg_color=GRN, height=4).pack(fill="x")
        bd = _ck.Frame(dlg, fg_color="#0D0D14", padx=24, pady=20)
        bd.pack(fill="both", expand=True)
        _ck.Label(bd, text="🎉 Update v{}".format(cl.get("version","")), fg_color="#0D0D14", text_color=GRN,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        _ck.Label(bd, text="Berikut perubahan terbaru:", fg_color="#0D0D14", text_color=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(4,8))
        txt = _ck.ScrolledText(bd, fg_color=CARD, text_color=FG, relief="flat",
                                        font=("Segoe UI", 9), height=10, wrap="word",
                                        state="normal")
        txt.insert("1.0", cl.get("notes",""))
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)
        _ck.Button(bd, text="Mengerti, Lanjutkan", fg_color=ACC, text_color="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", bd=0, padx=18, pady=8, cursor="hand2",
                  command=dlg.destroy).pack(anchor="e", pady=(12,0))
        dlg.update()
        dlg.deiconify()
        dlg.grab_set()

    def _show_dm_popup(self, msgs: list, my_email: str, token: str):
        """Show unread DM messages from master."""
        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Pesan dari Master")
        dlg.configure(fg_color="#0D0D14")
        dlg.resizable(True, False)
        dlg.attributes("-topmost", True)
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry("460x320+{}+{}".format((sw-460)//2, (sh-320)//2))
        _ck.Frame(dlg, fg_color="#7C3AED", height=4).pack(fill="x")
        bd = _ck.Frame(dlg, fg_color="#0D0D14", padx=24, pady=18)
        bd.pack(fill="both", expand=True)
        _ck.Label(bd, text="📬 {} Pesan Baru dari Admin".format(len(msgs)), fg_color="#0D0D14", text_color=ACC, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        from datetime import datetime as _dt2
        msg_frame = _ck.Frame(bd, fg_color=CARD)
        msg_frame.pack(fill="both", expand=True, pady=(10,0))
        for m in msgs:
            ts = m.get("ts", 0)
            try: t_str = _dt2.fromtimestamp(ts).strftime("%d %b %Y  %H:%M")
            except Exception: t_str = ""
            mf = _ck.Frame(msg_frame, fg_color=CARD, padx=12, pady=8)
            mf.pack(fill="x")
            _ck.Frame(msg_frame, fg_color="#1c1c2e", height=1).pack(fill="x")
            _ck.Label(mf, text=t_str, fg_color=CARD, text_color=MUT,
                     font=("Segoe UI", 7)).pack(anchor="w")
            _ck.Label(mf, text=m.get("message",""), fg_color=CARD, text_color=FG,
                     font=("Segoe UI", 9), wraplength=380, justify="left").pack(anchor="w")
        def _close():
            from modules.master_config import mark_dm_read
            for m in msgs:
                threading.Thread(
                    target=lambda k=m.get("_key",""):
                        mark_dm_read(my_email, k, token),
                    daemon=True).start()
            dlg.destroy()
        _ck.Button(bd, text="Tandai Sudah Dibaca", fg_color=ACC, text_color="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", bd=0, padx=18, pady=8, cursor="hand2",
                  command=_close).pack(anchor="e", pady=(12,0))
        dlg.update()
        dlg.deiconify()
        dlg.grab_set()

    def _show_alert(self, title, message, kind="info"):
        """Custom dark-theme alert dialog (info / warning). kind='info'|'warning'|'error'."""
        accent = {
            "warning": YEL,
            "error":   RED,
        }.get(kind, ACC)

        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("")
        dlg.resizable(False, False)
        dlg.configure(fg_color="#0D0D14")
        dlg.attributes("-topmost", True)

        W, H = 380, 180
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        dlg.geometry("{}x{}+{}+{}".format(W, H, (sw - W) // 2, (sh - H) // 2))

        _ck.Frame(dlg, fg_color=accent, bd=0).place(x=0, y=0, width=W, height=3)
        _ck.Label(dlg, text=title, fg_color="#0D0D14", text_color=FG,
                 font=("Segoe UI", 13, "bold")).pack(pady=(24, 0))
        _ck.Label(dlg, text=message, fg_color="#0D0D14", text_color=MUT,
                 font=("Segoe UI", 9), justify="center",
                 wraplength=330).pack(pady=(8, 14))
        _ck.Frame(dlg, fg_color=CARD, height=1).pack(fill="x", padx=24)
        _ck.Button(dlg, text="  OK  ", fg_color=accent, text_color="white",
                  relief="flat", font=("Segoe UI", 10, "bold"),
                  cursor="hand2", padx=12, pady=6,
                  command=dlg.destroy).pack(pady=14)

        dlg.update()
        dlg.deiconify()

        dlg.grab_set()
        dlg.focus_force()
        dlg.wait_window(dlg)

    def _ask_input(self, title, prompt, initial=""):
        """Custom dark-theme single-line input dialog. Returns string or None if cancelled."""
        result = [None]

        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("")
        dlg.resizable(False, False)
        dlg.configure(fg_color="#0D0D14")
        dlg.attributes("-topmost", True)

        W, H = 400, 210
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        dlg.geometry("{}x{}+{}+{}".format(W, H, (sw - W) // 2, (sh - H) // 2))

        _ck.Frame(dlg, fg_color=ACC, bd=0).place(x=0, y=0, width=W, height=3)
        _ck.Label(dlg, text=title, fg_color="#0D0D14", text_color=FG,
                 font=("Segoe UI", 13, "bold")).pack(pady=(24, 0))
        _ck.Label(dlg, text=prompt, fg_color="#0D0D14", text_color=MUT,
                 font=("Segoe UI", 9)).pack(pady=(6, 4))
        entry = _ck.Entry(dlg, fg_color=CARD2, text_color=FG, insertbackground=FG,
                         relief="flat", font=("Segoe UI", 10),
                         width=32, bd=6)
        entry.insert(0, initial)
        entry.pack(padx=24)
        entry.focus_set()

        _ck.Frame(dlg, fg_color=CARD, height=1).pack(fill="x", padx=24, pady=(12, 0))
        btn_row = _ck.Frame(dlg, fg_color="#0D0D14")
        btn_row.pack(pady=12)

        def _ok():
            result[0] = entry.get()
            dlg.destroy()

        entry.bind("<Return>", lambda e: _ok())
        entry.bind("<Escape>", lambda e: dlg.destroy())

        _ck.Button(btn_row, text="  OK  ", fg_color=ACC, text_color="white",
                  relief="flat", font=("Segoe UI", 10, "bold"),
                  cursor="hand2", padx=12, pady=6,
                  command=_ok).pack(side="left", padx=(0, 8))
        _ck.Button(btn_row, text="  Batal  ", fg_color=CARD2, text_color=FG,
                  relief="flat", font=("Segoe UI", 10),
                  cursor="hand2", padx=12, pady=6,
                  command=dlg.destroy).pack(side="left")

        dlg.update()
        dlg.deiconify()

        dlg.grab_set()
        dlg.wait_window(dlg)
        return result[0]

    def _logout(self):
        import os
        if not self._confirm_dialog(
                "Logout dari Synthex?",
                "Sesi kamu akan dihapus.\nKamu perlu login ulang saat membuka aplikasi.",
                confirm_text="Ya, Logout", cancel_text="Batal",
                accent=YEL):
            return
        # Set presence offline before logout
        try:
            from modules.chat import update_presence
            from auth.firebase_auth import get_valid_token
            _tok = get_valid_token()
            if _tok and self._email:
                update_presence(self._email, _tok, online=False)
        except Exception:
            pass
        # Clear RTDB session so another device can login cleanly
        from auth.firebase_auth import logout as _fa_logout
        try:
            _fa_logout()
        except Exception:
            pass
        # Clear token files (both legacy .json and new .enc)
        _appdata = os.environ.get("APPDATA", "")
        for _tname in ("token.enc", "token.json"):
            _tp = os.path.join(_appdata, "Synthex", _tname)
            if os.path.exists(_tp):
                try:
                    os.remove(_tp)
                except Exception:
                    pass
        # Clear stay-logged-in config
        self.config.set("ui.stay_logged_in", False)
        self.config.set("ui.last_email", "")
        self.config.save()
        # Stop tray, destroy window, exit process
        if self._tray:
            try: self._tray.stop()
            except Exception: pass
        if self._hkl:
            try: self._hkl.stop()
            except Exception: pass
        try: self._root.destroy()
        except Exception: pass
        import os as _os; _os._exit(0)

    def _start_tray(self):
        def _run():
            ico_path = _resolve_icon()
            if ico_path:
                try:
                    img = Image.open(ico_path).convert("RGBA").resize((64, 64))
                except Exception:
                    ico_path = None
            if not ico_path:
                img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                ImageDraw.Draw(img).ellipse([4, 4, 60, 60], fill=ACC)
            self._tray = pystray.Icon("synthex", img, "Synthex ⚡",
                pystray.Menu(
                    pystray.MenuItem(
                        "Show",
                        lambda *_: (self._root.after(0, self._root.deiconify)
                                    if self._root else None),
                        default=True),
                    pystray.MenuItem("Exit", lambda *_: self._quit())))
            self._tray.run()
        threading.Thread(target=_run, daemon=True).start()

    def _setup_hotkey(self):
        """Single keyboard listener: handles CTRL+1/CTRL+3 hotkeys AND routes
        key events to SimpleRecorder when recording is active.
        Using one listener prevents the two-listener C-level crash on Windows."""
        try:
            from pynput import keyboard as _kb

            _ctrl = [False]

            def _on_press(key):
                # Track CTRL state
                try:
                    if key in (_kb.Key.ctrl_l, _kb.Key.ctrl_r, _kb.Key.ctrl):
                        _ctrl[0] = True
                except Exception:
                    pass

                if _ctrl[0]:
                    # Detect CTRL+1 (VK 0x31) and CTRL+3 (VK 0x33)
                    vk = getattr(key, 'vk', None)
                    ch = None
                    try:
                        ch = key.char
                    except Exception:
                        pass
                    if vk == 0x31 or ch in ('1', '\x01'):
                        if self._root:
                            self._root.after(0, self._hk_play_pause)
                        return
                    if vk == 0x33 or ch in ('3', '\x03'):
                        self.logger.info("HK: CTRL+3 detected vk=%s ch=%r rec=%s fn=%s",
                            vk, ch, self._rec, self._rec_toggle_fn is not None)
                        if self._root:
                            self._root.after(0, self._hk_record_toggle)
                        return

                # Route to SimpleRecorder when recording is active
                if self._rec and self._simple_recorder:
                    try:
                        self._simple_recorder._on_key_press(key)
                    except Exception:
                        pass

            def _on_release(key):
                try:
                    if key in (_kb.Key.ctrl_l, _kb.Key.ctrl_r, _kb.Key.ctrl):
                        _ctrl[0] = False
                except Exception:
                    pass

            self._hkl = _kb.Listener(
                on_press=_on_press,
                on_release=_on_release,
                suppress=False,
                daemon=True,
            )
            self._hkl.start()
            self.logger.info("Hotkey listener started OK")
        except Exception as _e:
            self.logger.error("Hotkey setup failed: %s", _e)

    # -- Hotkey actions --

    def _hk_play_pause(self):
        """Ctrl+1: Pause/resume recording when recorder active, else play/pause playback."""
        if self._step_editor_open:
            return

        # Priority 1: recorder sedang aktif → pause/resume rekaman via toolbar fn
        if self._rec:
            if self._rec_pause_fn:
                self._rec_pause_fn()
            return

        # Priority 2: playback sedang berjalan → pause/resume playback
        if self._playback_running and self._playback_pause.is_set():
            self._playback_pause.clear()
            self._show_toast("Dilanjutkan", kind="info")
        elif self._playback_running:
            self._playback_pause.set()
            self._show_toast("Dijeda", kind="info")
        # Jika tidak ada recording/playback aktif → tidak melakukan apapun

    def _hk_play_smart(self, rec, idx):
        """Start smart recording playback (used by Ctrl+1 hotkey)."""
        steps = rec.get("steps", [])
        if not steps:
            return
        engine_steps = [
            {"type":  _STEP_TO_ENGINE.get(s.get("type", ""), s.get("type", "")),
             "value": s.get("value", "")}
            for s in steps
        ]
        self._playback_stop.clear()
        self._playback_pause.clear()
        self._playback_running = True
        total      = len(engine_steps)
        start_time = time.time()
        win        = self._show_playback_window(total, rec.get("name", ""))

        def on_step(i, ok, msg):
            if self._playback_stop.is_set():
                raise RuntimeError("Playback stopped by user.")
            while self._playback_pause.is_set():
                if self._playback_stop.is_set():
                    raise RuntimeError("Playback stopped by user.")
                time.sleep(0.05)
            self._root.after(
                0, lambda: self._update_playback_window(win, i + 1, total, msg))

        def _run():
            ok_count = 0
            try:
                if self.engine and self.engine.browser:
                    results = self.engine.browser.run_sequence(
                        engine_steps, on_step=on_step)
                    ok_count = sum(1 for r in results if r.get("success"))
            except Exception as e:
                self.logger.error("Hotkey smart playback: {}".format(e))
            self._playback_running = False
            duration = "{:.1f}s".format(time.time() - start_time)
            if 0 <= idx < len(self._ud.recordings):
                self._ud.recordings[idx]["last_run"] = \
                    datetime.now().strftime("%Y-%m-%d %H:%M")
                self._ud.recordings[idx]["duration"] = duration
                self._ud.log(
                    "Play: {}".format(rec.get("name", "")),
                    "{}/{} steps OK".format(ok_count, total))
                self._ud.save()
            self._root.after(0, lambda: [
                self._close_playback_window(win),
                self._refresh_recordings_tree(),
                self._sv.set(
                    "Done: {}/{} steps successful.".format(ok_count, total)),
            ])

        threading.Thread(target=_run, daemon=True).start()

    def _hk_record_toggle(self):
        """Ctrl+3: Start/stop recording — hanya aktif jika toolbar sudah terbuka."""
        self.logger.info("HK: _hk_record_toggle called step_editor=%s toolbar=%s rec=%s fn=%s",
            self._step_editor_open,
            self._rec_toolbar_win is not None,
            self._rec,
            self._rec_toggle_fn is not None)
        if self._step_editor_open:
            return
        if not self._rec_toolbar_win and not self._rec:
            return
        if self._rec_toggle_fn:
            try:
                self._rec_toggle_fn()
            except Exception as _e:
                self.logger.error("HK: _rec_toggle_fn error: %s", _e, exc_info=True)

    # ================================================================
    #  GOOGLE ACCOUNTS MANAGER  (in Settings)
    # ================================================================

    def _build_google_accounts_card(self, parent):
        from modules.sheets import connector as _sc

        card = _card(parent, "Google Accounts  (Sheets)")
        card.pack(fill="x", padx=20, pady=(12, 0))

        # Description
        _lbl(card,
             "Tambah beberapa akun Google (service account) untuk pakai di\n"
             "beda spreadsheet atau beda Gmail.", text_color=MUT, fg_color=CARD, font=("Segoe UI", 9),
             justify="left").pack(anchor="w", pady=(0, 10))

        # Accounts list frame
        list_frame = _ck.Frame(card, fg_color=CARD)
        list_frame.pack(fill="x", pady=(0, 8))

        def _refresh_accounts():
            for w in list_frame.winfo_children():
                w.destroy()
            accounts = _sc.list_accounts()
            if not accounts:
                _lbl(list_frame,
                     "Belum ada akun Google terhubung.", text_color=MUT, fg_color=CARD, font=("Segoe UI", 9)).pack(anchor="w")
                return

            # Header
            hdr = _ck.Frame(list_frame, fg_color=SIDE)
            hdr.pack(fill="x", pady=(0, 2))
            for txt, w in [("Nama", 110), ("Service Account Email", 280),
                           ("Status", 70), ("Aksi", 120)]:
                _ck.Label(hdr, text=txt, fg_color=SIDE, text_color=MUT,
                         font=("Segoe UI", 8, "bold"),
                         width=w // 8, anchor="w").pack(side="left", padx=4)

            for acc in accounts:
                row = _ck.Frame(list_frame, fg_color=BG, pady=3)
                row.pack(fill="x")

                # Name
                name_lbl = _ck.Label(row, text=acc["name"], fg_color=BG, text_color=FG,
                                    font=("Segoe UI", 9, "bold"),
                                    width=14, anchor="w")
                name_lbl.pack(side="left", padx=(4, 0))

                # Email (with copy button)
                email_frame = _ck.Frame(row, fg_color=BG)
                email_frame.pack(side="left", padx=(4, 0))
                email_txt = acc["email"] or "(invalid)"
                _ck.Label(email_frame, text=email_txt[:38], fg_color=BG, text_color=GRN if acc["email"] else RED,
                         font=("Consolas", 8), anchor="w").pack(side="left")
                _ck.Button(email_frame, text="copy", fg_color=BG, text_color=MUT,
                          font=("Segoe UI", 7), relief="flat", bd=0,
                          cursor="hand2", padx=4,
                          command=lambda e=acc["email"]: [
                              self._root.clipboard_clear(),
                              self._root.clipboard_append(e),
                              self._sv.set("Email disalin: {}".format(e))
                          ]).pack(side="left")

                # Active badge
                if acc["active"]:
                    _ck.Label(row, text=" AKTIF ", fg_color=GRN, text_color=BG,
                             font=("Segoe UI", 7, "bold"),
                             padx=4).pack(side="left", padx=(8, 0))
                else:
                    _ck.Button(row, text="Aktifkan", fg_color=CARD, text_color=ACC,
                              font=("Segoe UI", 8), relief="flat", bd=0,
                              padx=6, pady=2, cursor="hand2",
                              command=lambda n=acc["name"]: [
                                  _sc.set_active_account(n),
                                  _refresh_accounts(),
                                  self._navigate("sheet"),
                                  self._sv.set("Akun aktif: {}".format(n))
                              ]).pack(side="left", padx=(8, 0))

                # Delete
                _ck.Button(row, text="Hapus", fg_color=CARD, text_color=RED,
                          font=("Segoe UI", 8), relief="flat", bd=0,
                          padx=6, pady=2, cursor="hand2",
                          command=lambda n=acc["name"]: self._google_remove_account(
                              n, _refresh_accounts)
                          ).pack(side="right", padx=(0, 4))

        _refresh_accounts()

        # Action buttons
        btn_row = _ck.Frame(card, fg_color=CARD)
        btn_row.pack(anchor="w", pady=(4, 0))
        _ck.Button(btn_row, text="+ Tambah Akun Google", fg_color=ACC, text_color=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
                  command=lambda: self._show_sheets_setup_guide(
                      on_done=_refresh_accounts)
                  ).pack(side="left", padx=(0, 8))
        _ck.Button(btn_row, text="Panduan Setup", fg_color=CARD, text_color=FG, font=("Segoe UI", 9),
                  relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
                  command=lambda: self._show_sheets_setup_guide()
                  ).pack(side="left")

    def _google_remove_account(self, name, refresh_cb):
        from modules.sheets import connector as _sc
        if not self._confirm_dialog(
                "Hapus Akun Google?",
                "Hapus akun '{}'?\nSemua sheet yang pakai akun ini perlu disetup ulang.".format(name),
                confirm_text="Ya, Hapus", accent=RED):
            return
        _sc.remove_account(name)
        refresh_cb()
        self._sv.set("Akun '{}' dihapus.".format(name))

    def _show_sheets_setup_guide(self, on_done=None):
        """Step-by-step beginner wizard for Google Sheets setup."""
        import webbrowser
        from tkinter import filedialog
        from modules.sheets import connector as _sc

        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Setup Google Sheets — Panduan Langkah demi Langkah")
        dlg.geometry("560x500")
        dlg.configure(fg_color=BG)
        dlg.resizable(False, False)
        dlg.update()
        dlg.grab_set()

        # ── Step definitions ──────────────────────────────────────────────
        accs_now = _sc.list_accounts()
        active_email_now = next((a["email"] for a in accs_now if a["active"]), "")

        STEPS = [
            {
                "icon": "?", "color": ACC,
                "title": "Selamat datang di panduan Google Sheets!",
                "body": (
                    "Panduan ini akan membantu kamu menghubungkan Google Sheets\n"
                    "ke Synthex dalam 6 langkah mudah.\n\n"
                    "Kamu hanya perlu:\n"
                    "  - Akun Google (Gmail)\n"
                    "  - Akses internet\n\n"
                    "Tekan  Lanjut  untuk mulai."
                ),
            },
            {
                "icon": "1", "color": BLUE,
                "title": "Buka Google Cloud Console",
                "body": (
                    "Google Cloud Console adalah tempat kamu membuat akun robot untuk Synthex.\n\n"
                    "1. Klik tombol di bawah\n"
                    "2. Login dengan Gmail yang ingin kamu pakai\n"
                    "3. Kamu akan melihat halaman dashboard"
                ),
                "btn_label": "Buka Google Cloud Console",
                "btn_cmd": lambda: webbrowser.open("https://console.cloud.google.com/"),
            },
            {
                "icon": "2", "color": PRP,
                "title": "Buat Project Baru",
                "body": (
                    "Project adalah wadah untuk pengaturan aplikasimu.\n\n"
                    "1. Di pojok kiri atas, klik dropdown nama project\n"
                    "2. Klik  New Project\n"
                    "3. Isi nama: Synthex\n"
                    "4. Klik  Create\n\n"
                    "Tunggu sebentar sampai project selesai dibuat."
                ),
                "btn_label": "Langsung ke halaman buat project",
                "btn_cmd": lambda: webbrowser.open(
                    "https://console.cloud.google.com/projectcreate"),
            },
            {
                "icon": "3", "color": GRN,
                "title": "Aktifkan Google Sheets API",
                "body": (
                    "Kita perlu mengaktifkan izin untuk akses Google Sheets.\n\n"
                    "1. Klik tombol di bawah\n"
                    "2. Pastikan project Synthex sudah dipilih (cek pojok kiri atas)\n"
                    "3. Klik tombol biru  Enable\n\n"
                    "Selesai! API sudah aktif."
                ),
                "btn_label": "Aktifkan Google Sheets API",
                "btn_cmd": lambda: webbrowser.open(
                    "https://console.cloud.google.com/apis/library/sheets.googleapis.com"),
            },
            {
                "icon": "4", "color": YEL,
                "title": "Buat Service Account & Download Kunci",
                "body": (
                    "Service account adalah akun robot untuk Synthex (bukan akunmu sendiri).\n\n"
                    "1. Klik tombol di bawah\n"
                    "2. Klik  + Create Service Account\n"
                    "3. Isi nama: synthex-bot  lalu klik Done\n"
                    "4. Klik nama akun yang baru dibuat\n"
                    "5. Buka tab  Keys  -> Add Key -> Create new key -> JSON\n"
                    "6. File .json akan otomatis terdownload ke komputermu"
                ),
                "btn_label": "Buka halaman Service Accounts",
                "btn_cmd": lambda: webbrowser.open(
                    "https://console.cloud.google.com/iam-admin/serviceaccounts"),
            },
            {
                "icon": "5", "color": ACC,
                "title": "Upload File JSON ke Synthex",
                "body": "Pilih file .json yang tadi didownload dari langkah sebelumnya:",
                "is_upload": True,
            },
            {
                "icon": "6", "color": GRN,
                "title": "Share Spreadsheet ke Synthex",
                "body": (
                    "Langkah terakhir: beri izin Synthex untuk baca/tulis spreadsheetmu.\n\n"
                    "1. Buka Google Spreadsheet yang ingin dipakai\n"
                    "2. Klik tombol  Share  (pojok kanan atas)\n"
                    "3. Tempel email service account di bawah ini\n"
                    "4. Pilih akses  Editor\n"
                    "5. Klik Send\n\n"
                    "Selesai! Synthex sudah bisa mengakses spreadsheetmu."
                ),
                "is_share": True,
            },
        ]

        # ── Header bar ────────────────────────────────────────────────────
        hdr = _ck.Frame(dlg, fg_color=ACC, height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        _ck.Label(hdr, text="  Panduan Setup Google Sheets", fg_color=ACC, text_color=BG,
                 font=("Segoe UI", 12, "bold")).pack(side="left", pady=12)
        _ck.Button(hdr, text="X", fg_color=ACC, text_color=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=10, cursor="hand2",
                  command=dlg.destroy).pack(side="right", padx=8, pady=10)

        # ── Progress dots ─────────────────────────────────────────────────
        dot_frame = _ck.Frame(dlg, fg_color=BG, pady=8)
        dot_frame.pack(fill="x", padx=20)
        dot_labels = []
        for i, s in enumerate(STEPS):
            lbl = _ck.Label(dot_frame, text=" ", fg_color=SIDE, width=4, height=1)
            lbl.pack(side="left", padx=3)
            dot_labels.append((lbl, s["color"]))

        # ── Content area ──────────────────────────────────────────────────
        content_frame = _ck.Frame(dlg, fg_color=BG)
        content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # ── Bottom nav ────────────────────────────────────────────────────
        nav = _ck.Frame(dlg, fg_color=CARD, pady=10)
        nav.pack(fill="x", side="bottom")

        btn_prev = _ck.Button(nav, text="< Kembali", fg_color=SIDE, text_color=FG,
                             font=("Segoe UI", 9), relief="flat", bd=0,
                             padx=14, pady=6, cursor="hand2")
        btn_prev.pack(side="left", padx=16)

        step_lbl = _ck.Label(nav, text="", fg_color=CARD, text_color=MUT,
                            font=("Segoe UI", 9))
        step_lbl.pack(side="left", expand=True)

        btn_close = _ck.Button(nav, text="Tutup", fg_color=SIDE, text_color=FG,
                              font=("Segoe UI", 9), relief="flat", bd=0,
                              padx=14, pady=6, cursor="hand2",
                              command=dlg.destroy)
        btn_close.pack(side="right", padx=16)

        btn_next = _ck.Button(nav, text="Lanjut >", fg_color=ACC, text_color=BG,
                             font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                             padx=14, pady=6, cursor="hand2")
        btn_next.pack(side="right", padx=(0, 8))

        upload_status_var = tk.StringVar()
        upload_name_var   = tk.StringVar(value="gmail_saya")

        _cur = [0]

        def _render(idx):
            _cur[0] = idx
            for w in content_frame.winfo_children():
                w.destroy()
            step  = STEPS[idx]
            total = len(STEPS)

            for i, (lbl, col) in enumerate(dot_labels):
                lbl.configure(fg_color=col if i == idx else SIDE)

            step_lbl.configure(text="Langkah {} dari {}".format(idx + 1, total))
            btn_prev.configure(state="normal" if idx > 0 else "disabled")
            is_last = idx == total - 1
            btn_next.configure(
                text="Selesai!" if is_last else "Lanjut >", fg_color=GRN if is_last else ACC)

            top_row = _ck.Frame(content_frame, fg_color=BG)
            top_row.pack(fill="x", pady=(8, 4))
            _ck.Label(top_row, text=step["icon"], fg_color=step["color"], text_color=BG,
                     font=("Segoe UI", 11, "bold"), width=3, pady=4,
                     ).pack(side="left")
            _ck.Label(top_row, text="  " + step["title"], fg_color=BG, text_color=FG,
                     font=("Segoe UI", 11, "bold"), anchor="w",
                     ).pack(side="left", fill="x", expand=True)

            _ck.Frame(content_frame, fg_color=SIDE, height=1).pack(fill="x", pady=(4, 10))

            _ck.Label(content_frame, text=step["body"], fg_color=BG, text_color=MUT,
                     font=("Segoe UI", 10), justify="left", anchor="nw",
                     wraplength=500).pack(anchor="w", fill="x")

            if step.get("btn_label"):
                _ck.Button(content_frame, text=step["btn_label"], fg_color=step["color"], text_color=BG,
                          font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                          padx=14, pady=7, cursor="hand2",
                          command=step["btn_cmd"]).pack(anchor="w", pady=(14, 0))

            if step.get("is_upload"):
                up_row = _ck.Frame(content_frame, fg_color=BG)
                up_row.pack(fill="x", pady=(12, 0))
                _ck.Label(up_row, text="Nama akun (bebas):", fg_color=BG, text_color=MUT,
                         font=("Segoe UI", 9)).pack(side="left")
                _ck.Entry(up_row, textvariable=upload_name_var, fg_color=CARD, text_color=FG, insertbackground=ACC,
                         font=("Segoe UI", 10), relief="flat",
                         bd=0, highlightthickness=1,
                         highlightbackground=SIDE, highlightcolor=ACC,
                         width=18).pack(side="left", padx=(8, 0))

                status_up = _ck.Label(content_frame, textvariable=upload_status_var, fg_color=BG, text_color=GRN, font=("Segoe UI", 9),
                                     wraplength=500, justify="left")

                def _do_upload(s_lbl=status_up):
                    path = filedialog.askopenfilename(
                        parent=dlg,
                        title="Pilih file credentials JSON",
                        filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
                    if not path:
                        return
                    nm = upload_name_var.get().strip() or "default"
                    ok, msg = _sc.add_account(nm, path)
                    if ok:
                        upload_status_var.set("Berhasil! Email: {}".format(msg))
                        s_lbl.configure(text_color=GRN)
                        if on_done:
                            on_done()
                        nonlocal active_email_now
                        acts = _sc.list_accounts()
                        active_email_now = next(
                            (a["email"] for a in acts if a["active"]), msg)
                    else:
                        upload_status_var.set("Gagal: {}".format(msg))
                        s_lbl.configure(text_color=RED)

                _ck.Button(content_frame, text="Pilih File credentials.json", fg_color=ACC, text_color=BG, font=("Segoe UI", 10, "bold"),
                          relief="flat", bd=0, padx=16, pady=8,
                          cursor="hand2", command=_do_upload
                          ).pack(anchor="w", pady=(10, 0))
                status_up.pack(anchor="w", pady=(6, 0))

            if step.get("is_share"):
                email_show = active_email_now
                if not email_show:
                    acts = _sc.list_accounts()
                    email_show = next((a["email"] for a in acts if a["active"]), "")

                share_f = _ck.Frame(content_frame, fg_color=CARD, padx=14, pady=12)
                share_f.pack(fill="x", pady=(14, 0))
                _ck.Label(share_f,
                         text="Email service account (salin & tempel ke Share):", fg_color=CARD, text_color=YEL,
                         font=("Segoe UI", 9, "bold")).pack(anchor="w")
                em_row = _ck.Frame(share_f, fg_color=CARD)
                em_row.pack(fill="x", pady=(6, 0))
                disp = email_show or "(belum ada akun - selesaikan langkah 5 dulu)"
                _ck.Label(em_row, text=disp, fg_color=CARD, text_color=GRN,
                         font=("Consolas", 10, "bold")).pack(side="left")
                if email_show:
                    _ck.Button(em_row, text="Salin", fg_color=ACC, text_color=BG,
                              font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                              padx=10, pady=3, cursor="hand2",
                              command=lambda e=email_show: [
                                  self._root.clipboard_clear(),
                                  self._root.clipboard_append(e),
                                  self._sv.set("Email disalin!")
                              ]).pack(side="left", padx=(10, 0))

                _ck.Button(content_frame, text="Buka Google Sheets sekarang", fg_color=GRN, text_color=BG,
                          font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                          padx=14, pady=7, cursor="hand2",
                          command=lambda: webbrowser.open("https://sheets.google.com")
                          ).pack(anchor="w", pady=(14, 0))

        def _go(delta):
            nxt = _cur[0] + delta
            if 0 <= nxt < len(STEPS):
                _render(nxt)
            elif nxt >= len(STEPS):
                dlg.destroy()

        btn_prev.configure(command=lambda: _go(-1))
        btn_next.configure(command=lambda: _go(+1))
        _render(0)
        dlg.update()
        dlg.deiconify()
    # ================================================================
    #  TEMPLATES PAGE
    # ================================================================

    def _pg_templates(self):
        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Template Macros",
                  "Pilih template siap pakai, kustomisasi, lalu simpan sebagai macro.")

        templates = _load_templates()
        if not templates:
            _lbl(f, "Tidak ada template ditemukan.", text_color=MUT, font=("Segoe UI", 10)).pack(padx=24, pady=20)
            return f

        # Scrollable canvas
        canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        sb = _ck.Scrollbar(f, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = _ck.Frame(canvas, fg_color=BG)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(
            win_id, width=e.width))

        # Step-type icons for step list
        _TICONS = {
            "go_to_url": "->", "click": "[*]", "type": "[T]",
            "get_text": "<T", "get_number": "<#", "wait": "[~]",
            "sheet_read_cell": "[R]", "sheet_write_cell": "[W]",
            "sheet_find_row": "[F]", "sheet_append_row": "[+]",
            "if_equals": "[=]", "if_contains": "[?]", "notify": "[!]",
            "sheet_get_pending_rows": "[P]", "web_get_order_list": "[O]",
            "validate_and_confirm_orders": "[V]",
        }
        _TCOLORS = {
            "go_to_url": BLUE, "click": ACC, "type": GRN,
            "get_text": YEL, "get_number": YEL, "wait": MUT,
            "sheet_read_cell": GRN, "sheet_write_cell": GRN,
            "sheet_find_row": GRN, "sheet_append_row": GRN,
            "if_equals": PRP, "if_contains": PRP, "notify": RED,
        }
        _CARD_COLORS = [ACC, GRN, YEL, PRP, BLUE, RED]

        for t_idx, tpl in enumerate(templates):
            card_acc = _CARD_COLORS[t_idx % len(_CARD_COLORS)]

            card = _ck.Frame(inner, fg_color=CARD, padx=0, pady=0)
            card.pack(fill="x", padx=20, pady=(0, 14))

            # Color stripe on left
            _ck.Frame(card, fg_color=card_acc, width=5).pack(side="left", fill="y")

            body = _ck.Frame(card, fg_color=CARD, padx=16, pady=12)
            body.pack(side="left", fill="both", expand=True)

            # Header row
            hrow = _ck.Frame(body, fg_color=CARD)
            hrow.pack(fill="x")
            cont = tk.BooleanVar(value=tpl.get("continuous_mode", False))
            _lbl(hrow, tpl.get("name", ""), fg_color=CARD, text_color=FG,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
            if cont.get():
                _ck.Label(hrow, text=" LOOP ", fg_color=YEL, text_color=BG,
                         font=("Segoe UI", 7, "bold"),
                         padx=4).pack(side="left", padx=(8, 0))
            steps_count = len(tpl.get("steps", []))
            _lbl(hrow, "  {} steps".format(steps_count), text_color=MUT, fg_color=CARD,
                 font=("Segoe UI", 9)).pack(side="left")

            _lbl(body, tpl.get("description", ""), text_color=MUT, fg_color=CARD,
                 font=("Segoe UI", 9), justify="left").pack(
                anchor="w", pady=(4, 8))

            # Step preview chips
            chip_row = _ck.Frame(body, fg_color=CARD)
            chip_row.pack(fill="x", pady=(0, 10))
            for step in tpl.get("steps", [])[:8]:
                stype = step.get("type", "")
                icon  = _TICONS.get(stype, "[?]")
                clr   = _TCOLORS.get(stype, MUT)
                chip  = _ck.Frame(chip_row, fg_color=BG, padx=5, pady=2)
                chip.pack(side="left", padx=(0, 4), pady=2)
                _ck.Label(chip, text=icon, fg_color=BG, text_color=clr,
                         font=("Consolas", 8)).pack()
            if steps_count > 8:
                _ck.Label(chip_row, text="+{}".format(steps_count - 8), fg_color=BG, text_color=MUT, font=("Consolas", 8),
                         padx=4, pady=2).pack(side="left")

            # Action buttons
            btn_row = _ck.Frame(body, fg_color=CARD)
            btn_row.pack(anchor="w")
            _ck.Button(
                btn_row, text="Load Template", fg_color=card_acc, text_color=BG,
                font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                padx=14, pady=5, cursor="hand2",
                command=lambda t=tpl: self._mb_open_with_template(t)
            ).pack(side="left", padx=(0, 8))
            _ck.Button(
                btn_row, text="Preview Steps", fg_color=CARD, text_color=FG,
                font=("Segoe UI", 9), relief="flat", bd=0,
                padx=10, pady=5, cursor="hand2",
                command=lambda t=tpl: self._template_preview(t)
            ).pack(side="left")

        return f

    def _template_preview(self, tpl):
        """Show a popup with all steps of a template."""
        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Preview: {}".format(tpl.get("name", "")))
        dlg.geometry("560x480")
        dlg.configure(fg_color=BG)
        dlg.resizable(True, True)

        _lbl(dlg, tpl.get("name", ""),
             font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=20, pady=(16, 2))
        _lbl(dlg, tpl.get("description", ""), text_color=MUT, font=("Segoe UI", 9)).pack(anchor="w", padx=20, pady=(0, 10))
        _ck.Frame(dlg, fg_color=SIDE, height=1).pack(fill="x", padx=20)

        lf = _ck.Frame(dlg, fg_color=CARD, padx=10, pady=10)
        lf.pack(fill="both", expand=True, padx=20, pady=10)

        st = ttk.Treeview(lf, columns=("no", "type", "detail"),
                          show="headings", selectmode="browse")
        st.heading("no",     text="#")
        st.heading("type",   text="Type")
        st.heading("detail", text="Detail")
        st.column("no",     width=36,  anchor="center")
        st.column("type",   width=160, anchor="w")
        st.column("detail", width=310, anchor="w")
        vsb = _ck.Scrollbar(lf, orient="vertical", command=st.yview)
        st.configure(yscrollcommand=vsb.set)
        st.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for i, step in enumerate(tpl.get("steps", []), 1):
            st.insert("", "end", values=(i, step.get("type", ""), _step_label(step)))

        btn_f = _ck.Frame(dlg, fg_color=BG)
        btn_f.pack(fill="x", padx=20, pady=(0, 16))
        _ck.Button(btn_f, text="Load this Template", fg_color=ACC, text_color=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=14, pady=7, cursor="hand2",
                  command=lambda: [dlg.destroy(),
                                   self._mb_open_with_template(tpl)]).pack(side="left")
        _ck.Button(btn_f, text="Close", command=dlg.destroy).pack(
            side="left", padx=(10, 0))
        dlg.update()
        dlg.deiconify()

    # ================================================================
    #  LOGS PAGE  (Live log viewer)
    # ================================================================

    def _pg_logs(self):
        f = _ck.Frame(self._content, fg_color=BG)
        self._hdr(f, "Live Logs",
                  "Semua event & error Synthex ditampilkan di sini secara real-time.")

        # Toolbar
        tb = _ck.Frame(f, fg_color=BG)
        tb.pack(fill="x", padx=20, pady=(0, 6))

        level_var = tk.StringVar(value="ALL")
        _all_lines: list = []  # buffer of (level_str, display_line) tuples

        def _apply_filter(*_):
            filt = level_var.get()
            lw.configure(state="normal")
            lw.delete("1.0", tk.END)
            for lvl, line in _all_lines:
                if filt == "ALL" or lvl == filt:
                    tag = {"INFO": "info", "WARNING": "warn",
                           "ERROR": "error", "DEBUG": "debug"}.get(lvl, "info")
                    lw.insert(tk.END, line + "\n", tag)
            lw.configure(state="disabled")
            lw.see(tk.END)

        for lv in ("ALL", "INFO", "WARNING", "ERROR"):
            _ck.Radiobutton(tb, text=lv, variable=level_var, value=lv, fg_color=BG, text_color=FG, selectcolor=CARD,
                           activebackground=BG, activeforeground=ACC,
                           font=("Segoe UI", 8),
                           command=_apply_filter).pack(side="left", padx=(0, 8))

        _ck.Button(tb, text="Clear", fg_color=CARD, text_color=RED,
                  font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                  padx=10, pady=3, cursor="hand2",
                  command=lambda: [
                      lw.configure(state="normal"),
                      lw.delete("1.0", tk.END),
                      lw.configure(state="disabled")
                  ]).pack(side="right")
        _ck.Button(tb, text="Copy All", fg_color=CARD, text_color=FG,
                  font=("Segoe UI", 8), relief="flat", bd=0,
                  padx=10, pady=3, cursor="hand2",
                  command=lambda: [
                      self._root.clipboard_clear(),
                      self._root.clipboard_append(
                          lw.get("1.0", tk.END))
                  ]).pack(side="right", padx=(0, 6))

        def _export_txt():
            import csv as _csv
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
                initialfile="synthex_log_{}.txt".format(
                    datetime.now().strftime("%Y%m%d_%H%M%S")),
                title="Export Log sebagai TXT")
            if not path:
                return
            try:
                text = lw.get("1.0", tk.END)
                with open(path, "w", encoding="utf-8") as fp:
                    fp.write(text)
                self._show_toast("Log diekspor ke TXT", kind="success")
            except Exception as ex:
                self._show_toast("Gagal export: {}".format(ex), kind="error")

        def _export_csv():
            import csv as _csv, re as _re
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV file", "*.csv"), ("All files", "*.*")],
                initialfile="synthex_log_{}.csv".format(
                    datetime.now().strftime("%Y%m%d_%H%M%S")),
                title="Export Log sebagai CSV")
            if not path:
                return
            try:
                text = lw.get("1.0", tk.END)
                # Parse format: HH:MM:SS  [module        ]  LEVEL    message
                pat = _re.compile(
                    r"^(\d{2}:\d{2}:\d{2})\s+\[([^\]]*)\]\s+(\w+)\s+(.*)$")
                rows = []
                for line in text.splitlines():
                    m = pat.match(line.strip())
                    if m:
                        rows.append([m.group(1), m.group(2).strip(),
                                     m.group(3), m.group(4)])
                    elif line.strip() and rows:
                        # continuation line — append to last message
                        rows[-1][3] += " " + line.strip()
                with open(path, "w", newline="", encoding="utf-8") as fp:
                    w = _csv.writer(fp)
                    w.writerow(["Time", "Module", "Level", "Message"])
                    w.writerows(rows)
                self._show_toast(
                    "Log diekspor ke CSV ({} baris)".format(len(rows)),
                    kind="success")
            except Exception as ex:
                self._show_toast("Gagal export: {}".format(ex), kind="error")

        _ck.Button(tb, text="Export CSV", fg_color=CARD, text_color=GRN,
                  font=("Segoe UI", 8), relief="flat", bd=0,
                  padx=10, pady=3, cursor="hand2",
                  command=_export_csv).pack(side="right", padx=(0, 4))
        _ck.Button(tb, text="Export TXT", fg_color=CARD, text_color=ACC,
                  font=("Segoe UI", 8), relief="flat", bd=0,
                  padx=10, pady=3, cursor="hand2",
                  command=_export_txt).pack(side="right", padx=(0, 4))

        # Log widget
        lf = _ck.Frame(f, fg_color=CARD, padx=6, pady=6)
        lf.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        lw = _ck.ScrolledText(
            lf, fg_color="#0A0A0F", text_color=FG, insertbackground=FG,
            font=("Consolas", 9), relief="flat", state="disabled",
            wrap="word")
        lw.pack(fill="both", expand=True)

        for tag, clr in [("info",  FG), ("warn", YEL),
                         ("error", RED), ("debug", MUT),
                         ("ok",    GRN), ("fail", RED)]:
            lw.tag_configure(tag, foreground=clr)

        # Attach logger handler
        handler = _TkLogHandler(lw)
        fmt = logging.Formatter(
            "%(asctime)s  [%(name)-12s]  %(levelname)-7s  %(message)s",
            "%H:%M:%S")
        handler.setFormatter(fmt)

        # Patch emit: buffer all lines + respect level filter
        _orig_emit = handler.emit
        def _filtered_emit(record, _h=handler):
            line = fmt.format(record)
            lvl  = record.levelname  # "INFO", "WARNING", "ERROR", "DEBUG"
            _all_lines.append((lvl, line))
            filt = level_var.get()
            if filt == "ALL" or filt == lvl:
                _orig_emit(record)
        handler.emit = _filtered_emit

        logging.getLogger().addHandler(handler)

        # Store ref so we can detach on page destroy
        def _on_destroy(e, h=handler):
            try:
                logging.getLogger().removeHandler(h)
            except Exception:
                pass
        f.bind("<Destroy>", _on_destroy)

        # Guide hint
        _ck.Label(f, text="Logs dari semua modul (browser, sheets, scheduler, macro) muncul otomatis.", fg_color=BG, text_color=MUT, font=("Segoe UI", 7)).pack(padx=20, pady=(0, 4))
        return f

    # ================================================================
    #  HELP OVERLAY
    # ================================================================

    _HELP_TEXT = {
        "home": (
            "HOME  -  Panduan Cepat\n\n"
            "Quick Actions bar di atas:\n"
            "  + New Macro   -> buat macro baru di Schedule\n"
            "  Start Recording  -> rekam klik/ketik sekarang\n"
            "  Open Spy      -> lihat koordinat elemen browser\n"
            "  Templates     -> macro siap pakai\n"
            "  View Logs     -> pantau log real-time\n\n"
            "My Tasks Today  : task terjadwal & status terakhir\n"
            "Quick Run       : jalankan macro dengan 1 klik\n"
            "Recent Activity : 5 log aktivitas terakhir"
        ),
        "record": (
            "RECORD  -  Panduan\n\n"
            "Simple Record:\n"
            "  Rekam klik & ketik berdasarkan posisi layar.\n"
            "  Cocok untuk aplikasi desktop atau game.\n"
            "  Shortcut: Ctrl+3\n\n"
            "Smart Record:\n"
            "  Rekam selector elemen web (bukan posisi).\n"
            "  Tahan posisi meski window dipindah/resize.\n"
            "  Butuh Chrome yang sudah dibuka.\n\n"
            "Live Preview Panel:\n"
            "  Saat recording, panel melayang menampilkan\n"
            "  6 langkah terakhir yang direkam secara real-time."
        ),
        "spy": (
            "SPY MODE  -  Panduan\n\n"
            "1. Klik 'Open Floating Spy'\n"
            "2. Arahkan kursor ke elemen Chrome\n"
            "3. Panel menampilkan:\n"
            "     Screen coords (X, Y)\n"
            "     Client coords (relatif ke window)\n"
            "     Warna pixel + swatch\n"
            "     Window title, class, handle\n"
            "     Tag/ID/CSS/XPath element (tekan F8)\n\n"
            "Simpan koordinat:\n"
            "  Isi nama -> tekan SAVE / F8\n"
            "  Tersimpan di data/spy_coords.json\n"
            "  Double-click di list -> copy ke clipboard"
        ),
        "schedule": (
            "SCHEDULE  -  Panduan Macro Builder\n\n"
            "Step Types:\n"
            "  -> go_to_url   : buka URL di Chrome\n"
            "  [*] click      : klik elemen\n"
            "  [T] type       : ketik teks ke field\n"
            "  <T  get_text   : ambil teks -> simpan ke variabel\n"
            "  [R] sheet_read : baca sel Google Sheet\n"
            "  [W] sheet_write: tulis ke sel\n"
            "  [=] if_equals  : kondisi / logika\n"
            "  [!] notify     : kirim notifikasi\n\n"
            "Tips:\n"
            "  Gunakan {variable} untuk memakai nilai yang disimpan\n"
            "  Test Run: jalankan 1 step per step untuk debugging\n"
            "  Spy Mode: klik Use in Macro untuk insert selector otomatis"
        ),
        "templates": (
            "TEMPLATES  -  Panduan\n\n"
            "Template adalah macro yang sudah jadi.\n"
            "Kamu tinggal mengganti placeholder:\n"
            "  {url}           -> ganti dengan URL target\n"
            "  {selector}      -> CSS selector elemen\n"
            "  {sheet}         -> nama sheet yang terhubung\n"
            "  {cell}          -> alamat sel, contoh: A1\n\n"
            "Cara pakai:\n"
            "  1. Klik 'Load Template'\n"
            "  2. Macro Builder terbuka otomatis\n"
            "  3. Ganti setiap placeholder dengan nilai asli\n"
            "  4. Klik Save untuk menyimpan macro"
        ),
        "sheet": (
            "GOOGLE SHEETS  -  Panduan\n\n"
            "Setup sekali:\n"
            "  1. Buat Service Account di Google Cloud Console\n"
            "  2. Download credentials.json\n"
            "  3. Share spreadsheet ke email service account\n"
            "  4. Upload credentials.json ke Synthex\n\n"
            "Quick Actions:\n"
            "  Read Cell  : baca nilai 1 sel\n"
            "  Write Cell : tulis nilai ke sel\n"
            "  Append Row : tambah baris baru di bawah"
        ),
        "logs": (
            "LOGS  -  Panduan\n\n"
            "Semua modul Synthex menulis log di sini:\n"
            "  [INFO]    aktivitas normal\n"
            "  [WARNING] peringatan (tidak fatal)\n"
            "  [ERROR]   error yang butuh perhatian\n\n"
            "Tips debug:\n"
            "  Jika macro gagal -> lihat ERROR di log\n"
            "  Jika sheets gagal -> cari pesan 'gspread'\n"
            "  Jika browser gagal -> cari pesan 'playwright'\n\n"
            "Copy All -> salin semua log ke clipboard\n"
            "Clear    -> bersihkan tampilan log"
        ),
    }

    def _show_command_palette(self):
        """Ctrl+K command palette — ketik nama fitur, Enter untuk navigasi."""
        if not self._root or not self._root.winfo_exists():
            return

        # Prevent duplicate palette
        if getattr(self, "_palette_open", False):
            return
        self._palette_open = True

        # ── Build searchable items ────────────────────────────────────────
        _descriptions = {
            "home":      "Dashboard utama & ringkasan aktivitas",
            "web":       "Automasi browser & web scraping",
            "spy":       "Monitor aktivitas layar & input",
            "record":    "Rekam & putar ulang macro otomatis",
            "schedule":  "Jadwalkan task otomatis berkala",
            "templates": "Template macro siap pakai",
            "qris":      "Konversi QRIS statis ke dinamis dengan nominal kustom",
            "sheet":     "Sinkronisasi data ke Google Sheets",
            "rekening":  "Monitor saldo & mutasi rekening",
            "monitor":   "Pantau harga & perubahan data",
            "chat":      "Chat real-time dengan pengguna lain",
            "ai_chat":   "Chat pribadi dengan AI (GPT, Claude, Gemini, Groq)",
            "inbox":     "Pesan masuk & notifikasi",
            "blog":      "Tulis & kelola artikel blog",
            "remote":    "Kontrol perangkat dari jarak jauh",
            "history":   "Riwayat aktivitas & log eksekusi",
            "logs":      "Log sistem & error detail",
            "settings":  "Pengaturan akun & preferensi",
            "master":    "Panel kontrol master admin",
        }
        _is_master = (self._email == self.MASTER_EMAIL)
        _items = [
            (label, key, _descriptions.get(key, ""))
            for label, key in self.NAV
            if key and not (key == "master" and not _is_master)
        ]

        # ── Window ───────────────────────────────────────────────────────
        OW, PAD = 520, 12
        ov = ctk.CTkToplevel(self._root)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.0)
        ov.configure(fg_color="#0A0A14")

        # outer border
        border = _ck.Frame(ov, fg_color=ACC, bd=0)
        border.pack(fill="both", expand=True, padx=1, pady=1)
        body  = _ck.Frame(border, fg_color="#0D0D18")
        body.pack(fill="both", expand=True)

        # search row
        s_row = _ck.Frame(body, fg_color="#0D0D18")
        s_row.pack(fill="x", padx=PAD, pady=(PAD, 0))
        _ck.Label(s_row, text="🔍", fg_color="#0D0D18", text_color=MUT,
                 font=("Segoe UI", 11)).pack(side="left", padx=(0, 6))
        _var = tk.StringVar()
        entry = _ck.Entry(s_row, textvariable=_var, fg_color="#0D0D18", text_color=FG,
                         font=("Segoe UI", 12), relief="flat", bd=0,
                         insertbackground=ACC, width=36)
        entry.pack(side="left", fill="x", expand=True, ipady=6)
        _ck.Label(s_row, text="Esc", fg_color="#1A1A28", text_color=MUT,
                 font=("Segoe UI", 7), padx=5, pady=2).pack(side="right")

        _ck.Frame(body, fg_color="#1c1c2e", height=1).pack(fill="x", pady=(PAD, 0))

        # results frame (scrollable)
        results_frame = _ck.Frame(body, fg_color="#0D0D18")
        results_frame.pack(fill="both", expand=True, pady=(0, PAD))

        # hint label (shown when empty results)
        hint_lbl = _ck.Label(results_frame, text="Tidak ada hasil ditemukan.", fg_color="#0D0D18", text_color=MUT, font=("Segoe UI", 9))

        _rows: list = []      # list of (frame, key) for keyboard nav
        _sel  = [0]           # currently highlighted index

        def _close():
            self._palette_open = False
            def _fade(step=0):
                if not ov.winfo_exists(): return
                a = max(0.0, 1.0 - step / 6)
                ov.attributes("-alpha", a)
                if step < 6:
                    ov.after(16, _fade, step + 1)
                else:
                    try: ov.destroy()
                    except Exception: pass
            _fade()

        def _go(key):
            _close()
            self._root.after(80, lambda: self._show(key))

        def _highlight(idx):
            for i, (rf, _) in enumerate(_rows):
                rf.configure(fg_color="#1c1c2e" if i == idx else "#0D0D18")
                for child in rf.winfo_children():
                    child.configure(fg_color="#1c1c2e" if i == idx else "#0D0D18")

        def _render(query=""):
            # clear existing rows
            for rf, _ in _rows:
                rf.destroy()
            _rows.clear()
            hint_lbl.pack_forget()
            _sel[0] = 0

            q = query.strip().lower()
            filtered = [
                (label, key, desc)
                for label, key, desc in _items
                if not q or q in label.lower() or q in desc.lower()
            ]

            if not filtered:
                hint_lbl.pack(pady=18)
                return

            for i, (label, key, desc) in enumerate(filtered[:12]):
                rf = _ck.Frame(results_frame, fg_color="#0D0D18", cursor="hand2")
                rf.pack(fill="x", padx=0)

                # icon
                photo = self._nav_photo_dim.get(key)
                if photo:
                    ic = _ck.Label(rf, image=photo, fg_color="#0D0D18", padx=10, pady=8)
                    ic.pack(side="left")

                # text
                tf = _ck.Frame(rf, fg_color="#0D0D18")
                tf.pack(side="left", fill="x", expand=True, pady=6)
                _ck.Label(tf, text=label, fg_color="#0D0D18", text_color=FG,
                         font=("Segoe UI", 10, "bold"), anchor="w").pack(anchor="w")
                if desc:
                    _ck.Label(tf, text=desc, fg_color="#0D0D18", text_color=MUT,
                             font=("Segoe UI", 8), anchor="w").pack(anchor="w")

                # arrow hint
                _ck.Label(rf, text="↵", fg_color="#0D0D18", text_color="#2A2A44",
                         font=("Segoe UI", 10), padx=10).pack(side="right")

                _rows.append((rf, key))
                _cur_idx = len(_rows) - 1

                def _bind_row(frame, k, idx):
                    frame.bind("<Button-1>", lambda e: _go(k))
                    for child in frame.winfo_children():
                        child.bind("<Button-1>", lambda e, kk=k: _go(kk))
                    frame.bind("<Enter>", lambda e, i=idx: _highlight(i))
                    frame.bind("<Leave>", lambda e: _highlight(_sel[0]))
                _bind_row(rf, key, _cur_idx)

            _highlight(0)

            # resize window height to fit
            ov.update_idletasks()
            new_h = min(500, body.winfo_reqheight() + 4)
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            ov.geometry("{}x{}+{}+{}".format(
                OW, new_h, (sw - OW) // 2,
                int(sh * 0.22)))

        def _on_key(e):
            if e.keysym == "Escape":
                _close(); return
            if e.keysym == "Return" and _rows:
                _go(_rows[_sel[0]][1]); return
            if e.keysym == "Down" and _rows:
                _sel[0] = (_sel[0] + 1) % len(_rows)
                _highlight(_sel[0]); return
            if e.keysym == "Up" and _rows:
                _sel[0] = (_sel[0] - 1) % len(_rows)
                _highlight(_sel[0]); return

        _var.trace_add("write", lambda *_: _render(_var.get()))
        ov.bind("<KeyPress>", _on_key)
        entry.bind("<KeyPress>", _on_key)

        # ── Position & animate open ───────────────────────────────────────
        _render()
        ov.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        h0 = body.winfo_reqheight() + 4
        ov.geometry("{}x{}+{}+{}".format(OW, h0, (sw - OW) // 2, int(sh * 0.22)))

        def _fade_in(step=0):
            if not ov.winfo_exists(): return
            ov.attributes("-alpha", min(0.97, step / 8 * 0.97))
            if step < 8:
                ov.after(14, _fade_in, step + 1)

        ov.after(10, _fade_in)
        entry.focus_set()
        try:
            ov.update()
            ov.grab_set()
        except Exception:
            self._palette_open = False
            return
        ov.bind("<Destroy>", lambda e: setattr(self, "_palette_open", False))

    def _show_help(self):
        """Show contextual help overlay for current page."""
        page = self._cur
        text = self._HELP_TEXT.get(page, (
            "Synthex  -  Bantuan\n\n"
            "Pilih halaman dari sidebar, lalu klik ? untuk panduan spesifik.\n\n"
            "Shortcut:\n"
            "  Ctrl+1   : Play recording terakhir\n"
            "  Ctrl+3   : Mulai/Stop simple recording\n\n"
            "Butuh bantuan lebih? Hubungi Yohn18."
        ))

        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()
        dlg.title("Panduan - {}".format(page.capitalize()))
        dlg.geometry("480x400")
        dlg.configure(fg_color=BG)
        dlg.resizable(True, True)
        dlg.attributes("-topmost", True)

        # Header
        hdr = _ck.Frame(dlg, fg_color=ACC, height=42)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        _ck.Label(hdr, text="  Panduan: {}".format(page.upper()), fg_color=ACC, text_color=BG, font=("Segoe UI", 11, "bold")).pack(
            side="left", pady=10)
        _ck.Button(hdr, text="X", fg_color=ACC, text_color=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=10, cursor="hand2",
                  command=dlg.destroy).pack(side="right", pady=8, padx=8)

        # Content
        txt = _ck.ScrolledText(
            dlg, fg_color=CARD, text_color=FG, font=("Segoe UI", 10),
            relief="flat", wrap="word", padx=16, pady=12,
            state="normal")
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.insert("1.0", text)
        txt.configure(state="disabled")

        # Tip: navigate to other helps
        nav_f = _ck.Frame(dlg, fg_color=BG)
        nav_f.pack(fill="x", padx=10, pady=(0, 10))
        _lbl(nav_f, "Panduan lain:", text_color=MUT, fg_color=BG,
             font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))
        for pg in ("home", "record", "spy", "schedule", "templates", "sheet", "logs"):
            if pg != page:
                _ck.Button(nav_f, text=pg, fg_color=CARD, text_color=MUT,
                          font=("Segoe UI", 7), relief="flat", bd=0,
                          padx=6, pady=2, cursor="hand2",
                          command=lambda p=pg, d=dlg: [
                              d.destroy(), self._show("{}".format(p)),
                              self._root.after(50, self._show_help)
                          ]).pack(side="left", padx=(0, 3))
        dlg.update()
        dlg.deiconify()

    def _quit(self):
        """Tampilkan konfirmasi close yang menarik, lalu keluar + logout."""
        if getattr(self, "_quit_open", False):
            return
        self._quit_open = True
        dlg = ctk.CTkToplevel(self._root)
        dlg.withdraw()  # hide until fully built
        dlg.title("Tutup Synthex")
        dlg.resizable(False, False)
        dlg.configure(fg_color="#0D0D14")
        dlg.attributes("-topmost", True)

        W, H = 360, 210
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        dlg.geometry("{}x{}+{}+{}".format(W, H, (sw - W) // 2, (sh - H) // 2))

        # Border frame
        border = _ck.Frame(dlg, fg_color=ACC)
        border.place(x=0, y=0, width=W, height=3)

        # Icon + title
        _ck.Label(dlg, text="✕", fg_color="#0D0D14", text_color=ACC,
                 font=("Segoe UI", 22, "bold")).pack(pady=(22, 0))
        _ck.Label(dlg, text="Tutup Synthex?", fg_color="#0D0D14", text_color=FG,
                 font=("Segoe UI", 13, "bold")).pack(pady=(6, 0))
        _ck.Label(dlg, text="Kamu akan otomatis ter-logout\ndan semua proses akan dihentikan.", fg_color="#0D0D14", text_color=MUT, font=("Segoe UI", 9),
                 justify="center").pack(pady=(6, 16))

        # Separator
        _ck.Frame(dlg, fg_color=CARD, height=1).pack(fill="x", padx=24)

        # Buttons
        btn_row = _ck.Frame(dlg, fg_color="#0D0D14")
        btn_row.pack(pady=16)

        def _do_quit():
            dlg.destroy()
            import os as _os
            _appdata = _os.environ.get("APPDATA", "")
            for _tname in ("token.enc", "token.json"):
                _tp = _os.path.join(_appdata, "Synthex", _tname)
                if _os.path.exists(_tp):
                    try: _os.remove(_tp)
                    except Exception: pass
            try:
                self.config.set("ui.stay_logged_in", False)
                self.config.set("ui.last_email", "")
                self.config.save()
            except Exception:
                pass
            for _attr in ("_dm_poll_id", "_chat_poll_id", "_broadcast_poll_id",
                          "_adb_poll_id", "_spy_poll_id", "_rem_poll_id"):
                _pid = getattr(self, _attr, None)
                if _pid and self._root:
                    try: self._root.after_cancel(_pid)
                    except Exception: pass
                    setattr(self, _attr, None)
            if self._tray:
                try: self._tray.stop()
                except Exception: pass
            if self._hkl:
                try: self._hkl.stop()
                except Exception: pass
            if hasattr(self, "_price_monitor") and self._price_monitor:
                try: self._price_monitor.stop()
                except Exception: pass
            if getattr(self, "_scrcpy", None):
                try: self._scrcpy.stop()
                except Exception: pass

            def _fade_and_exit(step=0):
                total = 14
                alpha = max(0.0, 1.0 - step / total)
                try:
                    self._root.attributes("-alpha", alpha)
                except Exception:
                    pass
                if step < total:
                    self._root.after(16, _fade_and_exit, step + 1)
                else:
                    try:
                        self._root.destroy()
                    except Exception:
                        pass
                    _os._exit(0)

            if self._root:
                _fade_and_exit()
            else:
                _os._exit(0)

        _ck.Button(btn_row, text="  Ya, Tutup  ", fg_color=RED, text_color="white", relief="flat", font=("Segoe UI", 10, "bold"),
                  cursor="hand2", padx=14, pady=7,
                  command=_do_quit).pack(side="left", padx=(0, 10))
        def _cancel():
            self._quit_open = False
            dlg.destroy()

        _ck.Button(btn_row, text="  Batal  ", fg_color=CARD2, text_color=FG,
                  relief="flat", font=("Segoe UI", 10),
                  cursor="hand2", padx=14, pady=7,
                  command=_cancel).pack(side="left")

        dlg.protocol("WM_DELETE_WINDOW", _cancel)
        dlg.update()
        dlg.deiconify()
        dlg.grab_set()
        dlg.focus_force()
