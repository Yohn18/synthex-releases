# -*- coding: utf-8 -*-
"""ui/app.py - Synthex dashboard by Yohn18."""
import json, logging, os, re, sys, threading, time, tkinter as tk
from datetime import datetime
from tkinter import ttk, scrolledtext, simpledialog, messagebox
import pystray
from PIL import Image, ImageDraw
from core.config import Config
from core.logger import get_logger

_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_FILE = os.path.join(_ROOT, "data", "user_data.json")

BG    = "#111118"
CARD  = "#1A1A24"
CARD2 = "#1A1A28"   # darker card / input background
SIDE  = "#0D0D12"
ACC   = "#6C4AFF"   # purple accent
ACC2  = "#8880FF"   # lighter accent
FG    = "#E0DFFF"
MUT   = "#555575"
GRN   = "#4CAF88"
RED   = "#F06070"
YEL   = "#F0C060"
PRP   = "#9D5CF6"
BLUE  = "#4A9EFF"

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
    "sheet_get_pending_rows":       "[P]",
    "web_get_order_list":           "[O]",
    "validate_and_confirm_orders":  "[V]",
}


class _TkLogHandler(logging.Handler):
    def __init__(self, w):
        super().__init__()
        self._w = w

    def emit(self, record):
        msg = self.format(record) + "\n"
        tag = {logging.DEBUG: "debug", logging.INFO: "info",
               logging.WARNING: "warn"}.get(record.levelno, "error")
        self._w.after(0, lambda m=msg, t=tag: [
            self._w.configure(state="normal"),
            self._w.insert(tk.END, m, t),
            self._w.see(tk.END),
            self._w.configure(state="disabled")])


class UserData:
    def __init__(self):
        self._d = {k: [] for k in
                   ("websites", "recordings", "tasks", "activity",
                    "elements", "sheets")}
        try:
            saved = json.load(open(_DATA_FILE, "r", encoding="utf-8"))
            for k in self._d:
                self._d[k] = saved.get(k, [])
        except Exception:
            pass

    def save(self):
        os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
        json.dump(self._d, open(_DATA_FILE, "w", encoding="utf-8"), indent=2)

    def log(self, task, result, ok=True):
        self._d["activity"].insert(0, {
            "time":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "task":   task,
            "result": result,
            "ok":     ok,
        })
        self._d["activity"] = self._d["activity"][:500]
        self.save()

    @property
    def websites(self):   return self._d["websites"]
    @property
    def recordings(self): return self._d["recordings"]
    @property
    def tasks(self):      return self._d["tasks"]
    @property
    def activity(self):   return self._d["activity"]
    @property
    def elements(self):   return self._d["elements"]
    @property
    def sheets(self):     return self._d["sheets"]


# -- Widget helpers --

def _lbl(parent, text, fg=FG, bg=BG, font=("Segoe UI", 10), **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg, font=font, **kw)

def _card(parent, title=""):
    f = tk.Frame(parent, bg=CARD, padx=14, pady=12)
    if title:
        _lbl(f, title, fg=ACC, bg=CARD,
             font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
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
    s.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10))
    s.configure("TFrame",  background=BG)
    s.configure("TLabel",  background=BG, foreground=FG)
    s.configure("TButton", background=CARD, foreground=FG,
                relief="flat", padding=[10, 6])
    s.map("TButton",
          background=[("active", ACC)], foreground=[("active", BG)])
    s.configure("Accent.TButton", background=ACC, foreground=BG,
                font=("Segoe UI", 10, "bold"), padding=[14, 7])
    s.map("Accent.TButton", background=[("active", "#8880FF")])
    s.configure("Danger.TButton", background=CARD, foreground=RED,
                padding=[10, 6])
    s.map("Danger.TButton",
          background=[("active", RED)], foreground=[("active", BG)])
    s.configure("TEntry", fieldbackground=CARD, foreground=FG,
                insertcolor=FG, borderwidth=0)
    s.configure("Treeview", background=CARD, foreground=FG,
                fieldbackground=CARD, borderwidth=0, rowheight=28)
    s.map("Treeview",
          background=[("selected", ACC)], foreground=[("selected", BG)])
    s.configure("Treeview.Heading", background=SIDE, foreground=MUT,
                font=("Segoe UI", 9, "bold"), borderwidth=0)
    s.configure("TScrollbar", background=CARD, troughcolor=BG,
                borderwidth=0, arrowcolor=MUT)
    s.configure("TCombobox", fieldbackground=CARD, foreground=FG,
                arrowcolor=FG, background=CARD)
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
    return t or "(empty step)"


def _load_templates():
    path = os.path.join(_ROOT, "data", "templates.json")
    try:
        return json.load(open(path, "r", encoding="utf-8"))
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


# ============================================================
#  Main application class
# ============================================================

class SynthexApp:
    NAV = [
        ("Home",          "home"),
        ("Web",           "web"),
        ("Spy",           "spy"),
        ("Record",        "record"),
        ("Schedule",      "schedule"),
        ("Templates",     "templates"),
        ("Sheet",         "sheet"),
        ("Rekening",      "rekening"),
        ("Dashboard Update", "monitor"),
        ("Remote",        "remote"),
        ("History",       "history"),
        ("Logs",          "logs"),
        ("Settings",      "settings"),
    ]

    def __init__(self, config, engine=None):
        self.config  = config
        self.engine  = engine
        self.logger  = get_logger("ui")
        self._tray   = None
        self._hkl    = None
        self._root   = None
        self._email  = None
        self._token  = None
        self._ud     = UserData()
        self._pages  = {}
        self._nav    = {}
        self._cur    = ""

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

    def set_auth(self, email, token):
        self._email = email
        self._token = token

    def run(self):
        self._start_tray()
        self._splash()
        self._root.mainloop()

    # -- Splash / loading --

    def _splash(self):
        r = self._root = tk.Tk()
        if hasattr(sys, '_MEIPASS'):
            icon_path = os.path.join(sys._MEIPASS, 'assets', 'synthex.ico')
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'synthex.ico')
        if os.path.exists(icon_path):
            r.iconbitmap(icon_path)
        r.title("SYNTHEX")
        r.geometry("460x280")
        r.resizable(False, False)
        r.configure(bg=BG)
        r.protocol("WM_DELETE_WINDOW", self._quit)
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry("460x280+{}+{}".format((sw-460)//2, (sh-280)//2))
        _lbl(r, "SYNTHEX", fg=ACC,
             font=("Segoe UI", 30, "bold")).pack(pady=(46, 2))
        _lbl(r, "Automation Platform  by Yohn18",
             fg=MUT, font=("Segoe UI", 9)).pack()
        tk.Frame(r, bg=CARD, height=1).pack(fill="x", padx=48, pady=(24, 0))
        self._pc = tk.Canvas(r, width=364, height=4, bg=CARD,
                             highlightthickness=0, bd=0)
        self._pc.pack(padx=48)
        tk.Frame(r, bg=CARD, height=1).pack(fill="x", padx=48, pady=(0, 10))
        self._pv = tk.StringVar(value="Preparing...")
        tk.Label(r, textvariable=self._pv, fg=MUT, bg=BG,
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
        self._root.after(500, self._dashboard)

    # -- Dashboard shell --

    def _dashboard(self):
        for w in self._root.winfo_children():
            w.destroy()
        r = self._root
        r.title("Synthex  -  by Yohn18")
        r.geometry("1180x720")
        r.minsize(920, 600)
        r.resizable(True, True)
        r.configure(bg=BG)
        r.protocol("WM_DELETE_WINDOW", self._quit)
        _apply_styles(r)

        # ── HEADER ────────────────────────────────────────────────────────────
        top = tk.Frame(r, bg=SIDE, height=54)
        top.pack(fill="x")
        top.pack_propagate(False)

        # Left accent stripe
        tk.Frame(top, bg=ACC, width=4).pack(side="left", fill="y")

        tk.Label(top, text="\u26a1", bg=SIDE, fg=ACC,
                 font=("Segoe UI", 15)).pack(side="left", padx=(12, 3), pady=14)
        tk.Label(top, text="SYNTHEX", bg=SIDE, fg=ACC,
                 font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Label(top, text="by Yohn18", bg=SIDE, fg=MUT,
                 font=("Segoe UI", 8)).pack(side="left", padx=(6, 0), pady=(18, 0))

        # Right side
        tk.Button(top, text="Exit", bg=RED, fg=FG,
                  activebackground="#C04050", activeforeground=FG,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=16, pady=6, cursor="hand2",
                  command=self._logout).pack(side="right", padx=14, pady=12)
        tk.Button(top, text=" ? ", bg=CARD, fg=ACC,
                  activebackground=ACC, activeforeground=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=8, pady=6, cursor="hand2",
                  command=self._show_help).pack(side="right", pady=12)
        if self._email:
            tk.Label(top, text=self._email, bg=SIDE, fg=GRN,
                     font=("Segoe UI", 9)).pack(side="right", padx=10)

        # ── BODY ──────────────────────────────────────────────────────────────
        body = tk.Frame(r, bg=BG)
        body.pack(fill="both", expand=True)

        # ── SIDEBAR ───────────────────────────────────────────────────────────
        side = tk.Frame(body, bg=SIDE, width=200)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        # Sidebar top divider
        tk.Frame(side, bg="#1A1A28", height=1).pack(fill="x")

        tk.Label(side, text="NAVIGATION", bg=SIDE, fg=MUT,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=18, pady=(14, 6))

        NAV_ICONS = {
            "home":      "\U0001f3e0", "web":       "\U0001f310", "spy":      "\U0001f441",
            "record":    "\u23fa",     "schedule":  "\U0001f4c5", "sheet":    "\U0001f4ca",
            "rekening":  "\U0001f3e6", "history":   "\U0001f4cb", "settings": "\u2699\ufe0f",
            "templates": "\U0001f4da", "logs":      "\U0001f5d2", "monitor":  "\U0001f4b9",
            "remote":    "\U0001f4f1",
        }
        self._nav      = {}
        self._nav_bars = {}

        for label, key in self.NAV:
            icon = NAV_ICONS.get(key, "\u2022")
            row = tk.Frame(side, bg=SIDE)
            row.pack(fill="x")

            bar = tk.Frame(row, bg=ACC, width=3)
            bar.pack(side="left", fill="y")
            bar.pack_forget()
            self._nav_bars[key] = bar

            b = tk.Button(
                row,
                text="  {}  {}".format(icon, label),
                anchor="w", bg=SIDE, fg=MUT,
                activebackground=CARD, activeforeground=FG,
                font=("Segoe UI", 10), relief="flat", bd=0,
                padx=14, pady=9, cursor="hand2",
                command=lambda k=key: self._show(k))
            b.pack(fill="x", side="left", expand=True)
            self._nav[key] = b

        # Bottom status bar
        self._sv = tk.StringVar(value="")
        tk.Label(side, textvariable=self._sv, bg=SIDE, fg=MUT,
                 font=("Segoe UI", 7), wraplength=180,
                 justify="left").pack(side="bottom", anchor="w", padx=12, pady=(4, 4))

        # ── CONTENT ───────────────────────────────────────────────────────────
        self._content = tk.Frame(body, bg=BG)
        self._content.pack(side="left", fill="both", expand=True)

        # ── CLOCK (right side of header) ──────────────────────────────────────
        self._cl = tk.Label(top, text="", fg=MUT, bg=SIDE, font=("Segoe UI", 8))
        self._cl.pack(side="right", padx=6)
        self._tick()

        self._page_builders = {
            "home":      self._pg_home,
            "web":       self._pg_web,
            "spy":       self._pg_spy,
            "record":    self._pg_record,
            "schedule":  self._pg_schedule,
            "templates": self._pg_templates,
            "sheet":     self._pg_sheet,
            "rekening":  self._pg_rekening,
            "monitor":   self._pg_monitor,
            "remote":    self._pg_remote,
            "history":   self._pg_history,
            "logs":      self._pg_logs,
            "settings":  self._pg_settings,
        }

        self._show("home")
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry("1180x720+{}+{}".format((sw-1180)//2, (sh-720)//2))
        self._root.after(400, self._maybe_show_onboarding)

    def _show(self, key):
        if self._cur in self._pages:
            self._pages[self._cur].pack_forget()
        for k, b in self._nav.items():
            b.configure(bg=SIDE, fg=MUT,
                        activebackground=CARD, activeforeground=FG)
            self._nav_bars[k].pack_forget()
        if key in self._nav:
            self._nav[key].configure(bg=CARD, fg=FG,
                                      activebackground=CARD, activeforeground=ACC)
            self._nav_bars[key].pack(side="left", fill="y")
        if key not in self._pages:
            self._pages[key] = self._page_builders[key]()
        self._pages[key].pack(fill="both", expand=True)
        self._cur = key

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
        self._cl.configure(text=datetime.now().strftime("%d %b %Y  %H:%M:%S"))
        self._root.after(1000, self._tick)

    def _hdr(self, f, title, sub=""):
        _lbl(f, title, font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=24, pady=(20, 0))
        if sub:
            _lbl(f, sub, fg=MUT, font=("Segoe UI", 9)).pack(
                anchor="w", padx=24, pady=(2, 10))

    # ================================================================
    #  HOME PAGE
    # ================================================================

    def _pg_home(self):
        f = tk.Frame(self._content, bg=BG)

        name    = self._email.split("@")[0] if self._email else "User"
        greet   = "{}, {}!".format(_greeting(), name)
        today   = datetime.now().strftime("%A, %d %B %Y")

        # Greeting
        _lbl(f, greet, font=("Segoe UI", 18, "bold"),
             fg=FG).pack(anchor="w", padx=24, pady=(22, 0))
        _lbl(f, today, fg=MUT, font=("Segoe UI", 10)).pack(
            anchor="w", padx=24, pady=(2, 16))

        # Quick Status row
        status_row = tk.Frame(f, bg=BG)
        status_row.pack(fill="x", padx=20, pady=(0, 4))
        browser_status = "Connected" if (
            self.engine and self.engine.browser and
            getattr(self.engine.browser, "_ready", False)
        ) else "Standby"
        sheet_count = len(self._ud.sheets)
        active_count = sum(1 for t in self._ud.tasks
                           if t.get("enabled", True) and
                           t.get("schedule_type","manual") != "manual")
        for lbl, val, clr in [
            ("Chrome",  browser_status,
             GRN if browser_status == "Connected" else YEL),
            ("Sheets",  "{} connected".format(sheet_count), GRN),
            ("Tasks",   "{} active".format(active_count),   ACC),
            ("Macros",  "{} saved".format(len(self._ud.tasks)), FG),
        ]:
            c = tk.Frame(status_row, bg=CARD, padx=14, pady=10)
            c.pack(side="left", fill="both", expand=True, padx=3)
            _lbl(c, lbl, fg=MUT, bg=CARD, font=("Segoe UI", 8)).pack(anchor="w")
            _lbl(c, val, fg=clr, bg=CARD,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")

        # ── Quick Action Bar ─────────────────────────────────────────────────
        qa_bar = tk.Frame(f, bg=SIDE, padx=12, pady=8)
        qa_bar.pack(fill="x", padx=20, pady=(6, 0))
        _lbl(qa_bar, "QUICK ACTIONS", fg=MUT, bg=SIDE,
             font=("Segoe UI", 7, "bold")).pack(side="left", padx=(0, 12))
        for qa_label, qa_cmd, qa_color in [
            ("+ New Macro",       lambda: self._show("schedule"),   ACC),
            ("Start Recording",   self._start_simple_rec,            GRN),
            ("Open Spy",          self._open_floating_spy,           BLUE),
            ("Templates",         lambda: self._show("templates"),   PRP),
            ("View Logs",         lambda: self._show("logs"),        MUT),
        ]:
            tk.Button(qa_bar, text=qa_label, bg=qa_color, fg=BG,
                      font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                      padx=10, pady=4, cursor="hand2",
                      activebackground=CARD, activeforeground=FG,
                      command=qa_cmd).pack(side="left", padx=(0, 6))

        # My Tasks Today
        tasks_frame = _card(f, "My Tasks Today")
        tasks_frame.pack(fill="x", padx=20, pady=(14, 0))
        active_tasks = [t for t in self._ud.tasks
                        if t.get("enabled", True) and
                        t.get("schedule_type", "manual") != "manual"]
        if active_tasks:
            for task in active_tasks[:5]:
                stype = task.get("schedule_type", "manual")
                sval  = task.get("schedule_value", "")
                stime = task.get("schedule_time", "")
                if stype == "interval" and sval:
                    sched = "Every {}m".format(sval)
                elif stype == "daily" and stime:
                    sched = "Daily {}".format(stime)
                elif stype == "hourly":
                    sched = "Hourly"
                else:
                    sched = "Manual"

                tr = tk.Frame(tasks_frame, bg=CARD, pady=4)
                tr.pack(fill="x")
                tk.Frame(tr, bg=MUT, width=2).pack(side="left", fill="y",
                                                     padx=(0, 8))
                _lbl(tr, task.get("name", ""), bg=CARD,
                     font=("Segoe UI", 9, "bold")).pack(side="left")
                _lbl(tr, "|", fg=MUT, bg=CARD,
                     font=("Segoe UI", 9)).pack(side="left", padx=6)
                _lbl(tr, sched, fg=ACC, bg=CARD,
                     font=("Segoe UI", 9)).pack(side="left")
                status = task.get("last_status", "-")
                _lbl(tr, task.get("last_run", "-"), fg=MUT, bg=CARD,
                     font=("Segoe UI", 8)).pack(side="right", padx=(0, 8))
                _lbl(tr, status,
                     fg=GRN if status == "OK" else (RED if status == "FAIL" else MUT),
                     bg=CARD, font=("Segoe UI", 8, "bold")).pack(
                    side="right", padx=(0, 4))

                def _make_toggle(t=task):
                    def _do():
                        t["enabled"] = not t.get("enabled", True)
                        self._ud.save()
                        # Refresh home page
                        if "home" in self._pages:
                            self._pages["home"].destroy()
                            del self._pages["home"]
                        if self._cur == "home":
                            self._show("home")
                    return _do
                on_off = "ON" if task.get("enabled", True) else "OFF"
                btn_clr = GRN if task.get("enabled", True) else MUT
                tk.Button(tr, text=on_off, bg=btn_clr, fg=BG,
                          font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                          padx=6, pady=2, cursor="hand2",
                          command=_make_toggle()).pack(side="right", padx=(0, 8))
        else:
            _lbl(tasks_frame,
                 "No scheduled tasks yet. Go to Schedule to create one.",
                 fg=MUT, bg=CARD, font=("Segoe UI", 9)).pack(anchor="w")

        # Quick Run
        qr_frame = _card(f, "Quick Run")
        qr_frame.pack(fill="x", padx=20, pady=(14, 0))
        if self._ud.tasks:
            card_row = tk.Frame(qr_frame, bg=CARD)
            card_row.pack(fill="x")
            for task in self._ud.tasks[:6]:
                def _make_runner(t=task):
                    def _run():
                        if not self._confirm_run_dialog(t):
                            return
                        idx = self._ud.tasks.index(t)
                        stop_ev = threading.Event()
                        self._run_stop_flag = stop_ev
                        if t.get("continuous_mode"):
                            panel = self._show_continuous_progress_panel(t, stop_ev)
                            threading.Thread(
                                target=self._run_continuous_task_thread,
                                args=(t, idx, stop_ev, panel), daemon=True).start()
                        else:
                            panel = self._show_run_progress_panel(t, stop_ev)
                            threading.Thread(
                                target=self._run_task_thread,
                                args=(t, idx, stop_ev, panel), daemon=True).start()
                        self._sv.set("Running: {}...".format(t["name"]))
                    return _run
                tc = tk.Frame(card_row, bg=BG, padx=10, pady=8, cursor="hand2",
                              relief="flat", bd=1)
                tc.pack(side="left", padx=4, pady=2)
                _lbl(tc, task.get("name","")[:18], bg=BG,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")
                last = task.get("last_run", "-")
                stat = task.get("last_status", "-")
                _lbl(tc, "Last: {}".format(last), fg=MUT, bg=BG,
                     font=("Segoe UI", 7)).pack(anchor="w")
                tk.Button(tc, text="Run Now", bg=ACC, fg=BG,
                          font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                          padx=8, pady=3, cursor="hand2",
                          command=_make_runner()).pack(anchor="w", pady=(4, 0))
        else:
            _lbl(qr_frame, "No macros saved yet. Create one in Schedule.",
                 fg=MUT, bg=CARD, font=("Segoe UI", 9)).pack(anchor="w")

        # Recent Activity
        ac = _card(f, "Recent Activity")
        ac.pack(fill="x", padx=20, pady=(14, 20))
        acts = self._ud.activity[:5]
        if acts:
            for e in acts:
                ok = e.get("ok")
                r2 = tk.Frame(ac, bg=CARD)
                r2.pack(fill="x", pady=1)
                _lbl(r2, e["time"], fg=MUT, bg=CARD,
                     font=("Segoe UI", 8), width=19, anchor="w").pack(side="left")
                _lbl(r2, e["task"][:28], bg=CARD,
                     font=("Segoe UI", 9)).pack(side="left", padx=6)
                _lbl(r2, "OK" if ok else "FAIL",
                     fg=GRN if ok else RED,
                     bg=CARD, font=("Segoe UI", 8, "bold")).pack(side="right")
                _lbl(r2, e.get("result","")[:30], fg=MUT, bg=CARD,
                     font=("Segoe UI", 8)).pack(side="right", padx=6)
        else:
            _lbl(ac, "No activity yet.", fg=MUT, bg=CARD,
                 font=("Segoe UI", 9)).pack(anchor="w")
        return f

    # ================================================================
    #  WEB PAGE
    # ================================================================

    def _pg_web(self):
        f = tk.Frame(self._content, bg=BG)
        self._hdr(f, "Web Browser", "Navigate to websites in Chrome.")
        c = _card(f, "Open URL")
        c.pack(fill="x", padx=20)
        row = tk.Frame(c, bg=CARD)
        row.pack(fill="x")
        self._url = tk.StringVar()
        ttk.Entry(row, textvariable=self._url,
                  font=("Segoe UI", 10)).pack(
            side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="Open", style="Accent.TButton",
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
        f = tk.Frame(self._content, bg=BG)
        self._hdr(f, "Spy Mode", "Inspect Chrome elements in real-time.")

        main = tk.Frame(f, bg=BG)
        main.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        ctrl = _card(left, "Spy Controls")
        ctrl.pack(fill="x", pady=(0, 8))
        self._spy_btn = tk.Button(
            ctrl, text="ENABLE SPY", bg=ACC, fg=BG,
            font=("Segoe UI", 11, "bold"), relief="flat", bd=0,
            padx=16, pady=8, cursor="hand2", command=self._toggle_spy)
        self._spy_btn.pack(side="left", padx=(0, 8))
        ttk.Button(ctrl, text="Open Floating Spy",
                   command=self._open_floating_spy).pack(side="left",
                                                          padx=(0, 8))
        self._spy_status_lbl = _lbl(
            ctrl, "Inactive", fg=MUT, bg=CARD, font=("Segoe UI", 9))
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
            _lbl(guide, line, fg=MUT, bg=CARD,
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
            row = tk.Frame(info, bg=CARD)
            row.pack(fill="x", pady=2)
            _lbl(row, "{}:".format(label), fg=MUT, bg=CARD,
                 font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
            var = tk.StringVar(value="-")
            tk.Label(row, textvariable=var, fg=FG, bg=CARD,
                     font=("Segoe UI", 9), anchor="w").pack(
                side="left", fill="x", expand=True)
            self._spy_fields[key] = var
        ttk.Button(info, text="Save Element", style="Accent.TButton",
                   command=self._save_spy_element).pack(
            anchor="w", pady=(10, 0))

        saved = _card(left, "Saved Elements")
        saved.pack(fill="both", expand=True)
        self._spy_elements_tree = _tree(saved, [
            ("name",     "Name",     100),
            ("type",     "Type",      65),
            ("selector", "Selector", 195),
        ])
        btn_row = tk.Frame(saved, bg=CARD)
        btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_row, text="Fetch Value",
                   command=self._fetch_spy_element_value).pack(
            side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Copy Selector",
                   command=self._copy_spy_selector).pack(
            side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Scrape ke Sheet",
                   command=self._scrape_spy_to_sheet).pack(
            side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Delete", style="Danger.TButton",
                   command=self._delete_spy_element).pack(side="right")
        self._refresh_spy_elements_tree()
        return f

    # ================================================================
    #  RECORD PAGE
    # ================================================================

    def _pg_record(self):
        f = tk.Frame(self._content, bg=BG)
        self._hdr(f, "Action Recording",
                  "Rekam & putar ulang aksi secara otomatis.")

        # How-to strip
        how = tk.Frame(f, bg="#0D1A0D", padx=14, pady=8)
        how.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(how, text="Cara pakai:",
                 bg="#0D1A0D", fg=GRN, font=("Segoe UI", 8, "bold")).pack(
            side="left", padx=(0, 6))
        tk.Label(how,
                 text="Simple Record = rekam gerakan mouse & ketikan  |  "
                      "Smart Record = buat langkah otomasi manual (URL, klik, ketik, dll)",
                 bg="#0D1A0D", fg=FG, font=("Segoe UI", 8)).pack(
            side="left", fill="x", expand=True)

        # Two mode cards
        cards = tk.Frame(f, bg=BG)
        cards.pack(fill="x", padx=20, pady=(0, 12))

        # Simple Record card
        sc = tk.Frame(cards, bg=CARD, padx=16, pady=14)
        sc.pack(side="left", fill="both", expand=True, padx=(0, 8))
        _lbl(sc, "SIMPLE RECORD", bg=CARD, fg=ACC,
             font=("Segoe UI", 11, "bold")).pack(anchor="w")
        _lbl(sc,
             "Rekam semua klik mouse\ndan ketikan keyboard\nsecara otomatis.\n\n"
             "Cocok untuk tugas\nberulang di aplikasi\nmanapun (desktop/game).\n\n"
             "Shortcut: Ctrl+3",
             bg=CARD, fg=MUT,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 10))
        tk.Button(sc, text="Buka Recorder",
                  bg=ACC, fg=BG, font=("Segoe UI", 10, "bold"),
                  relief="flat", bd=0, padx=12, pady=8, cursor="hand2",
                  command=self._start_simple_rec).pack(fill="x")

        # Smart Record card
        ac = tk.Frame(cards, bg=CARD, padx=16, pady=14)
        ac.pack(side="left", fill="both", expand=True)
        _lbl(ac, "SMART RECORD", bg=CARD, fg=GRN,
             font=("Segoe UI", 11, "bold")).pack(anchor="w")
        _lbl(ac,
             "Buat langkah otomasi\nsatu per satu secara\nmanual: buka URL,\n"
             "klik elemen, ketik\nteks, tunggu, ambil\nteks, screenshot, dll.\n\n"
             "Hasil bisa dijalankan\nberkali-kali.",
             bg=CARD, fg=MUT,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 10))
        tk.Button(ac, text="Buat Langkah Baru",
                  bg=GRN, fg=BG, font=("Segoe UI", 10, "bold"),
                  relief="flat", bd=0, padx=12, pady=8, cursor="hand2",
                  command=self._start_smart_rec).pack(fill="x")

        # ── Daftar Rekaman Tersimpan ──────────────────────────────────────────
        lc = tk.Frame(f, bg=CARD, padx=0, pady=0)
        lc.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Card header row (title + counter badge)
        lc_hdr = tk.Frame(lc, bg=CARD, padx=14, pady=10)
        lc_hdr.pack(fill="x")
        tk.Label(lc_hdr, text="Daftar Rekaman Tersimpan",
                 bg=CARD, fg=FG,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        self._rec_count_lbl = tk.Label(lc_hdr, text="",
                 bg=ACC, fg="white",
                 font=("Segoe UI", 8, "bold"),
                 padx=7, pady=1)
        self._rec_count_lbl.pack(side="left", padx=(8, 0))

        # Treeview inside a padded inner frame
        tree_frame = tk.Frame(lc, bg=CARD, padx=14, pady=0)
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
        _ctx = tk.Menu(self._recordings_tree, tearoff=0,
                       bg=CARD2, fg=FG, activebackground=ACC,
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
        act_row = tk.Frame(lc, bg="#14141E", padx=14, pady=8)
        act_row.pack(fill="x")

        _BTN = dict(font=("Segoe UI", 9), relief="flat", bd=0,
                    padx=14, pady=6, cursor="hand2")
        tk.Button(act_row, text="  Play", bg=GRN, fg="white",
                  command=self._play_selected_recording, **_BTN).pack(
            side="left", padx=(0, 4))
        tk.Button(act_row, text="  Edit", bg=ACC, fg="white",
                  command=self._edit_selected_recording, **_BTN).pack(
            side="left", padx=(0, 4))
        tk.Button(act_row, text="  Hapus", bg=RED, fg="white",
                  command=self._delete_selected_recording, **_BTN).pack(
            side="left", padx=(0, 4))
        # divider
        tk.Frame(act_row, bg=MUT, width=1, height=22).pack(
            side="left", padx=(6, 10))
        tk.Button(act_row, text="Naik", bg=CARD2, fg=FG,
                  command=self._move_rec_up, **_BTN).pack(
            side="left", padx=(0, 4))
        tk.Button(act_row, text="Turun", bg=CARD2, fg=FG,
                  command=self._move_rec_down, **_BTN).pack(side="left")

        self._rec_folder_var = tk.StringVar(value="General")
        self._refresh_recordings_tree()
        return f

    # ================================================================
    #  SCHEDULE PAGE  (Macro Builder)
    # ================================================================

    def _pg_schedule(self):
        """Schedule page: toggles between list view and builder view."""
        f = tk.Frame(self._content, bg=BG)

        # -- List view --
        self._mb_list_view = tk.Frame(f, bg=BG)
        self._mb_list_view.pack(fill="both", expand=True)

        self._hdr(self._mb_list_view, "Smart Macros",
                  "Automate tasks: browser + Google Sheets + notifications.")

        top_bar = _card(self._mb_list_view)
        top_bar.pack(fill="x", padx=20, pady=(0, 8))
        tk.Button(top_bar, text="+ Create New Macro",
                  bg=ACC, fg=BG, font=("Segoe UI", 11, "bold"),
                  relief="flat", bd=0, padx=18, pady=9, cursor="hand2",
                  command=lambda: self._mb_open(parent=f)).pack(side="left")
        ttk.Button(top_bar, text="Run Now",
                   command=self._run_selected_task).pack(
            side="left", padx=(8, 0))
        ttk.Button(top_bar, text="Edit",
                   command=lambda: self._mb_open(
                       parent=f, edit_idx=self._selected_task_idx()
                   )).pack(side="left", padx=(4, 0))
        ttk.Button(top_bar, text="Toggle ON/OFF",
                   command=self._toggle_task_enabled).pack(
            side="left", padx=(4, 0))
        ttk.Button(top_bar, text="Delete", style="Danger.TButton",
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
        self._refresh_tasks_tree()
        self._start_countdown_refresh()

        # -- Builder view (hidden initially) --
        self._mb_build_view = tk.Frame(f, bg=BG)
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
        top = tk.Frame(f, bg=SIDE, height=52)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Button(top, text="< Back", bg=SIDE, fg=MUT,
                  font=("Segoe UI", 10), relief="flat", bd=0,
                  padx=12, pady=8, cursor="hand2",
                  command=self._mb_back).pack(side="left", padx=4, pady=8)
        tk.Frame(top, bg=MUT, width=1).pack(side="left", fill="y",
                                              padx=4, pady=8)
        _lbl(top, "Macro Name:", fg=MUT, bg=SIDE,
             font=("Segoe UI", 9)).pack(side="left", padx=(8, 4), pady=14)
        self._mb_name_var = tk.StringVar(
            value=existing.get("name","") if existing else "")
        name_entry = tk.Entry(top, textvariable=self._mb_name_var,
                              bg=CARD, fg=FG, insertbackground=FG,
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
        sched_cb = ttk.Combobox(
            top, textvariable=self._mb_sched_type,
            values=["manual", "interval", "daily", "hourly"],
            state="readonly", width=9)
        sched_cb.pack(side="left", padx=(0, 4), pady=14)
        ttk.Entry(top, textvariable=self._mb_sched_val,
                  width=5).pack(side="left", padx=(0, 2), pady=14)
        _lbl(top, "min / time:", fg=MUT, bg=SIDE,
             font=("Segoe UI", 8)).pack(side="left")
        ttk.Entry(top, textvariable=self._mb_sched_time,
                  width=7).pack(side="left", padx=(2, 8), pady=14)

        tk.Button(top, text="Save Macro", bg=GRN, fg=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=14, pady=7, cursor="hand2",
                  command=self._mb_save).pack(side="right", padx=12, pady=8)
        tk.Button(top, text="Test Run", bg=YEL, fg=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=14, pady=7, cursor="hand2",
                  command=self._mb_dry_run).pack(side="right", padx=(0, 2), pady=8)

        # -- Body: left panel + right panel --
        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True)

        # Left panel - step list (270px)
        left_outer = tk.Frame(body, bg=SIDE, width=270)
        left_outer.pack(side="left", fill="y")
        left_outer.pack_propagate(False)

        _lbl(left_outer, "STEPS", fg=MUT, bg=SIDE,
             font=("Segoe UI", 8, "bold")).pack(
            anchor="w", padx=12, pady=(10, 4))

        # Scrollable step list
        list_canvas = tk.Canvas(left_outer, bg=SIDE,
                                highlightthickness=0)
        list_sb = ttk.Scrollbar(left_outer, orient="vertical",
                                command=list_canvas.yview)
        list_sb.pack(side="right", fill="y")
        list_canvas.pack(side="left", fill="both", expand=True)
        list_canvas.configure(yscrollcommand=list_sb.set)

        self._mb_list_inner = tk.Frame(list_canvas, bg=SIDE)
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
        add_btn_frame = tk.Frame(left_outer, bg=SIDE, pady=6)
        add_btn_frame.pack(fill="x", side="bottom")
        tk.Button(add_btn_frame, text="+ Add Step",
                  bg=ACC, fg=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                  command=lambda: self._mb_add_step()).pack(fill="x",
                                                             padx=10)

        # Right panel - step editor
        right_outer = tk.Frame(body, bg=BG)
        right_outer.pack(side="left", fill="both", expand=True)

        self._mb_editor_frame = tk.Frame(right_outer, bg=BG)
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

            row = tk.Frame(self._mb_list_inner, bg=bg_row,
                           cursor="hand2")
            row.pack(fill="x", padx=4, pady=1)

            tk.Label(row, text="{:2}.".format(i + 1), bg=bg_row, fg=fg_row,
                     font=("Consolas", 9), width=3, anchor="e").pack(
                side="left", padx=(4, 2))
            tk.Label(row, text=icon, bg=bg_row,
                     fg=YEL if is_sel else YEL,
                     font=("Consolas", 9), width=4).pack(side="left")
            tk.Label(row, text=desc, bg=bg_row, fg=fg_row,
                     font=("Segoe UI", 9), anchor="w").pack(
                side="left", fill="x", expand=True, padx=(0, 4))

            # Test button
            def _make_test(idx=i):
                def _do():
                    self._mb_test_single_step(idx)
                return _do
            tk.Button(row, text="Test", bg=YEL, fg=BG,
                      font=("Segoe UI", 7, "bold"), relief="flat", bd=0,
                      padx=4, cursor="hand2",
                      command=_make_test()).pack(side="right", padx=1, pady=3)

            # Delete button
            def _make_del(idx=i):
                def _do():
                    self._mb_delete_step(idx)
                return _do
            tk.Button(row, text="x", bg=bg_row, fg=RED if not is_sel else BG,
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
            tk.Button(row, text="^", bg=bg_row,
                      fg=MUT if not is_sel else BG,
                      font=("Segoe UI", 7), relief="flat", bd=0, padx=3,
                      cursor="hand2",
                      command=_make_up()).pack(side="right", pady=3)
            tk.Button(row, text="v", bg=bg_row,
                      fg=MUT if not is_sel else BG,
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
             "Choose a template to get started quickly:",
             fg=MUT, bg=BG, font=("Segoe UI", 10)).pack(
            anchor="w", padx=24, pady=(20, 12))

        templates = _load_templates()
        row1 = tk.Frame(self._mb_editor_frame, bg=BG)
        row1.pack(fill="x", padx=20, pady=(0, 8))
        row2 = tk.Frame(self._mb_editor_frame, bg=BG)
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

            tc = tk.Frame(parent_row, bg=CARD, padx=16, pady=14,
                          cursor="hand2")
            tc.pack(side="left", fill="both", expand=True, padx=(0, 8))

            hrow = tk.Frame(tc, bg=CARD)
            hrow.pack(fill="x", pady=(0, 6))
            tk.Label(hrow, text=ic, bg=CARD, fg=clr,
                     font=("Consolas", 14, "bold")).pack(side="left",
                                                          padx=(0, 10))
            _lbl(hrow, tmpl["name"], fg=clr, bg=CARD,
                 font=("Segoe UI", 10, "bold")).pack(side="left")

            _lbl(tc, tmpl.get("description",""), fg=MUT, bg=CARD,
                 font=("Segoe UI", 8), wraplength=220,
                 justify="left").pack(anchor="w", pady=(0, 8))

            steps = tmpl.get("steps", [])
            for s in steps[:4]:
                step_ic = _STEP_ICONS.get(s.get("type",""), "[?]")
                _lbl(tc, "{}  {}".format(step_ic, _step_label(s)[:28]),
                     fg=MUT, bg=CARD,
                     font=("Consolas", 8)).pack(anchor="w")
            if len(steps) > 4:
                _lbl(tc, "  ... +{} more steps".format(len(steps)-4),
                     fg=MUT, bg=CARD, font=("Segoe UI", 8)).pack(anchor="w")

            tk.Button(tc, text="Use This Template",
                      bg=clr, fg=BG,
                      font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                      padx=10, pady=5, cursor="hand2",
                      command=_use_tmpl).pack(anchor="w", pady=(10, 0))

        # OR start blank
        blank = tk.Frame(self._mb_editor_frame, bg=CARD, padx=16,
                         pady=14, cursor="hand2")
        blank.pack(fill="x", padx=20, pady=(12, 0))
        brow = tk.Frame(blank, bg=CARD)
        brow.pack(fill="x", pady=(0, 6))
        tk.Label(brow, text="[+]", bg=CARD, fg=FG,
                 font=("Consolas", 14, "bold")).pack(side="left",
                                                      padx=(0, 10))
        _lbl(brow, "Start from scratch", fg=FG, bg=CARD,
             font=("Segoe UI", 10, "bold")).pack(side="left")
        _lbl(blank, "Build your own macro step by step with any combination "
             "of actions.", fg=MUT, bg=CARD, font=("Segoe UI", 8),
             wraplength=400, justify="left").pack(anchor="w", pady=(0, 8))
        tk.Button(blank, text="+ Add First Step",
                  bg=FG, fg=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                  command=self._mb_add_step).pack(anchor="w")

    def _mb_build_editor(self, step_type, existing=None, step_idx=None):
        """Build the step editor in the right panel."""
        for w in self._mb_editor_frame.winfo_children():
            w.destroy()
        self._mb_field_vars = {}
        self._mb_type_var   = tk.StringVar(value=step_type)

        # -- Step type selector --
        type_frame = tk.Frame(self._mb_editor_frame, bg=BG)
        type_frame.pack(fill="x", padx=20, pady=(16, 8))
        _lbl(type_frame, "Step Type:", fg=MUT, bg=BG,
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
        ]
        display_names = [d for _, d in TYPE_OPTIONS]
        type_to_key   = {d: k for k, d in TYPE_OPTIONS}
        key_to_disp   = {k: d for k, d in TYPE_OPTIONS}

        curr_disp = key_to_disp.get(step_type, display_names[0])
        disp_var  = tk.StringVar(value=curr_disp)

        type_cb = ttk.Combobox(type_frame, textvariable=disp_var,
                               values=display_names, state="readonly",
                               width=28, font=("Segoe UI", 10))
        type_cb.pack(anchor="w")

        # -- Fields area --
        fields_outer = tk.Frame(self._mb_editor_frame, bg=BG)
        fields_outer.pack(fill="both", expand=True, padx=20, pady=(4, 0))

        # Scroll for fields
        fc = tk.Canvas(fields_outer, bg=BG, highlightthickness=0)
        fsb = ttk.Scrollbar(fields_outer, orient="vertical",
                            command=fc.yview)
        fsb.pack(side="right", fill="y")
        fc.pack(side="left", fill="both", expand=True)
        fc.configure(yscrollcommand=fsb.set)
        fields_inner = tk.Frame(fc, bg=BG)
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
            f = tk.Frame(parent, bg=BG)
            f.pack(fill="x", pady=(0, 10))
            _lbl(f, label, fg=FG, bg=BG,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 2))
            val = tk.StringVar(value=existing.get(key, default))
            if multiline:
                txt = tk.Text(f, bg=CARD, fg=FG, insertbackground=FG,
                              font=("Segoe UI", 10), relief="flat",
                              height=height, wrap="word")
                txt.insert("1.0", existing.get(key, default))
                txt.pack(fill="x")
                self._mb_field_vars[key] = txt
            else:
                entry = tk.Entry(f, textvariable=val, bg=CARD, fg=FG,
                                 insertbackground=FG, font=("Segoe UI", 10),
                                 relief="flat")
                entry.pack(fill="x", ipady=6)
                self._mb_field_vars[key] = val
            if helper:
                _lbl(f, helper, fg=MUT, bg=BG,
                     font=("Segoe UI", 8)).pack(anchor="w")
            return val

        def _spy_button(selector_key):
            """Add a 'USE SPY TO PICK' button that fills selector_key."""
            row = tk.Frame(parent, bg=BG)
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

            tk.Button(row, text="USE SPY TO PICK",
                      bg=PRP, fg=BG, font=("Segoe UI", 9, "bold"),
                      relief="flat", bd=0, padx=12, pady=6,
                      cursor="hand2", command=_do_spy_pick).pack(
                side="left")
            _lbl(row, "Hover over element in Chrome, click USE IN MACRO",
                 fg=MUT, bg=BG, font=("Segoe UI", 8)).pack(
                side="left", padx=8)

        # -- Per step type fields --
        if step_type == "go_to_url":
            _field("Website URL", "url", "https://",
                   helper="Tip: Copy the exact URL from your browser address bar")
            row = tk.Frame(parent, bg=BG)
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
            tk.Button(row, text="Open in Browser",
                      bg=CARD, fg=FG, font=("Segoe UI", 9),
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
            _lbl(parent, "Will click: [selector shown above]",
                 fg=MUT, bg=BG, font=("Segoe UI", 8)).pack(anchor="w",
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
            _lbl(parent, 'Example: Write {price} to cell B2',
                 fg=MUT, bg=BG, font=("Segoe UI", 8)).pack(
                anchor="w", pady=(0, 8))

        elif step_type == "if_equals":
            _field("Variable or value", "value1", "",
                   helper='Use {variable_name} or literal text')
            _field("Equals what?", "value2", "",
                   helper="Leave empty to check if variable is blank")
            f_cond = tk.Frame(parent, bg=BG)
            f_cond.pack(fill="x", pady=(0, 10))
            _lbl(f_cond, "If FALSE, then:", fg=MUT, bg=BG,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))
            act_var = tk.StringVar(
                value=existing.get("action_false", "stop"))
            self._mb_field_vars["action_false"] = act_var
            for val, label in [("stop", "Stop macro"),
                                ("skip", "Skip next step"),
                                ("continue", "Continue anyway")]:
                tk.Radiobutton(f_cond, text=label, variable=act_var,
                               value=val, bg=BG, fg=FG,
                               selectcolor=CARD, activebackground=BG,
                               activeforeground=ACC,
                               font=("Segoe UI", 9)).pack(anchor="w")

        elif step_type == "if_contains":
            _field("Text or variable", "text", "",
                   helper='Use {variable_name} to check a captured value')
            _field("Contains what?", "keyword", "",
                   helper='Example: Habis, Out of Stock, Error')
            f_true = tk.Frame(parent, bg=BG)
            f_true.pack(fill="x", pady=(0, 6))
            _lbl(f_true, "If TRUE, then:", fg=MUT, bg=BG,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))
            act_true = tk.StringVar(
                value=existing.get("action_true", "notify"))
            self._mb_field_vars["action_true"] = act_true
            for val, lbl in [("notify", "Send notification"),
                              ("skip",   "Skip next step"),
                              ("stop",   "Stop macro")]:
                tk.Radiobutton(f_true, text=lbl, variable=act_true,
                               value=val, bg=BG, fg=FG, selectcolor=CARD,
                               activebackground=BG, activeforeground=ACC,
                               font=("Segoe UI", 9)).pack(anchor="w")
            _field("Notification message", "notify_message", "",
                   helper="Shown when condition is true. Supports {variables}")

        elif step_type == "notify":
            _field("Message", "message", "",
                   helper="Supports {variables}. Example: Price updated: {price}")
            f_type = tk.Frame(parent, bg=BG)
            f_type.pack(fill="x", pady=(0, 10))
            _lbl(f_type, "Notification type:", fg=MUT, bg=BG,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))
            ntype = tk.StringVar(value=existing.get("notify_type", "popup"))
            self._mb_field_vars["notify_type"] = ntype
            for val, lbl in [("popup", "Popup message"),
                              ("sound", "Sound only"),
                              ("both",  "Popup + Sound")]:
                tk.Radiobutton(f_type, text=lbl, variable=ntype,
                               value=val, bg=BG, fg=FG, selectcolor=CARD,
                               activebackground=BG, activeforeground=ACC,
                               font=("Segoe UI", 9)).pack(anchor="w")

        else:
            _field("Value / Selector", "value", existing.get("value",""))

    def _mb_build_editor_actions(self, parent, step_idx):
        """Add Apply / Insert Below buttons at bottom of editor."""
        row = tk.Frame(parent, bg=BG)
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

        tk.Button(row, text="Apply Changes", bg=GRN, fg=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=14, pady=7, cursor="hand2",
                  command=_apply).pack(side="left", padx=(0, 8))
        tk.Button(row, text="+ Insert Step Below",
                  bg=CARD, fg=FG, font=("Segoe UI", 9),
                  relief="flat", bd=0, padx=10, pady=7, cursor="hand2",
                  command=_insert_below).pack(side="left")

    def _mb_save(self):
        """Save macro and return to list."""
        name = self._mb_name_var.get().strip() if self._mb_name_var else ""
        if not name:
            messagebox.showwarning("Macro Name",
                                   "Please enter a macro name.",
                                   parent=self._root)
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
            messagebox.showinfo("Test Run", "No steps to run.",
                                parent=self._root)
            return
        if not self.engine:
            messagebox.showwarning("Test Run",
                                   "Engine not connected. Browser/Sheets "
                                   "steps will fail, but logic steps will work.",
                                   parent=self._root)

        task = {"name": self._mb_name_var.get() or "Dry Run",
                "steps": list(self._mb_steps)}
        stop_ev = threading.Event()

        # -- Dry run panel (extends progress panel) --
        panel = self._show_run_progress_panel(task, stop_ev)
        w = panel["window"]
        w.title("Dry Run: {}".format(task["name"]))

        # Extra info banner
        info = tk.Label(w, text="DRY RUN  -  Sheet writes are simulated",
                        bg=YEL, fg=BG, font=("Segoe UI", 9, "bold"),
                        padx=10, pady=4)
        info.pack(fill="x", before=panel["step_lbl"])

        # Per-step confirm controls
        ctrl = tk.Frame(w, bg=BG)
        ctrl.pack(fill="x", padx=16, pady=(0, 4))
        confirm_var = tk.StringVar(value="waiting")

        next_btn = tk.Button(ctrl, text="Execute Step", bg=GRN, fg=BG,
                             font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                             padx=10, pady=4, cursor="hand2",
                             command=lambda: confirm_var.set("yes"),
                             state="disabled")
        next_btn.pack(side="left", padx=(0, 6))
        skip_btn = tk.Button(ctrl, text="Skip", bg=CARD, fg=FG,
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
                self._root.after(0, lambda idx=i: self._mb_highlight_step(idx))

                # Update panel label and wait for confirm
                lbl = "Step {}/{}: {}  -  OK to execute?".format(
                    i + 1, len(self._mb_steps), step_desc[:40])
                self._root.after(0, lambda t=lbl: panel["step_lbl"].configure(text=t))
                self._root.after(0, _enable_confirm)
                self._root.after(0, _watch_confirm)

                confirm_event.clear()
                confirm_event.wait()

                if confirm_result[0] == "skip":
                    msg = "Step {}: [SKIPPED]\n".format(i + 1)
                    self._root.after(0, lambda m=msg: [
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
                self._root.after(0, lambda m=msg, t=tag: [
                    panel["log_box"].configure(state="normal"),
                    panel["log_box"].insert(tk.END, m, t),
                    panel["log_box"].see(tk.END),
                    panel["log_box"].configure(state="disabled"),
                ])
                panel["progress_var"].set(i + 1)

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
            self._root.after(0, lambda s=summary: [
                panel["step_lbl"].configure(text=s),
                self._toast_success(s) if fail_count == 0 else self._toast_warning(s),
                self._mb_highlight_step(-1),  # clear highlight
            ])
            self._root.after(0, lambda: panel["stop_btn"].configure(
                state="disabled", text="Done"))

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
                row.configure(bg=bg)
                for child in row.winfo_children():
                    try:
                        child.configure(bg=bg)
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
        w = tk.Toplevel(self._root)
        w.title("Step Test: {}".format(_step_label(step)[:40]))
        w.configure(bg=BG)
        w.geometry("400x180")
        w.attributes("-topmost", True)
        w.resizable(False, False)

        tk.Label(w, text="Testing: {}".format(_step_label(step)[:50]),
                 bg=BG, fg=FG, font=("Segoe UI", 10, "bold"),
                 padx=16, pady=10, anchor="w").pack(fill="x")
        status_lbl = tk.Label(w, text="Running...",
                              bg=BG, fg=MUT, font=("Segoe UI", 9),
                              padx=16, anchor="w")
        status_lbl.pack(fill="x")
        result_lbl = tk.Label(w, text="",
                              bg=CARD, fg=FG, font=("Consolas", 9),
                              padx=12, pady=8, anchor="w", wraplength=370,
                              justify="left")
        result_lbl.pack(fill="x", padx=16, pady=(6, 0))
        ttk.Button(w, text="Close", command=w.destroy).pack(pady=10)

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
                        text="OK" if ok else "FAILED",
                        fg=GRN if ok else RED,
                        font=("Segoe UI", 10, "bold"))
                    result_lbl.configure(text=result_text)
                except Exception:
                    pass
            self._root.after(0, _show)

        threading.Thread(target=_run, daemon=True).start()

    # ================================================================
    #  SHEET PAGE  (Connected Sheets)
    # ================================================================

    def _pg_sheet(self):
        from modules.sheets import connector as _sc
        f = tk.Frame(self._content, bg=BG)
        self._hdr(f, "Google Sheets",
                  "Connect sheets, preview data, and write values.")

        scroll_canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(f, orient="vertical",
                                  command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(scroll_canvas, bg=BG)
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
             "(credentials.json). Follow the steps below to get one for free.",
             fg=MUT, bg=CARD, font=("Segoe UI", 9), justify="left").pack(
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
             "The wizard will guide you through every step.",
             fg=MUT, bg=CARD, font=("Segoe UI", 9), justify="left").pack(
            anchor="w", pady=(0, 16))
        tk.Button(
            empty_card, text="+ Connect First Sheet",
            bg=ACC, fg=BG, font=("Segoe UI", 11, "bold"),
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

        btn_row = tk.Frame(conn_card, bg=CARD)
        btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_row, text="Preview",
                   command=self._sheet_btn_preview).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Test",
                   command=self._sheet_test).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Remove", style="Danger.TButton",
                   command=self._sheet_remove).pack(side="left")
        tk.Button(btn_row, text="+ Add Sheet",
                  bg=ACC, fg=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=4, cursor="hand2",
                  command=self._sheet_launch_wizard).pack(side="right")
        self._refresh_sheets_tree()

        # -- Data Preview --
        prev_card = _card(parent, "Data Preview")
        prev_card.pack(fill="x", padx=20, pady=(0, 8))

        prev_ctrl = tk.Frame(prev_card, bg=CARD)
        prev_ctrl.pack(fill="x", pady=(0, 8))
        _lbl(prev_ctrl, "Sheet:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._prev_sheet_var = tk.StringVar()
        self._prev_sheet_cb  = ttk.Combobox(
            prev_ctrl, textvariable=self._prev_sheet_var,
            values=[s.get("name","") for s in self._ud.sheets],
            state="readonly", width=18)
        self._prev_sheet_cb.pack(side="left", padx=(4, 16))

        _lbl(prev_ctrl, "Tab:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._prev_ws_var = tk.StringVar()
        self._prev_ws_cb  = ttk.Combobox(
            prev_ctrl, textvariable=self._prev_ws_var,
            state="readonly", width=14)
        self._prev_ws_cb.pack(side="left", padx=(4, 16))
        self._prev_sheet_cb.bind(
            "<<ComboboxSelected>>", self._on_prev_sheet_change)

        ttk.Button(prev_ctrl, text="Refresh",
                   command=self._sheet_preview_refresh).pack(side="left")

        self._sheet_preview_frame = tk.Frame(prev_card, bg=CARD)
        self._sheet_preview_frame.pack(fill="x")
        _lbl(self._sheet_preview_frame,
             "Select a connected sheet and click Refresh to preview data.",
             fg=MUT, bg=CARD, font=("Segoe UI", 9)).pack(anchor="w")

        # Cell reader row
        cell_row = tk.Frame(prev_card, bg=CARD)
        cell_row.pack(fill="x", pady=(10, 0))
        _lbl(cell_row, "Read cell:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._prev_cell_var = tk.StringVar(value="A1")
        ttk.Entry(cell_row, textvariable=self._prev_cell_var,
                  width=6).pack(side="left", padx=(4, 8))
        ttk.Button(cell_row, text="Read",
                   command=self._sheet_read_cell).pack(side="left")
        self._cell_result_lbl = _lbl(cell_row, "", fg=GRN, bg=CARD,
                                     font=("Segoe UI", 9))
        self._cell_result_lbl.pack(side="left", padx=(10, 0))

        # -- Quick Actions --
        qa_card = _card(parent, "Quick Actions")
        qa_card.pack(fill="x", padx=20, pady=(0, 8))

        # Read cell row
        _lbl(qa_card, "Read Cell", fg=ACC, bg=CARD,
             font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        rc_row = tk.Frame(qa_card, bg=CARD)
        rc_row.pack(fill="x", pady=(0, 10))
        _lbl(rc_row, "Sheet:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._rc_sheet_var = tk.StringVar()
        ttk.Combobox(rc_row, textvariable=self._rc_sheet_var,
                     values=[s.get("name","") for s in self._ud.sheets],
                     state="readonly", width=16).pack(side="left", padx=(4, 10))
        _lbl(rc_row, "Cell:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._rc_cell_var = tk.StringVar(value="A1")
        ttk.Entry(rc_row, textvariable=self._rc_cell_var,
                  width=6).pack(side="left", padx=(4, 8))
        ttk.Button(rc_row, text="Read",
                   command=self._sheet_qa_read).pack(side="left")
        self._rc_result_lbl = _lbl(rc_row, "", fg=GRN, bg=CARD,
                                   font=("Segoe UI", 9))
        self._rc_result_lbl.pack(side="left", padx=(10, 0))

        # Write cell row
        _lbl(qa_card, "Write Cell", fg=ACC, bg=CARD,
             font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        wc_row1 = tk.Frame(qa_card, bg=CARD)
        wc_row1.pack(fill="x", pady=(0, 4))
        _lbl(wc_row1, "Sheet:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._wc_sheet_var = tk.StringVar()
        ttk.Combobox(wc_row1, textvariable=self._wc_sheet_var,
                     values=[s.get("name","") for s in self._ud.sheets],
                     state="readonly", width=16).pack(side="left", padx=(4, 10))
        _lbl(wc_row1, "Cell:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._wc_cell_var = tk.StringVar(value="A1")
        ttk.Entry(wc_row1, textvariable=self._wc_cell_var,
                  width=6).pack(side="left", padx=(4, 0))
        wc_row2 = tk.Frame(qa_card, bg=CARD)
        wc_row2.pack(fill="x", pady=(0, 10))
        _lbl(wc_row2, "Value:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._wc_val_var = tk.StringVar()
        ttk.Entry(wc_row2, textvariable=self._wc_val_var,
                  font=("Segoe UI", 9)).pack(
            side="left", fill="x", expand=True, padx=(4, 8))
        tk.Button(wc_row2, text="Write Now",
                  bg=GRN, fg=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=4, cursor="hand2",
                  command=self._sheet_qa_write).pack(side="left")

        # Append row
        _lbl(qa_card, "Append Row", fg=ACC, bg=CARD,
             font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        ar_row1 = tk.Frame(qa_card, bg=CARD)
        ar_row1.pack(fill="x", pady=(0, 4))
        _lbl(ar_row1, "Sheet:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._ar_sheet_var = tk.StringVar()
        ttk.Combobox(ar_row1, textvariable=self._ar_sheet_var,
                     values=[s.get("name","") for s in self._ud.sheets],
                     state="readonly", width=16).pack(side="left", padx=(4, 0))
        ar_row2 = tk.Frame(qa_card, bg=CARD)
        ar_row2.pack(fill="x", pady=(0, 4))
        _lbl(ar_row2, "Values (comma-separated):", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left")
        self._ar_vals_var = tk.StringVar()
        ttk.Entry(ar_row2, textvariable=self._ar_vals_var,
                  font=("Segoe UI", 9)).pack(
            side="left", fill="x", expand=True, padx=(8, 8))
        tk.Button(ar_row2, text="Append",
                  bg=ACC, fg=BG, font=("Segoe UI", 9, "bold"),
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
                    messagebox.showinfo("Already Connected",
                                       "This sheet is already connected.",
                                       parent=self._root)
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
            messagebox.showinfo("Preview", "Select a sheet first.",
                                parent=self._root)
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
        if messagebox.askyesno("Remove Sheet",
                               "Remove sheet '{}'?\n\n"
                               "This only removes it from Synthex. "
                               "Your actual Google Sheet is not affected.".format(name),
                               parent=self._root):
            del self._ud.sheets[idx]
            self._ud.save()
            self._navigate("sheet")

    def _sheet_test(self):
        if not hasattr(self, "_sheets_tree"):
            return
        sel = self._sheets_tree.selection()
        if not sel:
            messagebox.showinfo("Test", "Select a sheet first.",
                                parent=self._root)
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
            messagebox.showinfo("Read Cell", "Select a sheet first.",
                                parent=self._root)
            return
        self._cell_result_lbl.configure(text="Reading...", fg=MUT)

        def _do():
            from modules.sheets import connector as _sc
            val, err = _sc.read_cell(self._ud.sheets, name, cell)
            if err:
                self._root.after(0, lambda: self._cell_result_lbl.configure(
                    text=err, fg=RED))
            else:
                self._root.after(0, lambda: self._cell_result_lbl.configure(
                    text=val or "(empty)", fg=GRN))
        threading.Thread(target=_do, daemon=True).start()

    def _sheet_preview_refresh(self):
        if not hasattr(self, "_prev_sheet_var"):
            return
        sheet_name = self._prev_sheet_var.get()
        if not sheet_name:
            messagebox.showinfo("Preview", "Select a sheet first.",
                                parent=self._root)
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
        _lbl(self._sheet_preview_frame, "Loading...",
             fg=MUT, bg=CARD, font=("Segoe UI", 9)).pack(anchor="w")

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
            _lbl(self._sheet_preview_frame, err, fg=RED, bg=CARD,
                 font=("Segoe UI", 9), justify="left",
                 wraplength=560).pack(anchor="w")
            return
        if rows:
            tbl = tk.Frame(self._sheet_preview_frame, bg=CARD)
            tbl.pack(fill="x")
            max_cols = min(max(len(r) for r in rows), 10)
            for ri, row in enumerate(rows[:15]):
                for ci in range(max_cols):
                    val = row[ci] if ci < len(row) else ""
                    bg  = SIDE if ri == 0 else CARD
                    tk.Label(tbl, text=str(val)[:20], bg=bg,
                             fg=ACC if ri == 0 else FG,
                             font=("Segoe UI", 8),
                             relief="flat", padx=6, pady=3,
                             borderwidth=1).grid(row=ri, column=ci, sticky="w")
        else:
            _lbl(self._sheet_preview_frame,
                 "No data available. Make sure the sheet has data and access is correct.",
                 fg=MUT, bg=CARD, font=("Segoe UI", 9)).pack(anchor="w")

    # -- Quick Action handlers --

    def _sheet_qa_read(self):
        name = self._rc_sheet_var.get()
        cell = self._rc_cell_var.get().strip() or "A1"
        if not name:
            messagebox.showwarning("Read Cell", "Select a sheet first.",
                                   parent=self._root)
            return
        self._rc_result_lbl.configure(text="Reading...", fg=MUT)

        def _do():
            from modules.sheets import connector as _sc
            val, err = _sc.read_cell(self._ud.sheets, name, cell)
            if err:
                self._root.after(0, lambda: self._rc_result_lbl.configure(
                    text=err, fg=RED))
            else:
                self._root.after(0, lambda: self._rc_result_lbl.configure(
                    text=repr(val) if val else "(empty)", fg=GRN))
        threading.Thread(target=_do, daemon=True).start()

    def _sheet_qa_write(self):
        name  = self._wc_sheet_var.get()
        cell  = self._wc_cell_var.get().strip()
        value = self._wc_val_var.get()
        if not name or not cell:
            messagebox.showwarning("Write Cell",
                                   "Select a sheet and enter a cell address.",
                                   parent=self._root)
            return
        now = datetime.now()
        value = value.replace("{current_date}", now.strftime("%Y-%m-%d"))
        value = value.replace("{current_time}", now.strftime("%H:%M:%S"))
        if not messagebox.askyesno(
            "Confirm Write",
            "Write '{}' to cell {} in '{}'?".format(value, cell, name),
            parent=self._root,
        ):
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
            messagebox.showwarning("Append Row",
                                   "Select a sheet and enter values.",
                                   parent=self._root)
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
        f = tk.Frame(self._content, bg=BG)

        # ── HEADER ────────────────────────────────────────────────────────────
        hdr_frame = tk.Frame(f, bg=BG)
        hdr_frame.pack(fill="x", padx=24, pady=(18, 6))
        tk.Label(hdr_frame, text="\U0001f3e6 Cek Rekening", bg=BG, fg=ACC,
                 font=("Segoe UI", 16, "bold"), anchor="w").pack(anchor="w")
        tk.Label(hdr_frame, text="Cek informasi pemilik rekening bank",
                 bg=BG, fg=MUT, font=("Segoe UI", 9), anchor="w").pack(anchor="w")

        # ── BODY: split layout ────────────────────────────────────────────────
        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # ── LEFT: input (~420px) ──────────────────────────────────────────────
        left = tk.Frame(body, bg=CARD, width=420, padx=16, pady=14)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        # Top accent
        tk.Frame(left, bg=ACC, height=3).pack(fill="x", pady=(0, 10))

        tk.Label(left, text="Nomor Rekening (satu per baris):",
                 bg=CARD, fg=MUT, font=("Segoe UI", 8, "bold"),
                 anchor="w").pack(anchor="w", pady=(0, 4))

        txt = scrolledtext.ScrolledText(
            left, bg=BG, fg=FG, insertbackground=FG,
            font=("Consolas", 10), relief="flat", bd=0,
            height=12, wrap="none",
            selectbackground=ACC, selectforeground=BG)
        txt.pack(fill="x")
        txt.insert("1.0", "BCA 1234567890\nBNI 0987654321\nMANDIRI 1122334455")

        # Button row
        btn_row = tk.Frame(left, bg=CARD)
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

        run_btn = tk.Button(btn_row, text="Cek Semua",
                            bg=ACC, fg=BG, font=("Segoe UI", 9, "bold"),
                            relief="flat", bd=0, padx=12, pady=6,
                            cursor="hand2", command=_do_check)
        run_btn.pack(side="left", padx=(0, 6))

        stop_btn = tk.Button(btn_row, text="Stop",
                             bg=CARD, fg=RED, font=("Segoe UI", 9),
                             relief="flat", bd=0, padx=12, pady=6,
                             cursor="hand2", command=_do_stop,
                             state="disabled")
        stop_btn.pack(side="left", padx=(0, 6))

        tk.Button(btn_row, text="Clear",
                  bg=CARD, fg=MUT, font=("Segoe UI", 9),
                  relief="flat", bd=0, padx=12, pady=6,
                  cursor="hand2", command=_do_clear).pack(side="left")

        # Hint
        tk.Label(left, text="Double-klik baris untuk menyalin nama",
                 bg=CARD, fg=MUT, font=("Segoe UI", 7),
                 anchor="w").pack(anchor="w", pady=(8, 0))

        # ── RIGHT: results ────────────────────────────────────────────────────
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        res_hdr = tk.Frame(right, bg=BG)
        res_hdr.pack(fill="x", pady=(0, 6))
        tk.Label(res_hdr, text="Hasil Pengecekan", bg=BG, fg=FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(anchor="w")

        tree_frame = tk.Frame(right, bg=CARD)
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

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
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

        f = tk.Frame(self._content, bg=BG)
        self._hdr(f, "Dashboard Update")

        # State: satu instance PriceMonitor per session
        if not hasattr(self, "_price_monitor"):
            self._price_monitor = None

        # ── Outer scroll area ─────────────────────────────────────────────────
        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # ── Konfigurasi ───────────────────────────────────────────────────────
        cfg_card = _card(body, "Konfigurasi")
        cfg_card.pack(fill="x", pady=(8, 0))

        def _row(parent, label, widget_fn):
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", padx=10, pady=3)
            tk.Label(row, text=label, bg=CARD, fg=MUT,
                     font=("Segoe UI", 9), width=22, anchor="w").pack(
                         side="left", padx=(0, 6))
            w = widget_fn(row)
            w.pack(side="left", fill="x", expand=True)
            return w

        # URL
        v_url = tk.StringVar()
        _row(cfg_card, "URL Halaman *",
             lambda p: tk.Entry(p, textvariable=v_url, bg=CARD2, fg=FG,
                                insertbackground=FG, relief="flat", font=("Segoe UI", 9)))

        # Tombol refresh selector
        v_btn = tk.StringVar()
        btn_entry = _row(cfg_card, "Selector Tombol Refresh",
                         lambda p: tk.Entry(p, textvariable=v_btn, bg=CARD2, fg=FG,
                                            insertbackground=FG, relief="flat",
                                            font=("Segoe UI", 9)))
        tk.Label(cfg_card, text="   (kosongkan jika tidak ada tombol refresh)",
                 bg=CARD, fg=MUT, font=("Segoe UI", 8)).pack(anchor="w", padx=10)

        # Selector tabel
        v_tbl = tk.StringVar(value="table")
        _row(cfg_card, "Selector Tabel *",
             lambda p: tk.Entry(p, textvariable=v_tbl, bg=CARD2, fg=FG,
                                insertbackground=FG, relief="flat", font=("Segoe UI", 9)))

        # Mode
        v_mode = tk.StringVar(value="requests")
        mode_row = tk.Frame(cfg_card, bg=CARD)
        mode_row.pack(fill="x", padx=10, pady=3)
        tk.Label(mode_row, text="Mode Browser", bg=CARD, fg=MUT,
                 font=("Segoe UI", 9), width=22, anchor="w").pack(side="left")
        for txt, val in [("Requests (halaman statis)", "requests"),
                         ("Headless Chrome (JS/dinamis)", "headless")]:
            tk.Radiobutton(mode_row, text=txt, variable=v_mode, value=val,
                           bg=CARD, fg=FG, selectcolor=CARD2,
                           activebackground=CARD, activeforeground=FG,
                           font=("Segoe UI", 9)).pack(side="left", padx=(0, 12))

        tk.Label(cfg_card,
                 text="   Headless = browser tersembunyi, tidak muncul di layar. "
                      "Tab browser kamu bisa diminimize.",
                 bg=CARD, fg=YEL, font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(0, 4))

        # Interval
        v_interval = tk.StringVar(value="5")
        intv_row = tk.Frame(cfg_card, bg=CARD)
        intv_row.pack(fill="x", padx=10, pady=3)
        tk.Label(intv_row, text="Interval (menit) *", bg=CARD, fg=MUT,
                 font=("Segoe UI", 9), width=22, anchor="w").pack(side="left")
        tk.Spinbox(intv_row, from_=1, to=1440, textvariable=v_interval,
                   width=6, bg=CARD2, fg=FG, buttonbackground=CARD2,
                   relief="flat", font=("Segoe UI", 9)).pack(side="left")
        tk.Label(intv_row, text="menit", bg=CARD, fg=MUT,
                 font=("Segoe UI", 9)).pack(side="left", padx=4)

        # ── Google Sheet ──────────────────────────────────────────────────────
        sheet_card = _card(body, "Google Sheet Tujuan")
        sheet_card.pack(fill="x", pady=(10, 0))

        v_sheet_id = tk.StringVar()
        _row(sheet_card, "Sheet ID / URL *",
             lambda p: tk.Entry(p, textvariable=v_sheet_id, bg=CARD2, fg=FG,
                                insertbackground=FG, relief="flat", font=("Segoe UI", 9)))

        v_ws = tk.StringVar(value="Sheet1")
        _row(sheet_card, "Nama Worksheet",
             lambda p: tk.Entry(p, textvariable=v_ws, bg=CARD2, fg=FG,
                                insertbackground=FG, relief="flat", font=("Segoe UI", 9)))

        v_cell = tk.StringVar(value="A1")
        _row(sheet_card, "Mulai dari sel",
             lambda p: tk.Entry(p, textvariable=v_cell, bg=CARD2, fg=FG,
                                insertbackground=FG, relief="flat", font=("Segoe UI", 9)))

        v_clear = tk.BooleanVar(value=True)
        tk.Checkbutton(sheet_card, text="Hapus isi sheet sebelum update",
                       variable=v_clear, bg=CARD, fg=FG,
                       selectcolor=CARD2, activebackground=CARD,
                       activeforeground=FG, font=("Segoe UI", 9)).pack(
                           anchor="w", padx=10, pady=(0, 6))

        # ── Status & log ──────────────────────────────────────────────────────
        ctrl_card = _card(body, "Status & Kontrol")
        ctrl_card.pack(fill="both", expand=True, pady=(10, 0))

        # Stats row
        stats_row = tk.Frame(ctrl_card, bg=CARD)
        stats_row.pack(fill="x", padx=10, pady=(6, 4))

        v_status_lbl  = tk.StringVar(value="Belum berjalan")
        v_last_update = tk.StringVar(value="-")
        v_cycle_count = tk.StringVar(value="0")

        tk.Label(stats_row, text="Status:", bg=CARD, fg=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Label(stats_row, textvariable=v_status_lbl, bg=CARD, fg=YEL,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(4, 20))
        tk.Label(stats_row, text="Siklus:", bg=CARD, fg=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Label(stats_row, textvariable=v_cycle_count, bg=CARD, fg=FG,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(4, 20))
        tk.Label(stats_row, text="Update terakhir:", bg=CARD, fg=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Label(stats_row, textvariable=v_last_update, bg=CARD, fg=GRN,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=4)

        # Log box
        log_frame = tk.Frame(ctrl_card, bg=CARD2, relief="flat")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        log_txt = tk.Text(log_frame, height=7, bg=CARD2, fg=FG,
                          font=("Consolas", 8), relief="flat",
                          state="disabled", wrap="word")
        log_scroll = tk.Scrollbar(log_frame, command=log_txt.yview,
                                  bg=CARD2, troughcolor=CARD2)
        log_txt.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        log_txt.pack(fill="both", expand=True, padx=4, pady=4)

        # Preview tabel
        prev_card = _card(body, "Preview Data Terakhir")
        prev_card.pack(fill="both", expand=True, pady=(10, 0))

        prev_txt = tk.Text(prev_card, height=6, bg=CARD2, fg=GRN,
                           font=("Consolas", 8), relief="flat",
                           state="disabled", wrap="none")
        prev_scroll_y = tk.Scrollbar(prev_card, command=prev_txt.yview,
                                     bg=CARD2, troughcolor=CARD2)
        prev_scroll_x = tk.Scrollbar(prev_card, orient="horizontal",
                                     command=prev_txt.xview,
                                     bg=CARD2, troughcolor=CARD2)
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

        btn_row = tk.Frame(ctrl_card, bg=CARD)
        btn_row.pack(fill="x", padx=10, pady=(0, 8))

        def _build_monitor():
            """Read config vars and create/reconfigure PriceMonitor."""
            url = v_url.get().strip()
            if not url:
                messagebox.showwarning("Dashboard Update",
                                       "URL wajib diisi.", parent=self._root)
                return None
            if not url.startswith(("http://", "https://")):
                messagebox.showwarning("Dashboard Update",
                                       "URL harus dimulai dengan http:// atau https://",
                                       parent=self._root)
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

        btn_start = tk.Button(btn_row, text="MULAI MONITOR", bg=GRN, fg=BG,
                              font=("Segoe UI", 10, "bold"), relief="flat",
                              padx=14, pady=6, cursor="hand2")
        btn_stop  = tk.Button(btn_row, text="STOP", bg=RED, fg="#fff",
                              font=("Segoe UI", 10, "bold"), relief="flat",
                              padx=14, pady=6, cursor="hand2",
                              state="disabled")
        btn_once  = tk.Button(btn_row, text="JALANKAN SEKALI", bg=ACC2, fg="#fff",
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

        return f

    # ================================================================
    #  REMOTE PAGE  (ADB Mirror via scrcpy)
    # ================================================================

    def _pg_remote(self):
        import threading as _thr
        import os as _os

        f = tk.Frame(self._content, bg=BG)
        self._hdr(f, "Mirror HP",
                  "\"Your phone, your screen — anywhere you work.\"")

        _FB = dict(relief="flat", bd=0, cursor="hand2")

        # ── scrollable body ──────────────────────────────────────────────────
        sb = ttk.Scrollbar(f, orient="vertical")
        sb.pack(side="right", fill="y")
        cv = tk.Canvas(f, bg=BG, highlightthickness=0,
                       yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.config(command=cv.yview)
        body = tk.Frame(cv, bg=BG)
        _wid = cv.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>",
                lambda e: cv.itemconfig(_wid, width=e.width))

        def _sec(title, accent=ACC):
            w = tk.Frame(body, bg=CARD)
            w.pack(fill="x", padx=20, pady=(0, 12))
            h = tk.Frame(w, bg=accent, padx=14, pady=8)
            h.pack(fill="x")
            tk.Label(h, text=title, bg=accent, fg="white",
                     font=("Segoe UI", 10, "bold")).pack(side="left")
            b = tk.Frame(w, bg=CARD, padx=14, pady=10)
            b.pack(fill="x")
            return b

        # ── TOP SPACER ──────────────────────────────────────────────────────
        tk.Frame(body, bg=BG, height=8).pack()

        # ═══════════════════════════════════════════════════════
        # SECTION 1 — Koneksi HP
        # ═══════════════════════════════════════════════════════
        conn = _sec("Koneksi HP", accent="#2A1050")

        # status dot + label + combobox
        st = tk.Frame(conn, bg=CARD)
        st.pack(fill="x", pady=(0, 8))
        dot = tk.Label(st, text="\u25cf", bg=CARD, fg=MUT,
                       font=("Segoe UI", 13))
        dot.pack(side="left")
        status_var = tk.StringVar(value="Menginisialisasi...")
        tk.Label(st, textvariable=status_var, bg=CARD, fg=FG,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 14))
        dev_var   = tk.StringVar(value="")
        dev_combo = ttk.Combobox(st, textvariable=dev_var,
                                 state="readonly", width=24)
        dev_combo.pack(side="left", padx=(0, 8))
        msg_var = tk.StringVar(value="")
        tk.Label(conn, textvariable=msg_var, bg=CARD, fg=MUT,
                 font=("Segoe UI", 8), wraplength=560,
                 justify="left").pack(anchor="w", pady=(0, 4))

        def _refresh_devs():
            if self._adb is None:
                return
            try:
                devs = self._adb.list_devices()
                vals = [d["serial"] for d in devs if d["state"] == "device"]
                dev_combo["values"] = vals
                if vals:
                    dev_combo.set(vals[0])
                    status_var.set("{} perangkat".format(len(vals)))
                    dot.configure(fg=GRN)
                else:
                    dev_combo.set("")
                    status_var.set("Tidak ada perangkat")
                    dot.configure(fg=MUT)
            except Exception:
                pass

        tk.Button(st, text="Refresh", bg=CARD2, fg=FG,
                  font=("Segoe UI", 8), padx=8, pady=3,
                  command=lambda: _thr.Thread(
                      target=_refresh_devs, daemon=True).start(),
                  **_FB).pack(side="left")

        # IP + Port row
        ip_row = tk.Frame(conn, bg=CARD)
        ip_row.pack(fill="x", pady=(0, 6))
        tk.Label(ip_row, text="IP HP:", bg=CARD, fg=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        ip_var = tk.StringVar(value=self.config.get("remote.last_ip", ""))
        tk.Entry(ip_row, textvariable=ip_var,
                 bg=CARD2, fg=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 10),
                 width=18, bd=4).pack(side="left", padx=(6, 4))
        tk.Label(ip_row, text="Port:", bg=CARD, fg=MUT,
                 font=("Segoe UI", 9)).pack(side="left")
        port_var = tk.StringVar(value="5555")
        tk.Entry(ip_row, textvariable=port_var,
                 bg=CARD2, fg=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 10),
                 width=6, bd=4).pack(side="left", padx=(4, 10))

        def _connect_bg():
            ip = ip_var.get().strip()
            if not ip:
                msg_var.set("Masukkan IP address HP.")
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
                self.config.save()
            if self._root:
                self._root.after(0, lambda: msg_var.set(msg))
            _refresh_devs()

        def _disconnect_bg():
            if self._adb:
                ok, msg = self._adb.disconnect(dev_var.get())
                if self._root:
                    self._root.after(0, lambda: msg_var.set(msg))
            _refresh_devs()

        tk.Button(ip_row, text="Hubungkan", bg=ACC, fg="white",
                  font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                  command=lambda: _thr.Thread(
                      target=_connect_bg, daemon=True).start(),
                  **_FB).pack(side="left", padx=(0, 6))
        tk.Button(ip_row, text="Putuskan", bg=CARD2, fg=FG,
                  font=("Segoe UI", 9), padx=10, pady=5,
                  command=lambda: _thr.Thread(
                      target=_disconnect_bg, daemon=True).start(),
                  **_FB).pack(side="left")

        # USB one-time setup
        tk.Frame(conn, bg=CARD2, height=1).pack(fill="x", pady=(8, 8))
        tk.Label(conn,
                 text="Setup sekali via USB — colok HP, klik tombol, "
                      "cabut USB, lalu hubungkan via WiFi:",
                 bg=CARD, fg=MUT, font=("Segoe UI", 8),
                 wraplength=560, justify="left").pack(
            anchor="w", pady=(0, 6))

        def _usb_setup_bg():
            if self._root:
                self._root.after(0, lambda: msg_var.set(
                    "Menjalankan adb tcpip 5555..."))
            if self._adb is None:
                return
            ok, m = self._adb.tcpip(5555)
            if not ok:
                if self._root:
                    self._root.after(0, lambda: msg_var.set("Gagal: " + m))
                return
            import time as _t; _t.sleep(1)
            ip = self._adb.get_device_ip()
            if ip:
                if self._root:
                    self._root.after(0, lambda: ip_var.set(ip))
                    self._root.after(0, lambda: msg_var.set(
                        "Berhasil! IP: {}  — cabut USB, klik Hubungkan".format(ip)))
                self.config.set("remote.last_ip", ip)
                self.config.save()
            else:
                if self._root:
                    self._root.after(0, lambda: msg_var.set(
                        "tcpip OK, IP tidak terdeteksi — isi manual."))
            _refresh_devs()

        usb_row = tk.Frame(conn, bg=CARD)
        usb_row.pack(anchor="w")
        tk.Button(usb_row, text="Setup Wireless via USB",
                  bg="#3A1060", fg="white",
                  font=("Segoe UI", 9, "bold"), padx=14, pady=6,
                  command=lambda: _thr.Thread(
                      target=_usb_setup_bg, daemon=True).start(),
                  **_FB).pack(side="left", padx=(0, 10))
        tk.Label(usb_row, text="Butuh USB Debugging aktif di HP",
                 bg=CARD, fg=MUT,
                 font=("Segoe UI", 8)).pack(side="left")

        # ═══════════════════════════════════════════════════════
        # SECTION 2 — Pengaturan Mirror
        # ═══════════════════════════════════════════════════════
        mir = _sec("Pengaturan Mirror", accent="#0A2A18")

        # Row 1: Resolusi Bitrate FPS Orientasi
        row1 = tk.Frame(mir, bg=CARD)
        row1.pack(fill="x", pady=(0, 8))

        def _lbl_cb(parent, lbl, var, vals, w=8):
            tk.Label(parent, text=lbl, bg=CARD, fg=MUT,
                     font=("Segoe UI", 9)).pack(side="left")
            ttk.Combobox(parent, textvariable=var, values=vals,
                         state="readonly", width=w).pack(
                side="left", padx=(4, 14))

        res_var = tk.StringVar(value="1024")
        br_var  = tk.StringVar(value="8M")
        fps_var = tk.StringVar(value="60")
        ori_var = tk.StringVar(value="Auto")
        _lbl_cb(row1, "Resolusi:", res_var,
                ["480", "720", "1024", "1280", "1920"], w=6)
        _lbl_cb(row1, "Bitrate:",  br_var,
                ["2M", "4M", "8M", "16M", "32M"],      w=5)
        _lbl_cb(row1, "FPS:",      fps_var,
                ["24", "30", "45", "60"],               w=4)
        _lbl_cb(row1, "Orientasi:", ori_var,
                ["Auto", "Portrait", "Landscape"],      w=9)

        # Row 2: checkboxes
        row2 = tk.Frame(mir, bg=CARD)
        row2.pack(fill="x", pady=(0, 10))
        stay_var  = tk.BooleanVar(value=True)
        touch_var = tk.BooleanVar(value=False)
        top_var   = tk.BooleanVar(value=True)
        full_var  = tk.BooleanVar(value=False)
        audio_var = tk.BooleanVar(value=False)
        bord_var  = tk.BooleanVar(value=True)
        for _txt, _v in [
            ("Stay Awake",    stay_var),
            ("Show Touches",  touch_var),
            ("Always On Top", top_var),
            ("Fullscreen",    full_var),
            ("No Audio",      audio_var),
            ("Window Border", bord_var),
        ]:
            tk.Checkbutton(row2, text=_txt, variable=_v,
                           bg=CARD, fg=FG, selectcolor=CARD2,
                           activebackground=CARD, activeforeground=FG,
                           font=("Segoe UI", 9)).pack(
                side="left", padx=(0, 12))

        # scrcpy status bar
        sbar = tk.Frame(mir, bg="#0E0E1C", padx=10, pady=7)
        sbar.pack(fill="x", pady=(0, 10))
        scrcpy_sv  = tk.StringVar(value="scrcpy: memeriksa...")
        scrcpy_lbl = tk.Label(sbar, textvariable=scrcpy_sv,
                              bg="#0E0E1C", fg=MUT,
                              font=("Segoe UI", 8))
        scrcpy_lbl.pack(side="left", fill="x", expand=True)
        dl_sv = tk.StringVar(value="")
        tk.Label(sbar, textvariable=dl_sv, bg="#0E0E1C", fg=YEL,
                 font=("Segoe UI", 8)).pack(side="left", padx=(6, 0))

        def _upd_scrcpy():
            if self._scrcpy and self._scrcpy.available:
                scrcpy_sv.set("scrcpy: ditemukan")
                scrcpy_lbl.configure(fg=GRN)
            else:
                scrcpy_sv.set("scrcpy: belum ada — klik Download")
                scrcpy_lbl.configure(fg=YEL)

        def _download_scrcpy():
            dl_sv.set("Mengunduh...")

            def _do():
                import urllib.request as _ur
                import zipfile as _zf
                import json as _js
                import os as _o
                import sys as _sy
                base = (_o.path.dirname(_sy.executable)
                        if getattr(_sy, "frozen", False)
                        else _o.path.dirname(
                            _o.path.dirname(_o.path.abspath(__file__))))
                tdir = _o.path.join(base, "tools", "scrcpy")
                _o.makedirs(tdir, exist_ok=True)
                try:
                    req = _ur.Request(
                        "https://api.github.com/repos/Genymobile/scrcpy"
                        "/releases/latest",
                        headers={"User-Agent": "Synthex"})
                    with _ur.urlopen(req, timeout=15) as r:
                        info = _js.loads(r.read())
                    asset = next(
                        (a for a in info.get("assets", [])
                         if "win64" in a["name"]
                         and a["name"].endswith(".zip")), None)
                    if not asset:
                        if self._root:
                            self._root.after(
                                0, lambda: dl_sv.set("Asset tidak ditemukan."))
                        return
                    url  = asset["browser_download_url"]
                    name = asset["name"]
                    size = asset.get("size", 0)
                    if self._root:
                        self._root.after(0, lambda: dl_sv.set(
                            "Mengunduh {:.0f} MB...".format(
                                size / 1024 / 1024)))
                    zpath = _o.path.join(tdir, name)
                    _ur.urlretrieve(url, zpath)
                    if self._root:
                        self._root.after(0, lambda: dl_sv.set(
                            "Mengekstrak..."))
                    with _zf.ZipFile(zpath, "r") as z:
                        for m in z.namelist():
                            parts = m.split("/", 1)
                            tgt = parts[1] if len(parts) > 1 else parts[0]
                            if not tgt:
                                continue
                            dest = _o.path.join(tdir, tgt)
                            if m.endswith("/"):
                                _o.makedirs(dest, exist_ok=True)
                            else:
                                _o.makedirs(_o.path.dirname(dest),
                                            exist_ok=True)
                                with z.open(m) as src, \
                                     open(dest, "wb") as out:
                                    out.write(src.read())
                    _o.remove(zpath)
                    from modules.remote_control import _find_scrcpy
                    if self._scrcpy:
                        self._scrcpy.path = _find_scrcpy()
                    if self._root:
                        self._root.after(0, _upd_scrcpy)
                        self._root.after(
                            0, lambda: dl_sv.set("Selesai!"))
                except Exception as ex:
                    _msg = str(ex)[:60]
                    if self._root:
                        self._root.after(
                            0, lambda: dl_sv.set("Gagal: " + _msg))

            _thr.Thread(target=_do, daemon=True).start()

        tk.Button(sbar, text="Download scrcpy otomatis",
                  bg="#2A1050", fg="white",
                  font=("Segoe UI", 8, "bold"),
                  padx=10, pady=4,
                  command=_download_scrcpy, **_FB).pack(side="right")

        # Mirror start / stop buttons
        ctrl = tk.Frame(mir, bg=CARD)
        ctrl.pack(fill="x")
        mir_sv = tk.StringVar(value="")
        tk.Label(mir, textvariable=mir_sv, bg=CARD, fg=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 0))

        start_btn = tk.Button(ctrl, text="  Mulai Mirror",
                              bg=GRN, fg="white",
                              font=("Segoe UI", 12, "bold"),
                              padx=22, pady=10, **_FB)
        start_btn.pack(side="left", padx=(0, 10))
        stop_btn = tk.Button(ctrl, text="  Stop",
                             bg=RED, fg="white",
                             font=("Segoe UI", 12, "bold"),
                             padx=18, pady=10,
                             state="disabled", **_FB)
        stop_btn.pack(side="left")

        def _start_mirror():
            if self._scrcpy is None or not self._scrcpy.available:
                mir_sv.set("scrcpy belum ada — klik Download dulu.")
                return
            rot_map = {"Auto": None, "Portrait": 0, "Landscape": 1}
            rot = rot_map.get(ori_var.get())
            if rot is not None and hasattr(self._scrcpy, '_extra_args'):
                pass  # orientation handled via start() override below
            serial = dev_var.get()
            ok, msg = self._scrcpy.start(
                serial=serial,
                max_size=int(res_var.get()),
                bitrate=br_var.get(),
                stay_awake=stay_var.get(),
                show_touches=touch_var.get(),
                always_on_top=top_var.get(),
                no_audio=audio_var.get(),
            )
            mir_sv.set(msg)
            if ok:
                start_btn.configure(state="disabled")
                stop_btn.configure(state="normal")
                _poll_mirror()

        def _stop_mirror():
            if self._scrcpy:
                self._scrcpy.stop()
            start_btn.configure(state="normal")
            stop_btn.configure(state="disabled")
            mir_sv.set("Mirror dihentikan.")
            if self._rem_poll_id:
                try:
                    self._root.after_cancel(self._rem_poll_id)
                except Exception:
                    pass
                self._rem_poll_id = None

        def _poll_mirror():
            if self._scrcpy is None or not self._scrcpy.running:
                try:
                    start_btn.configure(state="normal")
                    stop_btn.configure(state="disabled")
                    mir_sv.set("Mirror selesai.")
                except Exception:
                    pass
                return
            self._rem_poll_id = self._root.after(800, _poll_mirror)

        start_btn.configure(command=_start_mirror)
        stop_btn.configure(command=_stop_mirror)
        if self._scrcpy and self._scrcpy.running:
            start_btn.configure(state="disabled")
            stop_btn.configure(state="normal")
            _poll_mirror()

        # ── Init ADB in background (no lag) ────────────────────────────────
        def _init_adb():
            from modules.remote_control import AdbManager, ScrcpyManager
            if self._adb is None:
                self._adb    = AdbManager()
                self._scrcpy = ScrcpyManager(self._adb)
            # Update UI on main thread
            def _after():
                if self._adb.available:
                    _refresh_devs()
                else:
                    status_var.set("adb tidak ditemukan")
                    dot.configure(fg=RED)
                _upd_scrcpy()
            if self._root:
                self._root.after(0, _after)

        _thr.Thread(target=_init_adb, daemon=True).start()

        return f

    def _pg_history(self):
        f = tk.Frame(self._content, bg=BG)
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
        ttk.Button(c, text="Clear All", style="Danger.TButton",
                   command=lambda: [
                       self._ud.activity.clear(), self._ud.save()
                   ]).pack(anchor="e", pady=(8, 0))
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
            messagebox.showinfo("Restore", "No backups found.")
            return

        dlg = tk.Toplevel(self._root)
        dlg.title("Restore from Backup")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        _lbl(dlg, "Select a backup to restore:", bg=BG,
             font=("Segoe UI", 10, "bold")).pack(padx=20, pady=(16, 8))

        lb_frame = tk.Frame(dlg, bg=BG)
        lb_frame.pack(padx=20, fill="both", expand=True)

        lb = tk.Listbox(lb_frame, bg=CARD, fg=FG, selectbackground=ACC,
                        font=("Segoe UI", 9), relief="flat",
                        width=36, height=min(len(backups), 8))
        lb.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lb_frame, orient="vertical", command=lb.yview)
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
            if not messagebox.askyesno(
                    "Confirm Restore",
                    f"Restore from {chosen['name']}?\n"
                    "Current data will be overwritten."):
                return
            def _run():
                ok = ab.restore_backup(chosen["path"])
                kind = "success" if ok else "error"
                msg  = "Restore complete!" if ok else "Restore failed – check logs."
                self._root.after(0, lambda: self._show_toast(msg, kind=kind))
            threading.Thread(target=_run, daemon=True).start()

        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(padx=20, pady=12, anchor="e")
        ttk.Button(btn_row, text="Cancel",
                   command=dlg.destroy).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Restore", bg=ACC, fg=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat",
                  padx=10, pady=4, cursor="hand2",
                  command=_do_restore).pack(side="left")

    def _pg_settings(self):
        f = tk.Frame(self._content, bg=BG)
        self._hdr(f, "Settings")

        # ---- Backup & Restore card ------------------------------------
        from utils.backup import AutoBackup
        _ab = AutoBackup()

        bc = _card(f, "Backup & Restore")
        bc.pack(fill="x", padx=20, pady=(8, 0))

        info_row = tk.Frame(bc, bg=CARD)
        info_row.pack(fill="x", pady=(0, 8))
        last_lbl = _lbl(info_row,
                        f"Last backup: {_ab.last_backup_label()}",
                        fg=MUT, bg=CARD, font=("Segoe UI", 9))
        last_lbl.pack(side="left")
        _lbl(info_row, "  |  Auto-backup: Daily",
             fg=MUT, bg=CARD, font=("Segoe UI", 9)).pack(side="left")

        btn_row_b = tk.Frame(bc, bg=CARD)
        btn_row_b.pack(anchor="w")
        tk.Button(btn_row_b, text="Backup Now",
                  bg=ACC, fg=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
                  command=lambda: self._backup_now(last_lbl)).pack(
                      side="left", padx=(0, 10))
        ttk.Button(btn_row_b, text="Restore from Backup",
                   command=self._restore_backup_dialog).pack(side="left")

        # ---- Rekening API card ----------------------------------------
        rak = _card(f, "Rekening API")
        rak.pack(fill="x", padx=20, pady=(12, 0))

        _lbl(rak, "API Key Validasi Rekening (Unlimited API)",
             fg=MUT, bg=CARD, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 4))

        rak_row = tk.Frame(rak, bg=CARD)
        rak_row.pack(fill="x")

        _cur_key = self.config.get("rekening_api_key", "")
        rak_var  = tk.StringVar(value=_cur_key)
        rak_entry = ttk.Entry(rak_row, textvariable=rak_var,
                              font=("Segoe UI", 10), show="*", width=36)
        rak_entry.pack(side="left", padx=(0, 6))

        _show_key = {"v": False}
        def _toggle_show():
            _show_key["v"] = not _show_key["v"]
            rak_entry.configure(show="" if _show_key["v"] else "*")
            show_btn.configure(text="Hide" if _show_key["v"] else "Show")
        show_btn = ttk.Button(rak_row, text="Show", command=_toggle_show, width=5)
        show_btn.pack(side="left", padx=(0, 6))

        rak_status = tk.StringVar(
            value="Tersimpan" if _cur_key else "Belum diisi")
        rak_status_lbl = _lbl(rak, "", fg=GRN if _cur_key else MUT,
                              bg=CARD, font=("Segoe UI", 9))
        rak_status_lbl.configure(textvariable=rak_status)
        rak_status_lbl.pack(anchor="w", pady=(4, 0))

        def _save_rak_key():
            val = rak_var.get().strip()
            self.config.set("rekening_api_key", val)
            self.config.save()
            if val:
                rak_status.set("Tersimpan")
                rak_status_lbl.configure(fg=GRN)
            else:
                rak_status.set("Belum diisi")
                rak_status_lbl.configure(fg=MUT)

        ttk.Button(rak, text="Save", style="Accent.TButton",
                   command=_save_rak_key).pack(anchor="w", pady=(8, 0))

        # ---- Google Accounts card ------------------------------------
        self._build_google_accounts_card(f)

        # ---- Account card ---------------------------------------------
        ac = _card(f, "Account")
        ac.pack(fill="x", padx=20, pady=(12, 0))
        _lbl(ac, "Email: {}".format(self._email or "-"), bg=CARD).pack(
            anchor="w")
        btn_row = tk.Frame(ac, bg=CARD)
        btn_row.pack(anchor="w", pady=(8, 0))
        ttk.Button(btn_row, text="Logout", style="Danger.TButton",
                   command=self._logout).pack(side="left", padx=(0, 10))
        tk.Button(btn_row, text="Setup Guide",
                  bg=ACC, fg=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=5, cursor="hand2",
                  command=self._launch_onboarding).pack(side="left")
        lc = _card(f, "System Log")
        lc.pack(fill="both", expand=True, padx=20, pady=(12, 20))
        self._lw = scrolledtext.ScrolledText(
            lc, bg=BG, fg=FG, insertbackground=FG,
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
            self._spy_btn.configure(text="DISABLE SPY", bg=RED)
            self._spy_status_lbl.configure(
                text="Active - Hover over elements in Chrome", fg=GRN)
            if self.engine and self.engine.browser:
                try:
                    self.engine.browser.inject_spy_overlay()
                except Exception as e:
                    self.logger.warning("inject_spy_overlay: {}".format(e))
            self._poll_spy()
        else:
            self._spy_active = False
            self._spy_btn.configure(text="ENABLE SPY", bg=ACC)
            self._spy_status_lbl.configure(text="Inactive", fg=MUT)
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
        name = info.get("name") or simpledialog.askstring(
            "Simpan Elemen", "Nama untuk elemen ini:", parent=self._root)
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
            messagebox.showwarning(
                "Spy",
                "No element selected.\nEnable Spy and hover over an element.",
                parent=self._root)
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
                self._root.after(0, lambda: messagebox.showinfo(
                    "Element Value", "Current value:\n{}".format(text),
                    parent=self._root))
            except Exception as e:
                from utils.error_handler import friendly_message
                msg = friendly_message(e)
                self._root.after(0, lambda m=msg, ex=e: self._toast_error(m, ex))
        threading.Thread(target=_fetch, daemon=True).start()

    def _scrape_spy_to_sheet(self):
        sel = self._spy_elements_tree.selection()
        if not sel:
            messagebox.showwarning("Scrape ke Sheet",
                                   "Pilih elemen terlebih dahulu.",
                                   parent=self._root)
            return
        idx = self._spy_elements_tree.index(sel[0])
        if idx >= len(self._ud.elements):
            return
        element  = self._ud.elements[idx]
        selector = element.get("selector", "")
        if not selector or not self.engine:
            messagebox.showwarning("Scrape ke Sheet",
                                   "Elemen tidak memiliki selector atau browser belum aktif.",
                                   parent=self._root)
            return

        # -- dialog -------------------------------------------------------
        sheets = [s.get("name", "") for s in self._ud.sheets if s.get("name")]
        if not sheets:
            messagebox.showwarning("Scrape ke Sheet",
                                   "Belum ada sheet terhubung. Tambahkan di halaman Sheet.",
                                   parent=self._root)
            return

        dlg = tk.Toplevel(self._root)
        dlg.title("Scrape ke Sheet")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.geometry("340x180+{}+{}".format(
            self._root.winfo_rootx() + 80,
            self._root.winfo_rooty() + 80))

        _lbl(dlg, "Sheet tujuan:", bg=BG, font=("Segoe UI", 9)).pack(
            anchor="w", padx=16, pady=(14, 2))
        sheet_var = tk.StringVar(value=sheets[0])
        ttk.Combobox(dlg, textvariable=sheet_var, values=sheets,
                     state="readonly", font=("Segoe UI", 10)).pack(
            fill="x", padx=16)

        _lbl(dlg, "Nama kolom / header (kosongkan = append nilai saja):",
             bg=BG, font=("Segoe UI", 9), fg=MUT).pack(
            anchor="w", padx=16, pady=(10, 2))
        col_var = tk.StringVar()
        ttk.Entry(dlg, textvariable=col_var,
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

        btn_row_dlg = tk.Frame(dlg, bg=BG)
        btn_row_dlg.pack(anchor="e", padx=16, pady=(12, 0))
        ttk.Button(btn_row_dlg, text="Scrape", style="Accent.TButton",
                   command=_do_scrape).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row_dlg, text="Batal",
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
        if messagebox.askyesno(
                "Delete", "Delete element '{}'?".format(name),
                parent=self._root):
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
        dlg = tk.Toplevel(self._root)
        dlg.title("")
        dlg.geometry("200x120")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.overrideredirect(True)
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        dlg.geometry("200x120+{}+{}".format(sw // 2 - 100, sh // 2 - 60))

        lbl = tk.Label(dlg, text="Recording starts in", bg=BG, fg=MUT,
                       font=("Segoe UI", 11))
        lbl.pack(pady=(18, 4))
        num = tk.Label(dlg, text=str(count), bg=BG, fg=ACC,
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

        dlg.after(1000, _tick)

    def _show_rec_toolbar(self):
        """Floating recorder control panel - recording starts/stops from here."""
        import time as _time

        win = tk.Toplevel(self._root)
        win.title("Synthex Recorder")
        win.configure(bg="#0D0D14")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.overrideredirect(True)

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
                    win.after_cancel(self._rec_timer_id)
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
        hdr = tk.Frame(win, bg=ACC, height=22, cursor="fleur")
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr.bind("<ButtonPress-1>", _drag_start)
        hdr.bind("<B1-Motion>",     _drag_move)

        tk.Label(hdr, text="  SYNTHEX REC", bg=ACC, fg="#FFFFFF",
                 font=("Segoe UI", 8, "bold")).pack(side="left", pady=3)
        tk.Button(hdr, text="x", bg=ACC, fg="#FFFFFF",
                  font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                  padx=7, cursor="hand2",
                  activebackground=RED, activeforeground="#FFFFFF",
                  command=lambda: _close_ref[0]()).pack(side="right", fill="y")
        tk.Button(hdr, text="—", bg=ACC, fg="#FFFFFF",
                  font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                  padx=7, cursor="hand2",
                  activebackground="#8870FF", activeforeground="#FFFFFF",
                  command=_do_minimize).pack(side="right", fill="y")

        # ── Status bar (1 compact line) ──────────────────────────────────────
        dot_var   = tk.StringVar(value="●")
        state_var = tk.StringVar(value="SIAP")
        timer_var = tk.StringVar(value="00:00")
        steps_var = tk.StringVar(value="0 steps")

        st = tk.Frame(win, bg="#0D0D14")
        st.pack(fill="x", padx=8, pady=(4, 2))

        dot_lbl = tk.Label(st, textvariable=dot_var, bg="#0D0D14", fg=MUT,
                           font=("Segoe UI", 10))
        dot_lbl.pack(side="left")
        tk.Label(st, textvariable=state_var, bg="#0D0D14", fg=FG,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(4, 0))
        tk.Label(st, textvariable=timer_var, bg="#0D0D14", fg=MUT,
                 font=("Consolas", 8)).pack(side="right", padx=(0, 2))
        tk.Label(st, textvariable=steps_var, bg="#0D0D14", fg=MUT,
                 font=("Segoe UI", 8)).pack(side="right", padx=(0, 6))

        tk.Frame(win, bg="#2A2A40", height=1).pack(fill="x", pady=(2, 0))

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
            dot_lbl.configure(fg=MUT)
            state_var.set("SIAP")
            timer_var.set("00:00")
            steps_var.set("0 langkah")
            btn_rec.configure(text="⏺", bg=RED, fg="#FFFFFF", state="normal")
            btn_pause.configure(text="⏸", bg=CARD2, fg=MUT, state="disabled")
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
                dot_lbl.configure(fg=RED)
                state_var.set("MEREKAM")
                btn_rec.configure(text="⏹", bg="#2A1A1A", fg=RED, state="normal")
                btn_pause.configure(text="⏸", bg=YEL, fg=BG, state="normal")
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
                try: win.after_cancel(self._rec_timer_id)
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
                dot_lbl.configure(fg=YEL)
                state_var.set("DIJEDA")
                btn_pause.configure(text="▶", bg=GRN, fg=BG)
                if self._simple_recorder:
                    self._simple_recorder.pause_recording()
            else:
                dot_var.set("●")
                dot_lbl.configure(fg=RED)
                state_var.set("MEREKAM")
                btn_pause.configure(text="⏸", bg=YEL, fg=BG)
                if self._simple_recorder:
                    self._simple_recorder.resume_recording()

        def _toggle_unlimited():
            self._rec_unlimited = not self._rec_unlimited
            if self._rec_unlimited:
                btn_unlim.configure(bg=ACC, fg="#FFFFFF")
            else:
                btn_unlim.configure(bg=CARD2, fg=MUT)

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

        btn_row = tk.Frame(win, bg="#0D0D14", height=52)
        btn_row.pack(fill="x", padx=8, pady=(6, 8))
        btn_row.pack_propagate(False)

        btn_rec = tk.Button(btn_row, text="⏺",
                            bg=RED, fg="#FFFFFF", font=ICON_F,
                            relief="flat", bd=0, cursor="hand2",
                            activebackground="#CC3050",
                            command=_toggle_recording)
        btn_rec.pack(side="left", fill="both", expand=True, padx=(0, 3))

        btn_pause = tk.Button(btn_row, text="⏸",
                              bg=CARD2, fg=MUT, font=ICON_F,
                              relief="flat", bd=0, cursor="hand2",
                              state="disabled", activebackground=CARD,
                              command=_toggle_pause)
        btn_pause.pack(side="left", fill="both", expand=True, padx=(0, 3))

        btn_play = tk.Button(btn_row, text="▶",
                             bg="#1A3A2A", fg=GRN, font=ICON_F,
                             relief="flat", bd=0, cursor="hand2",
                             activebackground="#254D38",
                             command=_play_last)
        btn_play.pack(side="left", fill="both", expand=True, padx=(0, 3))

        btn_unlim = tk.Button(btn_row, text="∞",
                              bg=CARD2, fg=MUT, font=ICON_F,
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
            messagebox.showinfo(
                "Rekaman Kosong",
                "Tidak ada langkah yang terekam.\n"
                "Coba rekam ulang — pastikan melakukan klik atau ketikan.",
                parent=self._root)
            return

        # Existing recording metadata (if editing)
        existing = (self._ud.recordings[edit_idx]
                    if edit_idx is not None and 0 <= edit_idx < len(self._ud.recordings)
                    else None)

        # ------------------------------------------------------------------ #
        #  Window setup                                                        #
        # ------------------------------------------------------------------ #
        dlg = tk.Toplevel(self._root)
        dlg.title("Macro Step Editor")
        dlg.geometry("980x700")
        dlg.configure(bg=BG)
        dlg.resizable(True, True)
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
        top_bar = tk.Frame(dlg, bg=CARD, padx=12, pady=8)
        top_bar.pack(fill="x", padx=0, pady=0)

        # Single compact row
        _lbl(top_bar, "Nama:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        name_var = tk.StringVar(
            value=existing.get("name", "") if existing else "")
        tk.Entry(top_bar, textvariable=name_var, bg=BG, fg=FG,
                 insertbackground=FG, font=("Segoe UI", 10),
                 relief="flat", bd=0, width=22).pack(
            side="left", padx=(0, 14), ipady=4)

        _lbl(top_bar, "Deskripsi:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        desc_var = tk.StringVar(
            value=existing.get("description", "") if existing else "")
        tk.Entry(top_bar, textvariable=desc_var, bg=BG, fg=FG,
                 insertbackground=FG, font=("Segoe UI", 10),
                 relief="flat", bd=0, width=28).pack(
            side="left", padx=(0, 14), ipady=4)

        _lbl(top_bar, "Folder:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        folders = sorted(
            {r.get("folder", "General") for r in self._ud.recordings}
            | {"General", "Work", "Personal"})
        folder_var = tk.StringVar(
            value=existing.get("folder", "General") if existing else "General")
        ttk.Combobox(top_bar, textvariable=folder_var, values=folders,
                     width=14).pack(side="left")

        # Filter combobox on the right side of top bar
        _lbl(top_bar, "  Filter:", fg=MUT, bg=CARD,
             font=("Segoe UI", 9)).pack(side="left", padx=(18, 4))
        filter_cb = ttk.Combobox(top_bar, textvariable=_filter_var,
                                 values=["Semua", "click", "type", "key", "scroll"],
                                 state="readonly", width=8)
        filter_cb.pack(side="left")

        # ------------------------------------------------------------------ #
        #  Toolbar row                                                         #
        # ------------------------------------------------------------------ #
        toolbar = tk.Frame(dlg, bg=SIDE, padx=8, pady=5)
        toolbar.pack(fill="x")

        def _tb_btn(parent, text, cmd, fg_col=FG, width=None):
            kw = {"width": width} if width else {}
            b = tk.Button(parent, text=text, command=cmd,
                          bg=CARD, fg=fg_col, relief="flat", bd=0,
                          font=("Segoe UI", 9), padx=8, pady=3,
                          activebackground=ACC, activeforeground=BG,
                          cursor="hand2", **kw)
            b.pack(side="left", padx=2)
            return b

        def _tb_sep():
            tk.Label(toolbar, text="|", bg=SIDE, fg=MUT,
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

        add_btn = tk.Button(toolbar, text="+ Tambah",
                            bg=ACC, fg=BG, relief="flat", bd=0,
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
        _lbl(toolbar, "Bulk Delay:", fg=MUT, bg=SIDE,
             font=("Segoe UI", 9)).pack(side="left", padx=(4, 2))
        bulk_delay_var = tk.IntVar(value=500)
        tk.Spinbox(toolbar, from_=0, to=30000, increment=50, width=6,
                   textvariable=bulk_delay_var,
                   bg=CARD, fg=FG, insertbackground=FG,
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
        step_count_lbl = tk.Label(toolbar, text="0 langkah",
                                  bg=SIDE, fg=MUT, font=("Segoe UI", 9))
        step_count_lbl.pack(side="right", padx=(4, 8))
        total_dur_lbl = tk.Label(toolbar, text="Total: 0.0s",
                                 bg=SIDE, fg=MUT, font=("Segoe UI", 9))
        total_dur_lbl.pack(side="right", padx=(4, 4))

        # ------------------------------------------------------------------ #
        #  Main area: treeview (65%) + right edit panel (35%)                 #
        # ------------------------------------------------------------------ #
        main_area = tk.Frame(dlg, bg=BG)
        main_area.pack(fill="both", expand=True, padx=0, pady=0)

        # --- LEFT: Treeview ------------------------------------------------ #
        left_frame = tk.Frame(main_area, bg=CARD)
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

        vsb = ttk.Scrollbar(left_frame, orient="vertical", command=st.yview)
        st.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        st.pack(side="left", fill="both", expand=True)

        # --- RIGHT: Edit panel --------------------------------------------- #
        right_frame = tk.Frame(main_area, bg=CARD, width=310)
        right_frame.pack(side="right", fill="y", padx=(4, 8), pady=8)
        right_frame.pack_propagate(False)

        edit_header = tk.Label(right_frame, text="Pilih langkah untuk diedit",
                               bg=CARD, fg=MUT,
                               font=("Segoe UI", 10, "bold"), anchor="w")
        edit_header.pack(fill="x", padx=10, pady=(10, 6))

        edit_fields = tk.Frame(right_frame, bg=CARD)
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
            return tk.Label(parent, text=text, bg=CARD, fg=MUT,
                            font=("Segoe UI", 9), anchor="w")

        def _build_edit_panel(atype="click"):
            for w in edit_fields.winfo_children():
                w.destroy()
            _edit_widgets.clear()

            # Type row
            r0 = tk.Frame(edit_fields, bg=CARD)
            r0.pack(fill="x", pady=(4, 2))
            _ep_lbl(r0, "Tipe:").pack(anchor="w")
            type_cb = ttk.Combobox(r0, textvariable=_ep_type,
                                   values=["click", "type", "scroll", "key"],
                                   state="readonly", width=14)
            type_cb.pack(fill="x", pady=(2, 0))
            type_cb.bind("<<ComboboxSelected>>",
                         lambda e: _build_edit_panel(_ep_type.get()))
            _edit_widgets["type_cb"] = type_cb

            # Delay row
            r1 = tk.Frame(edit_fields, bg=CARD)
            r1.pack(fill="x", pady=(6, 2))
            _ep_lbl(r1, "Delay (ms):").pack(anchor="w")
            delay_sp = tk.Spinbox(r1, from_=0, to=30000, increment=50,
                                  textvariable=_ep_delay, width=10,
                                  bg=BG, fg=FG, insertbackground=FG,
                                  relief="flat", font=("Segoe UI", 9))
            delay_sp.pack(fill="x", pady=(2, 0), ipady=3)
            _edit_widgets["delay_sp"] = delay_sp

            # Type-specific fields
            if atype == "click":
                for lbl_t, var, name in [("X:", _ep_x, "x_sp"),
                                          ("Y:", _ep_y, "y_sp")]:
                    rf = tk.Frame(edit_fields, bg=CARD)
                    rf.pack(fill="x", pady=(4, 2))
                    _ep_lbl(rf, lbl_t).pack(anchor="w")
                    sp = tk.Spinbox(rf, from_=-9999, to=9999, textvariable=var,
                                    width=10, bg=BG, fg=FG,
                                    insertbackground=FG, relief="flat",
                                    font=("Segoe UI", 9))
                    sp.pack(fill="x", pady=(2, 0), ipady=3)
                    _edit_widgets[name] = sp
                rb = tk.Frame(edit_fields, bg=CARD)
                rb.pack(fill="x", pady=(4, 2))
                _ep_lbl(rb, "Button:").pack(anchor="w")
                btn_cb = ttk.Combobox(rb, textvariable=_ep_button,
                                      values=["left", "right", "middle"],
                                      state="readonly", width=10)
                btn_cb.pack(fill="x", pady=(2, 0))
                _edit_widgets["btn_cb"] = btn_cb

            elif atype == "type":
                rt = tk.Frame(edit_fields, bg=CARD)
                rt.pack(fill="x", pady=(4, 2))
                _ep_lbl(rt, "Teks:").pack(anchor="w")
                txt_e = tk.Entry(rt, textvariable=_ep_text,
                                 bg=BG, fg=FG, insertbackground=FG,
                                 font=("Segoe UI", 9), relief="flat", bd=0)
                txt_e.pack(fill="x", pady=(2, 0), ipady=4)
                _edit_widgets["txt_e"] = txt_e

            elif atype == "scroll":
                for lbl_t, var, name in [("X:", _ep_x, "sx_sp"),
                                          ("Y:", _ep_y, "sy_sp")]:
                    rf = tk.Frame(edit_fields, bg=CARD)
                    rf.pack(fill="x", pady=(4, 2))
                    _ep_lbl(rf, lbl_t).pack(anchor="w")
                    sp = tk.Spinbox(rf, from_=-9999, to=9999, textvariable=var,
                                    width=10, bg=BG, fg=FG,
                                    insertbackground=FG, relief="flat",
                                    font=("Segoe UI", 9))
                    sp.pack(fill="x", pady=(2, 0), ipady=3)
                    _edit_widgets[name] = sp
                ra = tk.Frame(edit_fields, bg=CARD)
                ra.pack(fill="x", pady=(4, 2))
                _ep_lbl(ra, "Jumlah:").pack(anchor="w")
                amt_sp = tk.Spinbox(ra, from_=-100, to=100, textvariable=_ep_amount,
                                    width=10, bg=BG, fg=FG,
                                    insertbackground=FG, relief="flat",
                                    font=("Segoe UI", 9))
                amt_sp.pack(fill="x", pady=(2, 0), ipady=3)
                _edit_widgets["amt_sp"] = amt_sp

            elif atype == "key":
                rk = tk.Frame(edit_fields, bg=CARD)
                rk.pack(fill="x", pady=(4, 2))
                _ep_lbl(rk, "Key:").pack(anchor="w")
                key_e = tk.Entry(rk, textvariable=_ep_key,
                                 bg=BG, fg=FG, insertbackground=FG,
                                 font=("Segoe UI", 9), relief="flat", bd=0)
                key_e.pack(fill="x", pady=(2, 0), ipady=4)
                _ep_lbl(rk, "mis. enter, ctrl, f5").pack(anchor="w")
                _edit_widgets["key_e"] = key_e

            # Test Step + Apply buttons
            btn_sep = tk.Frame(edit_fields, bg=MUT, height=1)
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

            tk.Button(edit_fields, text="Test Step",
                      bg=CARD, fg=BLUE, relief="flat", bd=0,
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

            tk.Button(edit_fields, text="Terapkan",
                      bg=GRN, fg=BG, relief="flat", bd=0,
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
            popup = tk.Toplevel(dlg)
            popup.overrideredirect(True)
            popup.geometry("{}x{}+{}+{}".format(
                x1 - x0, y1 - y0,
                st.winfo_rootx() + x0,
                st.winfo_rooty() + y0))
            popup.configure(bg=ACC)

            cur_ms = int(round(step_data[orig_idx].get("delay", 0) * 1000))
            popup_var = tk.StringVar(value=str(cur_ms))
            popup_e = tk.Entry(popup, textvariable=popup_var,
                               bg=BG, fg=FG, insertbackground=FG,
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

        st.bind("<Double-ButtonPress-1>", _on_dbl_click)

        # ------------------------------------------------------------------ #
        #  Treeview selection → populate edit panel                           #
        # ------------------------------------------------------------------ #
        def _on_step_sel(event=None):
            sel = st.selection()
            if not sel:
                edit_header.configure(text="Pilih langkah untuk diedit", fg=MUT)
                return
            vis_idx  = st.index(sel[0])
            orig_idx = _filter_map[vis_idx] if _filter_map else vis_idx
            if orig_idx >= len(step_data):
                return
            a     = step_data[orig_idx]
            atype = a.get("type", "click")
            edit_header.configure(
                text="Edit Step #{} ({})".format(orig_idx + 1, atype), fg=ACC)
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
        bottom = tk.Frame(dlg, bg=SIDE, padx=12, pady=8)
        bottom.pack(fill="x", side="bottom")

        left_bottom = tk.Frame(bottom, bg=SIDE)
        left_bottom.pack(side="left", fill="y")

        _lbl(left_bottom, "Speed:", fg=MUT, bg=SIDE,
             font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        speed_var = tk.DoubleVar(
            value=float(existing.get("speed", 1.0)) if existing else 1.0)
        ttk.Combobox(left_bottom, textvariable=speed_var,
                     values=[0.25, 0.5, 1.0, 1.5, 2.0],
                     state="readonly", width=5).pack(side="left", padx=(0, 14))

        _lbl(left_bottom, "Ulangi:", fg=MUT, bg=SIDE,
             font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        repeat_var = tk.IntVar(
            value=int(existing.get("repeat", 1)) if existing else 1)
        repeat_sp = tk.Spinbox(left_bottom, from_=1, to=999999, width=6,
                               textvariable=repeat_var,
                               bg=CARD, fg=FG, insertbackground=FG,
                               relief="flat", font=("Segoe UI", 9))
        repeat_sp.pack(side="left", padx=(0, 14), ipady=2)

        silent_var = tk.BooleanVar(
            value=bool(existing.get("silent_mode", False)) if existing else False)
        tk.Checkbutton(left_bottom, text="Silent Mode",
                       variable=silent_var, bg=SIDE, fg=FG,
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

        tk.Checkbutton(left_bottom, text="Loop Tak Terbatas",
                       variable=unlimited_var, command=_toggle_unlimited,
                       bg=SIDE, fg=FG,
                       activebackground=SIDE, activeforeground=FG,
                       selectcolor=CARD,
                       font=("Segoe UI", 9)).pack(side="left")

        right_bottom = tk.Frame(bottom, bg=SIDE)
        right_bottom.pack(side="right", fill="y")

        warn_lbl = tk.Label(right_bottom,
                            text="Belum tersimpan", bg=SIDE, fg=YEL,
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
                messagebox.showinfo("Test Run", "Tidak ada langkah.",
                                    parent=dlg)
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
        tk.Button(right_bottom, text=lbl_save,
                  bg=GRN, fg="#FFFFFF",
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=16, pady=6, cursor="hand2",
                  activebackground="#3A9F70", activeforeground="#FFFFFF",
                  command=_save).pack(side="left", padx=(0, 6))

        tk.Button(right_bottom, text="Test Run",
                  bg=CARD, fg=FG, relief="flat", bd=0,
                  font=("Segoe UI", 9), padx=10, pady=6, cursor="hand2",
                  activebackground=ACC, activeforeground=BG,
                  command=_test_run).pack(side="left", padx=(0, 6))

        tk.Button(right_bottom, text="Batal",
                  bg=CARD, fg=MUT, relief="flat", bd=0,
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

        dlg = tk.Toplevel(self._root)
        dlg.title("Editor Langkah Rekaman")
        dlg.configure(bg=BG)
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
        hdr_f = tk.Frame(dlg, bg=BG)
        hdr_f.pack(fill="x", padx=20, pady=(16, 4))
        _lbl(hdr_f, "Editor Langkah Rekaman",
             font=("Segoe UI", 13, "bold"), bg=BG).pack(anchor="w")
        step_count_var = tk.StringVar(
            value="{} langkah   |   Klik baris untuk edit, lalu klik Perbarui".format(
                len(steps)))
        _lbl(hdr_f, "", fg=MUT, bg=BG, font=("Segoe UI", 9),
             textvariable=step_count_var).pack(anchor="w", pady=(2, 0))

        # Panduan cepat
        guide = tk.Frame(dlg, bg="#1A2A1A", padx=12, pady=8)
        guide.pack(fill="x", padx=20, pady=(0, 6))
        tk.Label(guide, text="Cara pakai: ",
                 bg="#1A2A1A", fg=GRN,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        tk.Label(guide,
                 text="Pilih baris di tabel -> Edit tipe & nilai di bawah -> Klik [Perbarui]. "
                      "Klik [+ Tambah] untuk langkah baru.",
                 bg="#1A2A1A", fg=FG,
                 font=("Segoe UI", 8), wraplength=580, justify="left").pack(
            side="left", fill="x", expand=True)

        lf = tk.Frame(dlg, bg=CARD, padx=8, pady=8)
        lf.pack(fill="both", expand=True, padx=20, pady=(0, 6))

        st = ttk.Treeview(lf, columns=("no", "type", "value"),
                          show="headings", selectmode="browse")
        st.heading("no",    text="#")
        st.heading("type",  text="Jenis Aksi")
        st.heading("value", text="Nilai / Target")
        st.column("no",    width=36, anchor="center")
        st.column("type",  width=130)
        st.column("value", width=420)
        vsb = ttk.Scrollbar(lf, orient="vertical", command=st.yview)
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
        form = tk.Frame(dlg, bg=CARD, padx=14, pady=10)
        form.pack(fill="x", padx=20, pady=(0, 4))

        type_var = tk.StringVar(value=_FRIENDLY_TYPES[0])
        val_var  = tk.StringVar()
        hint_var = tk.StringVar(value="Pilih jenis aksi untuk melihat petunjuk")

        r1 = tk.Frame(form, bg=CARD)
        r1.pack(fill="x", pady=(0, 4))
        _lbl(r1, "Jenis Aksi:", fg=MUT, bg=CARD, width=12, anchor="w").pack(side="left")
        type_cb = ttk.Combobox(r1, textvariable=type_var,
                               values=_FRIENDLY_TYPES,
                               state="readonly", width=18)
        type_cb.pack(side="left", padx=(0, 8))
        hint_lbl = tk.Label(r1, textvariable=hint_var,
                            bg=CARD, fg=MUT, font=("Segoe UI", 8),
                            anchor="w")
        hint_lbl.pack(side="left", fill="x", expand=True)

        def _update_hint(*_):
            eng = _FRIENDLY_TO_ENG.get(type_var.get(), type_var.get())
            hint_var.set(_TYPE_HINT.get(eng, ""))
        type_cb.bind("<<ComboboxSelected>>", _update_hint)

        r2 = tk.Frame(form, bg=CARD)
        r2.pack(fill="x")
        _lbl(r2, "Nilai / Target:", fg=MUT, bg=CARD, width=12, anchor="w").pack(
            side="left")
        ttk.Entry(r2, textvariable=val_var,
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

        btn_row = tk.Frame(form, bg=CARD)
        btn_row.pack(fill="x", pady=(8, 0))
        for txt, cmd, col in [
            ("Perbarui",  upd,       ACC),
            ("+ Tambah",  add,       GRN),
            ("Hapus",     delete,    RED),
            ("Naik",      move_up,   MUT),
            ("Turun",     move_down, MUT),
        ]:
            tk.Button(btn_row, text=txt, bg=col if col != MUT else CARD,
                      fg=BG if col != MUT else FG,
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

        sr = tk.Frame(dlg, bg=BG)
        sr.pack(fill="x", padx=20, pady=(0, 16))
        tk.Button(sr, text="Simpan Rekaman", bg=ACC, fg=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=16, pady=8, cursor="hand2",
                  command=save_rec).pack(side="left")
        ttk.Button(sr, text="Batal",
                   command=_on_editor_close).pack(side="left", padx=(8, 0))

        # Centre on screen, force render, bring to front
        dlg.update_idletasks()
        w, h = 720, 580
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry("{}x{}+{}+{}".format(
            w, h, (sw - w) // 2, (sh - h) // 2))
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()

    def _play_selected_recording(self):
        if not self._recordings_tree:
            return
        sel = self._recordings_tree.selection()
        if not sel:
            messagebox.showinfo("Mainkan",
                                "Pilih rekaman dari daftar terlebih dahulu.",
                                parent=self._root)
            return
        idx = self._recordings_tree.index(sel[0])
        if idx >= len(self._ud.recordings):
            return
        rec   = self._ud.recordings[idx]
        steps = rec.get("steps", [])
        if not steps:
            messagebox.showinfo("Mainkan",
                                "Rekaman ini tidak memiliki langkah apapun.",
                                parent=self._root)
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
        win = tk.Toplevel(self._root)
        win.title("Playing...")
        win.geometry("220x195")
        win.configure(bg=CARD)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        sw = self._root.winfo_screenwidth()
        win.geometry("220x195+{}+40".format(sw - 240))
        def _on_playback_close():
            self._playback_stop.set()
        win.protocol("WM_DELETE_WINDOW", _on_playback_close)

        _lbl(win, (name[:22] or "Playing Recording"),
             fg=ACC, bg=CARD, font=("Segoe UI", 10, "bold")).pack(
            pady=(12, 4), padx=12)
        step_var = tk.StringVar(value="Step 0 / {}".format(total))
        tk.Label(win, textvariable=step_var, fg=FG, bg=CARD,
                 font=("Segoe UI", 9)).pack(padx=12)
        desc_var = tk.StringVar(value="Preparing...")
        tk.Label(win, textvariable=desc_var, fg=MUT, bg=CARD,
                 font=("Segoe UI", 8), wraplength=196,
                 justify="left").pack(padx=12, pady=(2, 6))

        pct_var = tk.StringVar(value="0%")
        tk.Label(win, textvariable=pct_var, fg=GRN, bg=CARD,
                 font=("Consolas", 9, "bold")).pack(padx=12)
        pb = tk.Canvas(win, width=196, height=10, bg=BG, highlightthickness=0)
        pb.pack(padx=12, pady=(2, 8))
        win._pct_var = pct_var

        btn_row  = tk.Frame(win, bg=CARD)
        btn_row.pack(fill="x", padx=12, pady=(0, 12))
        pause_var = tk.StringVar(value="Pause")

        def toggle_pause():
            if self._playback_pause.is_set():
                self._playback_pause.clear()
                pause_var.set("Pause")
            else:
                self._playback_pause.set()
                pause_var.set("Resume")

        tk.Button(btn_row, textvariable=pause_var, bg=YEL, fg=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=8, pady=4, command=toggle_pause).pack(
            side="left", padx=(0, 4))
        tk.Button(btn_row, text="Stop", bg=RED, fg=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=8, pady=4,
                  command=self._playback_stop.set).pack(side="left")

        win._step_var = step_var
        win._desc_var = desc_var
        win._pb_canvas = pb
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
            if 0 <= idx < len(self._ud.recordings):
                self._ud.recordings[idx]["last_run"] = \
                    datetime.now().strftime("%Y-%m-%d %H:%M")
                self._ud.recordings[idx]["duration"] = duration
                self._ud.log("Play: {}".format(rec.get("name", "")),
                             "Simple playback done")
                self._ud.save()
            self._root.after(0, lambda: [
                self._close_playback_window(win),
                self._refresh_recordings_tree(),
                self._sv.set("Simple playback complete."),
            ])

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
                    self._rec_count_lbl.configure(text="", bg=CARD)
                else:
                    self._rec_count_lbl.configure(
                        text=" {} ".format(n), bg=ACC)
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
        dlg = tk.Toplevel(self._root)
        dlg.title("Hapus Rekaman")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.attributes("-topmost", True)
        dlg.overrideredirect(False)

        hdr = tk.Frame(dlg, bg=RED, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  Hapus Rekaman", bg=RED, fg="white",
                 font=("Segoe UI", 11, "bold")).pack(side="left", pady=10)

        body = tk.Frame(dlg, bg=BG, padx=24, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(body,
                 text='Yakin hapus rekaman ini?',
                 bg=BG, fg=FG, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(body, text='"{}"'.format(name),
                 bg=BG, fg=ACC2, font=("Segoe UI", 10, "italic"),
                 wraplength=320).pack(anchor="w", pady=(4, 12))
        tk.Label(body, text="Rekaman yang dihapus tidak bisa dipulihkan.",
                 bg=BG, fg=MUT, font=("Segoe UI", 8)).pack(anchor="w")

        result = [False]
        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(anchor="w", pady=(16, 0))

        def _yes():
            result[0] = True
            dlg.destroy()

        tk.Button(btn_row, text="Hapus", bg=RED, fg="white",
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=18, pady=7, cursor="hand2",
                  command=_yes).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Batal", bg=CARD, fg=FG,
                  font=("Segoe UI", 10), relief="flat", bd=0,
                  padx=14, pady=7, cursor="hand2",
                  command=dlg.destroy).pack(side="left")

        dlg.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        w, h = 380, 220
        dlg.geometry("{}x{}+{}+{}".format(w, h, (sw - w) // 2, (sh - h) // 2))
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
        dlg = tk.Toplevel(parent)
        dlg.title("Nama Rekaman")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.attributes("-topmost", True)

        # ── Header ────────────────────────────────────────────────────
        hdr = tk.Frame(dlg, bg=ACC, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  Simpan Rekaman",
                 bg=ACC, fg="white",
                 font=("Segoe UI", 12, "bold")).pack(side="left", pady=12, padx=4)

        # ── Body ──────────────────────────────────────────────────────
        body = tk.Frame(dlg, bg=BG, padx=24, pady=20)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Nama Rekaman",
                 bg=BG, fg=FG,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")

        # Entry with rounded-look border frame
        ef = tk.Frame(body, bg=ACC, padx=1, pady=1)
        ef.pack(fill="x", pady=(4, 2))
        name_entry = tk.Entry(ef, bg=CARD2, fg=FG, insertbackground=FG,
                              relief="flat", font=("Segoe UI", 11),
                              bd=6)
        name_entry.pack(fill="x")
        if current_name:
            name_entry.insert(0, current_name)
            name_entry.select_range(0, "end")

        tk.Label(body,
                 text="Contoh: Login Admin, Isi Form Pesanan, Klik Tombol Beli",
                 bg=BG, fg=MUT,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 14))

        # ── Buttons ───────────────────────────────────────────────────
        result = [""]
        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(anchor="w")

        def _save():
            val = name_entry.get().strip()
            if not val:
                name_entry.configure(bg="#3A1A1A")
                name_entry.focus_set()
                return
            result[0] = val
            dlg.destroy()

        def _cancel():
            dlg.destroy()

        tk.Button(btn_row, text="Simpan", bg=ACC, fg="white",
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=20, pady=8, cursor="hand2",
                  command=_save).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Batal", bg=CARD, fg=FG,
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
        for task in self._ud.tasks:
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

    def _run_selected_task(self):
        if not self._tasks_tree:
            return
        sel = self._tasks_tree.selection()
        if not sel:
            messagebox.showinfo("Run Task", "Select a task first.",
                                parent=self._root)
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

        dlg = tk.Toplevel(self._root)
        dlg.title("Confirm Run")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.attributes("-topmost", True)

        tk.Label(dlg, text='Run: "{}"'.format(task.get("name", "")),
                 bg=BG, fg=FG, font=("Segoe UI", 12, "bold"),
                 padx=20, pady=(14)).pack(anchor="w")
        tk.Label(dlg, text=msg, bg=BG, fg=MUT,
                 font=("Segoe UI", 9), justify="left",
                 padx=20).pack(anchor="w")

        result = [False]
        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(fill="x", padx=20, pady=14)

        def _yes():
            result[0] = True
            dlg.destroy()

        def _no():
            dlg.destroy()

        tk.Button(btn_row, text="Yes, Run", bg=GRN, fg=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=16, pady=7, cursor="hand2",
                  command=_yes).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Cancel", bg=CARD, fg=FG,
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
        self._root.wait_window(dlg)
        return result[0]

    def _show_run_progress_panel(self, task: dict, stop_flag) -> dict:
        """Show a floating live progress panel. Returns dict of widget refs."""
        steps = task.get("steps", [])
        total = len(steps)

        w = tk.Toplevel(self._root)
        w.title("Running: {}".format(task.get("name", "")))
        w.configure(bg=BG)
        w.resizable(False, False)
        w.attributes("-topmost", True)
        w.geometry("440x340")

        tk.Label(w, text="Running: {}".format(task.get("name", "")),
                 bg=BG, fg=FG, font=("Segoe UI", 11, "bold"),
                 padx=16, pady=10).pack(anchor="w")

        step_lbl = tk.Label(w, text="Preparing...",
                            bg=BG, fg=ACC, font=("Segoe UI", 10),
                            padx=16, anchor="w")
        step_lbl.pack(fill="x")

        progress_var = tk.DoubleVar(value=0.0)
        pb = ttk.Progressbar(w, variable=progress_var, maximum=total or 1,
                             length=400, mode="determinate")
        pb.pack(padx=16, pady=(6, 0))

        log_frame = tk.Frame(w, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(8, 0))
        log_box = scrolledtext.ScrolledText(
            log_frame, bg=CARD, fg=FG, font=("Consolas", 8),
            relief="flat", height=8, state="disabled")
        log_box.pack(fill="both", expand=True)
        log_box.tag_configure("ok",   foreground=GRN)
        log_box.tag_configure("fail", foreground=RED)
        log_box.tag_configure("info", foreground=MUT)

        btn_row = tk.Frame(w, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=10)

        def _stop():
            stop_flag.set()
            stop_btn.configure(state="disabled", text="Stopping...")

        stop_btn = tk.Button(btn_row, text="Stop", bg=RED, fg=BG,
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
        return panel

    def _run_task_thread(self, task, idx, stop_flag=None, panel=None):
        self._root.after(0, lambda: self._sv.set(
            "Running: {}...".format(task["name"])))
        # Mark as Running immediately so the tree shows yellow status
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
                    panel["step_lbl"].configure(
                        text="Done: {}/{} steps OK".format(ok_count, total))
                    panel["window"].after(
                        4000,
                        lambda: panel["window"].destroy()
                        if panel["window"].winfo_exists() else None)
                except Exception:
                    pass
            if status == "OK":
                self._toast_success(
                    "Done! Task '{}': {}/{} steps completed.".format(
                        task["name"], ok_count, total))
                self._sv.set("Task '{}' finished OK.".format(task["name"]))
            else:
                from utils.error_handler import friendly_message
                msg = (friendly_message(exc_ref) if exc_ref
                       else "Task '{}' failed: {}/{} steps completed.".format(
                           task["name"], ok_count, total))
                self._toast_error(msg, exc_ref)
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
        w = tk.Toplevel(self._root)
        w.title("Bulk Order Confirmation")
        w.configure(bg=BG)
        w.resizable(False, False)
        w.attributes("-topmost", True)
        w.geometry("400x530")

        # ── Title row ────────────────────────────────────────────────
        title_frame = tk.Frame(w, bg=CARD, padx=12, pady=10)
        title_frame.pack(fill="x")
        tk.Label(title_frame,
                 text=task.get("name", "Bulk Order Confirmation"),
                 bg=CARD, fg=FG, font=("Segoe UI", 11, "bold")).pack(side="left")
        loop_lbl = tk.Label(title_frame, text="[● READY]",
                            bg=CARD, fg=GRN, font=("Segoe UI", 9, "bold"))
        loop_lbl.pack(side="right")

        tk.Frame(w, bg=MUT, height=1).pack(fill="x")

        # ── This loop stats ───────────────────────────────────────────
        loop_frame = tk.Frame(w, bg=BG, padx=14, pady=8)
        loop_frame.pack(fill="x")
        tk.Label(loop_frame, text="This loop:",
                 bg=BG, fg=MUT, font=("Segoe UI", 8, "bold")).pack(anchor="w")

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
            tk.Label(loop_frame, textvariable=var,
                     bg=BG, fg=_stat_colors[key],
                     font=("Segoe UI", 9)).pack(anchor="w", padx=(10, 0))

        tk.Frame(w, bg=MUT, height=1).pack(fill="x")

        # ── All-time totals ───────────────────────────────────────────
        totals_frame = tk.Frame(w, bg=BG, padx=14, pady=8)
        totals_frame.pack(fill="x")
        tk.Label(totals_frame, text="All time totals:",
                 bg=BG, fg=MUT, font=("Segoe UI", 8, "bold")).pack(anchor="w")

        totals_vars = {
            "confirmed_total":   tk.StringVar(value="Confirmed: 0 orders"),
            "mismatches_total":  tk.StringVar(value="Mismatches: 0"),
            "unverified_total":  tk.StringVar(value="Unverified on web: 0"),
        }
        _tot_colors = {
            "confirmed_total": GRN, "mismatches_total": RED, "unverified_total": YEL,
        }
        for key, var in totals_vars.items():
            tk.Label(totals_frame, textvariable=var,
                     bg=BG, fg=_tot_colors[key],
                     font=("Segoe UI", 9)).pack(anchor="w", padx=(10, 0))

        tk.Frame(w, bg=MUT, height=1).pack(fill="x")

        # ── Live log ──────────────────────────────────────────────────
        log_frame = tk.Frame(w, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=14, pady=(6, 0))
        log_box = scrolledtext.ScrolledText(
            log_frame, bg=CARD, fg=FG, font=("Consolas", 7),
            relief="flat", height=6, state="disabled")
        log_box.pack(fill="both", expand=True)
        log_box.tag_configure("ok",   foreground=GRN)
        log_box.tag_configure("warn", foreground=YEL)
        log_box.tag_configure("fail", foreground=RED)
        log_box.tag_configure("info", foreground=MUT)

        tk.Frame(w, bg=MUT, height=1).pack(fill="x")

        # ── Countdown + buttons ───────────────────────────────────────
        bottom = tk.Frame(w, bg=BG, padx=14, pady=10)
        bottom.pack(fill="x")

        countdown_var = tk.StringVar(value="")
        tk.Label(bottom, textvariable=countdown_var,
                 bg=BG, fg=ACC, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))

        btn_row = tk.Frame(bottom, bg=BG)
        btn_row.pack(fill="x")

        def _stop():
            stop_flag.set()
            stop_btn.configure(state="disabled", text="Stopping...")

        def _export():
            date_str = datetime.now().strftime("%Y-%m-%d")
            csv_path = os.path.join(_ROOT, "data",
                                    "confirmation_report_{}.csv".format(date_str))
            if os.path.exists(csv_path):
                messagebox.showinfo(
                    "Export Report",
                    "Report saved at:\n{}".format(csv_path),
                    parent=w)
            else:
                messagebox.showinfo(
                    "Export Report",
                    "No report data yet for today.",
                    parent=w)

        stop_btn = tk.Button(btn_row, text="STOP", bg=RED, fg=BG,
                             font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                             padx=12, pady=5, cursor="hand2", command=_stop)
        stop_btn.pack(side="left", padx=(0, 8))

        tk.Button(btn_row, text="Export Report", bg=CARD, fg=FG,
                  font=("Segoe UI", 9), relief="flat", bd=0,
                  padx=12, pady=5, cursor="hand2",
                  command=_export).pack(side="left")

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
                            text="[● RUNNING] Loop #{}".format(loop), fg=GRN)
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
                            text="[◷ WAITING] Loop #{}".format(loop), fg=MUT)

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
                        text="[■ STOPPED]", fg=MUT)
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
        if messagebox.askyesno("Delete Task",
                               "Delete macro '{}'?".format(name),
                               parent=self._root):
            task_id = self._ud.tasks[idx].get("id", "")
            if task_id and self.engine and self.engine.scheduler:
                self.engine.scheduler.remove_job("task_{}".format(task_id))
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
        self._ud.tasks[idx]["enabled"] = not self._ud.tasks[idx].get(
            "enabled", True)
        self._ud.save()
        if self.engine:
            self.engine.register_task(self._ud.tasks[idx])
        self._refresh_tasks_tree()

    # ================================================================
    #  Toast notification
    # ================================================================

    def _show_toast(self, message, kind="info", details=None):
        """
        Show a toast notification in the bottom-right corner.

        kind:
          "info"    - accent colour (default)
          "success" - green  (GRN)
          "warning" - yellow (YEL)
          "error"   - red    (RED)

        details: optional technical string shown when user clicks 'Show Details'.
        """
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(
                "Synthex",
                message[:100],
                duration=4,
                threaded=True,
                icon_path=None,
            )
        except Exception:
            pass

        try:
            if not self._root or not self._root.winfo_exists():
                return
            colour_map = {
                "success": GRN,
                "warning": YEL,
                "error":   RED,
            }
            bg = colour_map.get(kind, ACC)
            fg = BG  # dark text on all backgrounds

            w = tk.Toplevel(self._root)
            w.overrideredirect(True)
            w.attributes("-topmost", True)
            w.configure(bg=bg)

            # Wrap long messages at 60 chars so the toast stays readable
            import textwrap
            wrapped = "\n".join(textwrap.wrap(message[:200], width=60))
            tk.Label(w, text=wrapped, bg=bg, fg=fg,
                     font=("Segoe UI", 10, "bold"),
                     padx=16, pady=10, justify="left").pack(anchor="w")

            if details:
                _details = details  # capture for lambda

                def _show_details():
                    dw = tk.Toplevel(self._root)
                    dw.title("Error Details")
                    dw.configure(bg=BG)
                    dw.geometry("600x320")
                    st = scrolledtext.ScrolledText(
                        dw, bg=CARD, fg=MUT,
                        font=("Consolas", 9), relief="flat")
                    st.pack(fill="both", expand=True, padx=12, pady=12)
                    st.insert(tk.END, _details)
                    st.configure(state="disabled")
                    ttk.Button(dw, text="Close",
                               command=dw.destroy).pack(pady=(0, 10))

                btn_row = tk.Frame(w, bg=bg)
                btn_row.pack(fill="x", padx=12, pady=(0, 8))
                tk.Button(btn_row, text="Show Details",
                          bg=bg, fg=fg,
                          font=("Segoe UI", 8), relief="flat", bd=0,
                          cursor="hand2",
                          command=_show_details).pack(side="left")
                tk.Button(btn_row, text="Dismiss",
                          bg=bg, fg=fg,
                          font=("Segoe UI", 8), relief="flat", bd=0,
                          cursor="hand2",
                          command=w.destroy).pack(side="right")

            w.update_idletasks()
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            ww = w.winfo_reqwidth()
            wh = w.winfo_reqheight()
            w.geometry("{}x{}+{}+{}".format(
                ww, wh, sw - ww - 20, sh - wh - 60))
            auto_close = 6000 if kind == "error" else 4000
            w.after(auto_close, lambda: w.destroy() if w.winfo_exists() else None)
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

    def _logout(self):
        import os
        if not messagebox.askyesno("Logout", "Are you sure you want to log out?",
                                   parent=self._root):
            return
        # Clear token file
        token_path = os.path.join(os.environ.get("APPDATA", ""), "Synthex", "token.json")
        if os.path.exists(token_path):
            os.remove(token_path)
        # Clear stay-logged-in config
        self.config.set("ui.stay_logged_in", False)
        self.config.set("ui.last_email", "")
        self.config.save()
        # Just close - user reopens manually
        self._root.destroy()

    def _start_tray(self):
        def _run():
            img = Image.new("RGB", (64, 64), ACC)
            ImageDraw.Draw(img).ellipse([8, 8, 56, 56], fill=BG)
            self._tray = pystray.Icon("synthex", img, "Synthex",
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
            )
            self._hkl.daemon = True
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
             "beda spreadsheet atau beda Gmail.",
             fg=MUT, bg=CARD, font=("Segoe UI", 9),
             justify="left").pack(anchor="w", pady=(0, 10))

        # Accounts list frame
        list_frame = tk.Frame(card, bg=CARD)
        list_frame.pack(fill="x", pady=(0, 8))

        def _refresh_accounts():
            for w in list_frame.winfo_children():
                w.destroy()
            accounts = _sc.list_accounts()
            if not accounts:
                _lbl(list_frame,
                     "Belum ada akun Google terhubung.",
                     fg=MUT, bg=CARD, font=("Segoe UI", 9)).pack(anchor="w")
                return

            # Header
            hdr = tk.Frame(list_frame, bg=SIDE)
            hdr.pack(fill="x", pady=(0, 2))
            for txt, w in [("Nama", 110), ("Service Account Email", 280),
                           ("Status", 70), ("Aksi", 120)]:
                tk.Label(hdr, text=txt, bg=SIDE, fg=MUT,
                         font=("Segoe UI", 8, "bold"),
                         width=w // 8, anchor="w").pack(side="left", padx=4)

            for acc in accounts:
                row = tk.Frame(list_frame, bg=BG, pady=3)
                row.pack(fill="x")

                # Name
                name_lbl = tk.Label(row, text=acc["name"], bg=BG, fg=FG,
                                    font=("Segoe UI", 9, "bold"),
                                    width=14, anchor="w")
                name_lbl.pack(side="left", padx=(4, 0))

                # Email (with copy button)
                email_frame = tk.Frame(row, bg=BG)
                email_frame.pack(side="left", padx=(4, 0))
                email_txt = acc["email"] or "(invalid)"
                tk.Label(email_frame, text=email_txt[:38],
                         bg=BG, fg=GRN if acc["email"] else RED,
                         font=("Consolas", 8), anchor="w").pack(side="left")
                tk.Button(email_frame, text="copy", bg=BG, fg=MUT,
                          font=("Segoe UI", 7), relief="flat", bd=0,
                          cursor="hand2", padx=4,
                          command=lambda e=acc["email"]: [
                              self._root.clipboard_clear(),
                              self._root.clipboard_append(e),
                              self._sv.set("Email disalin: {}".format(e))
                          ]).pack(side="left")

                # Active badge
                if acc["active"]:
                    tk.Label(row, text=" AKTIF ", bg=GRN, fg=BG,
                             font=("Segoe UI", 7, "bold"),
                             padx=4).pack(side="left", padx=(8, 0))
                else:
                    tk.Button(row, text="Aktifkan", bg=CARD, fg=ACC,
                              font=("Segoe UI", 8), relief="flat", bd=0,
                              padx=6, pady=2, cursor="hand2",
                              command=lambda n=acc["name"]: [
                                  _sc.set_active_account(n),
                                  _refresh_accounts(),
                                  self._navigate("sheet"),
                                  self._sv.set("Akun aktif: {}".format(n))
                              ]).pack(side="left", padx=(8, 0))

                # Delete
                tk.Button(row, text="Hapus", bg=CARD, fg=RED,
                          font=("Segoe UI", 8), relief="flat", bd=0,
                          padx=6, pady=2, cursor="hand2",
                          command=lambda n=acc["name"]: self._google_remove_account(
                              n, _refresh_accounts)
                          ).pack(side="right", padx=(0, 4))

        _refresh_accounts()

        # Action buttons
        btn_row = tk.Frame(card, bg=CARD)
        btn_row.pack(anchor="w", pady=(4, 0))
        tk.Button(btn_row, text="+ Tambah Akun Google",
                  bg=ACC, fg=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
                  command=lambda: self._show_sheets_setup_guide(
                      on_done=_refresh_accounts)
                  ).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Panduan Setup",
                  bg=CARD, fg=FG, font=("Segoe UI", 9),
                  relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
                  command=lambda: self._show_sheets_setup_guide()
                  ).pack(side="left")

    def _google_remove_account(self, name, refresh_cb):
        from modules.sheets import connector as _sc
        if not messagebox.askyesno(
                "Hapus Akun",
                "Hapus akun '{}'?\nSemua sheet yang pakai akun ini "
                "perlu disetup ulang.".format(name),
                parent=self._root):
            return
        _sc.remove_account(name)
        refresh_cb()
        self._sv.set("Akun '{}' dihapus.".format(name))

    def _show_sheets_setup_guide(self, on_done=None):
        """Step-by-step beginner wizard for Google Sheets setup."""
        import webbrowser
        from tkinter import filedialog
        from modules.sheets import connector as _sc

        dlg = tk.Toplevel(self._root)
        dlg.title("Setup Google Sheets — Panduan Langkah demi Langkah")
        dlg.geometry("560x500")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
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
        hdr = tk.Frame(dlg, bg=ACC, height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  Panduan Setup Google Sheets", bg=ACC, fg=BG,
                 font=("Segoe UI", 12, "bold")).pack(side="left", pady=12)
        tk.Button(hdr, text="X", bg=ACC, fg=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=10, cursor="hand2",
                  command=dlg.destroy).pack(side="right", padx=8, pady=10)

        # ── Progress dots ─────────────────────────────────────────────────
        dot_frame = tk.Frame(dlg, bg=BG, pady=8)
        dot_frame.pack(fill="x", padx=20)
        dot_labels = []
        for i, s in enumerate(STEPS):
            lbl = tk.Label(dot_frame, text=" ", bg=SIDE, width=4, height=1)
            lbl.pack(side="left", padx=3)
            dot_labels.append((lbl, s["color"]))

        # ── Content area ──────────────────────────────────────────────────
        content_frame = tk.Frame(dlg, bg=BG)
        content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # ── Bottom nav ────────────────────────────────────────────────────
        nav = tk.Frame(dlg, bg=CARD, pady=10)
        nav.pack(fill="x", side="bottom")

        btn_prev = tk.Button(nav, text="< Kembali", bg=SIDE, fg=FG,
                             font=("Segoe UI", 9), relief="flat", bd=0,
                             padx=14, pady=6, cursor="hand2")
        btn_prev.pack(side="left", padx=16)

        step_lbl = tk.Label(nav, text="", bg=CARD, fg=MUT,
                            font=("Segoe UI", 9))
        step_lbl.pack(side="left", expand=True)

        btn_close = tk.Button(nav, text="Tutup", bg=SIDE, fg=FG,
                              font=("Segoe UI", 9), relief="flat", bd=0,
                              padx=14, pady=6, cursor="hand2",
                              command=dlg.destroy)
        btn_close.pack(side="right", padx=16)

        btn_next = tk.Button(nav, text="Lanjut >", bg=ACC, fg=BG,
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
                lbl.configure(bg=col if i == idx else SIDE)

            step_lbl.configure(text="Langkah {} dari {}".format(idx + 1, total))
            btn_prev.configure(state="normal" if idx > 0 else "disabled")
            is_last = idx == total - 1
            btn_next.configure(
                text="Selesai!" if is_last else "Lanjut >",
                bg=GRN if is_last else ACC)

            top_row = tk.Frame(content_frame, bg=BG)
            top_row.pack(fill="x", pady=(8, 4))
            tk.Label(top_row, text=step["icon"], bg=step["color"], fg=BG,
                     font=("Segoe UI", 11, "bold"), width=3, pady=4,
                     ).pack(side="left")
            tk.Label(top_row, text="  " + step["title"], bg=BG, fg=FG,
                     font=("Segoe UI", 11, "bold"), anchor="w",
                     ).pack(side="left", fill="x", expand=True)

            tk.Frame(content_frame, bg=SIDE, height=1).pack(fill="x", pady=(4, 10))

            tk.Label(content_frame, text=step["body"], bg=BG, fg=MUT,
                     font=("Segoe UI", 10), justify="left", anchor="nw",
                     wraplength=500).pack(anchor="w", fill="x")

            if step.get("btn_label"):
                tk.Button(content_frame, text=step["btn_label"],
                          bg=step["color"], fg=BG,
                          font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                          padx=14, pady=7, cursor="hand2",
                          command=step["btn_cmd"]).pack(anchor="w", pady=(14, 0))

            if step.get("is_upload"):
                up_row = tk.Frame(content_frame, bg=BG)
                up_row.pack(fill="x", pady=(12, 0))
                tk.Label(up_row, text="Nama akun (bebas):", bg=BG, fg=MUT,
                         font=("Segoe UI", 9)).pack(side="left")
                tk.Entry(up_row, textvariable=upload_name_var,
                         bg=CARD, fg=FG, insertbackground=ACC,
                         font=("Segoe UI", 10), relief="flat",
                         bd=0, highlightthickness=1,
                         highlightbackground=SIDE, highlightcolor=ACC,
                         width=18).pack(side="left", padx=(8, 0))

                status_up = tk.Label(content_frame, textvariable=upload_status_var,
                                     bg=BG, fg=GRN, font=("Segoe UI", 9),
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
                        s_lbl.configure(fg=GRN)
                        if on_done:
                            on_done()
                        nonlocal active_email_now
                        acts = _sc.list_accounts()
                        active_email_now = next(
                            (a["email"] for a in acts if a["active"]), msg)
                    else:
                        upload_status_var.set("Gagal: {}".format(msg))
                        s_lbl.configure(fg=RED)

                tk.Button(content_frame, text="Pilih File credentials.json",
                          bg=ACC, fg=BG, font=("Segoe UI", 10, "bold"),
                          relief="flat", bd=0, padx=16, pady=8,
                          cursor="hand2", command=_do_upload
                          ).pack(anchor="w", pady=(10, 0))
                status_up.pack(anchor="w", pady=(6, 0))

            if step.get("is_share"):
                email_show = active_email_now
                if not email_show:
                    acts = _sc.list_accounts()
                    email_show = next((a["email"] for a in acts if a["active"]), "")

                share_f = tk.Frame(content_frame, bg=CARD, padx=14, pady=12)
                share_f.pack(fill="x", pady=(14, 0))
                tk.Label(share_f,
                         text="Email service account (salin & tempel ke Share):",
                         bg=CARD, fg=YEL,
                         font=("Segoe UI", 9, "bold")).pack(anchor="w")
                em_row = tk.Frame(share_f, bg=CARD)
                em_row.pack(fill="x", pady=(6, 0))
                disp = email_show or "(belum ada akun - selesaikan langkah 5 dulu)"
                tk.Label(em_row, text=disp, bg=CARD, fg=GRN,
                         font=("Consolas", 10, "bold")).pack(side="left")
                if email_show:
                    tk.Button(em_row, text="Salin",
                              bg=ACC, fg=BG,
                              font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                              padx=10, pady=3, cursor="hand2",
                              command=lambda e=email_show: [
                                  self._root.clipboard_clear(),
                                  self._root.clipboard_append(e),
                                  self._sv.set("Email disalin!")
                              ]).pack(side="left", padx=(10, 0))

                tk.Button(content_frame, text="Buka Google Sheets sekarang",
                          bg=GRN, fg=BG,
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
    # ================================================================
    #  TEMPLATES PAGE
    # ================================================================

    def _pg_templates(self):
        f = tk.Frame(self._content, bg=BG)
        self._hdr(f, "Template Macros",
                  "Pilih template siap pakai, kustomisasi, lalu simpan sebagai macro.")

        templates = _load_templates()
        if not templates:
            _lbl(f, "Tidak ada template ditemukan.",
                 fg=MUT, font=("Segoe UI", 10)).pack(padx=24, pady=20)
            return f

        # Scrollable canvas
        canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG)
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

            card = tk.Frame(inner, bg=CARD, padx=0, pady=0)
            card.pack(fill="x", padx=20, pady=(0, 14))

            # Color stripe on left
            tk.Frame(card, bg=card_acc, width=5).pack(side="left", fill="y")

            body = tk.Frame(card, bg=CARD, padx=16, pady=12)
            body.pack(side="left", fill="both", expand=True)

            # Header row
            hrow = tk.Frame(body, bg=CARD)
            hrow.pack(fill="x")
            cont = tk.BooleanVar(value=tpl.get("continuous_mode", False))
            _lbl(hrow, tpl.get("name", ""), bg=CARD, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
            if cont.get():
                tk.Label(hrow, text=" LOOP ", bg=YEL, fg=BG,
                         font=("Segoe UI", 7, "bold"),
                         padx=4).pack(side="left", padx=(8, 0))
            steps_count = len(tpl.get("steps", []))
            _lbl(hrow, "  {} steps".format(steps_count), fg=MUT, bg=CARD,
                 font=("Segoe UI", 9)).pack(side="left")

            _lbl(body, tpl.get("description", ""), fg=MUT, bg=CARD,
                 font=("Segoe UI", 9), justify="left").pack(
                anchor="w", pady=(4, 8))

            # Step preview chips
            chip_row = tk.Frame(body, bg=CARD)
            chip_row.pack(fill="x", pady=(0, 10))
            for step in tpl.get("steps", [])[:8]:
                stype = step.get("type", "")
                icon  = _TICONS.get(stype, "[?]")
                clr   = _TCOLORS.get(stype, MUT)
                chip  = tk.Frame(chip_row, bg=BG, padx=5, pady=2)
                chip.pack(side="left", padx=(0, 4), pady=2)
                tk.Label(chip, text=icon, bg=BG, fg=clr,
                         font=("Consolas", 8)).pack()
            if steps_count > 8:
                tk.Label(chip_row, text="+{}".format(steps_count - 8),
                         bg=BG, fg=MUT, font=("Consolas", 8),
                         padx=4, pady=2).pack(side="left")

            # Action buttons
            btn_row = tk.Frame(body, bg=CARD)
            btn_row.pack(anchor="w")
            tk.Button(
                btn_row, text="Load Template",
                bg=card_acc, fg=BG,
                font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                padx=14, pady=5, cursor="hand2",
                command=lambda t=tpl: self._mb_open_with_template(t)
            ).pack(side="left", padx=(0, 8))
            tk.Button(
                btn_row, text="Preview Steps",
                bg=CARD, fg=FG,
                font=("Segoe UI", 9), relief="flat", bd=0,
                padx=10, pady=5, cursor="hand2",
                command=lambda t=tpl: self._template_preview(t)
            ).pack(side="left")

        return f

    def _template_preview(self, tpl):
        """Show a popup with all steps of a template."""
        dlg = tk.Toplevel(self._root)
        dlg.title("Preview: {}".format(tpl.get("name", "")))
        dlg.geometry("560x480")
        dlg.configure(bg=BG)
        dlg.resizable(True, True)

        _lbl(dlg, tpl.get("name", ""),
             font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=20, pady=(16, 2))
        _lbl(dlg, tpl.get("description", ""),
             fg=MUT, font=("Segoe UI", 9)).pack(anchor="w", padx=20, pady=(0, 10))
        tk.Frame(dlg, bg=SIDE, height=1).pack(fill="x", padx=20)

        lf = tk.Frame(dlg, bg=CARD, padx=10, pady=10)
        lf.pack(fill="both", expand=True, padx=20, pady=10)

        st = ttk.Treeview(lf, columns=("no", "type", "detail"),
                          show="headings", selectmode="browse")
        st.heading("no",     text="#")
        st.heading("type",   text="Type")
        st.heading("detail", text="Detail")
        st.column("no",     width=36,  anchor="center")
        st.column("type",   width=160, anchor="w")
        st.column("detail", width=310, anchor="w")
        vsb = ttk.Scrollbar(lf, orient="vertical", command=st.yview)
        st.configure(yscrollcommand=vsb.set)
        st.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for i, step in enumerate(tpl.get("steps", []), 1):
            st.insert("", "end", values=(i, step.get("type", ""), _step_label(step)))

        btn_f = tk.Frame(dlg, bg=BG)
        btn_f.pack(fill="x", padx=20, pady=(0, 16))
        tk.Button(btn_f, text="Load this Template", bg=ACC, fg=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=14, pady=7, cursor="hand2",
                  command=lambda: [dlg.destroy(),
                                   self._mb_open_with_template(tpl)]).pack(side="left")
        ttk.Button(btn_f, text="Close", command=dlg.destroy).pack(
            side="left", padx=(10, 0))

    # ================================================================
    #  LOGS PAGE  (Live log viewer)
    # ================================================================

    def _pg_logs(self):
        f = tk.Frame(self._content, bg=BG)
        self._hdr(f, "Live Logs",
                  "Semua event & error Synthex ditampilkan di sini secara real-time.")

        # Toolbar
        tb = tk.Frame(f, bg=BG)
        tb.pack(fill="x", padx=20, pady=(0, 6))

        level_var = tk.StringVar(value="ALL")
        for lv in ("ALL", "INFO", "WARNING", "ERROR"):
            tk.Radiobutton(tb, text=lv, variable=level_var, value=lv,
                           bg=BG, fg=FG, selectcolor=CARD,
                           activebackground=BG, activeforeground=ACC,
                           font=("Segoe UI", 8),
                           command=lambda: None).pack(side="left", padx=(0, 8))

        tk.Button(tb, text="Clear", bg=CARD, fg=RED,
                  font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                  padx=10, pady=3, cursor="hand2",
                  command=lambda: [
                      lw.configure(state="normal"),
                      lw.delete("1.0", tk.END),
                      lw.configure(state="disabled")
                  ]).pack(side="right")
        tk.Button(tb, text="Copy All", bg=CARD, fg=FG,
                  font=("Segoe UI", 8), relief="flat", bd=0,
                  padx=10, pady=3, cursor="hand2",
                  command=lambda: [
                      self._root.clipboard_clear(),
                      self._root.clipboard_append(
                          lw.get("1.0", tk.END))
                  ]).pack(side="right", padx=(0, 6))

        # Log widget
        lf = tk.Frame(f, bg=CARD, padx=6, pady=6)
        lf.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        lw = scrolledtext.ScrolledText(
            lf, bg="#0A0A0F", fg=FG, insertbackground=FG,
            font=("Consolas", 9), relief="flat", state="disabled",
            wrap="word")
        lw.pack(fill="both", expand=True)

        for tag, clr in [("info",  FG), ("warn", YEL),
                         ("error", RED), ("debug", MUT),
                         ("ok",    GRN), ("fail", RED)]:
            lw.tag_configure(tag, foreground=clr)

        # Attach logger handler
        handler = _TkLogHandler(lw)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  [%(name)-12s]  %(levelname)-7s  %(message)s",
            "%H:%M:%S"))
        logging.getLogger().addHandler(handler)

        # Store ref so we can detach on page destroy
        def _on_destroy(e, h=handler):
            try:
                logging.getLogger().removeHandler(h)
            except Exception:
                pass
        f.bind("<Destroy>", _on_destroy)

        # Guide hint
        tk.Label(f, text="Logs dari semua modul (browser, sheets, scheduler, macro) muncul otomatis.",
                 bg=BG, fg=MUT, font=("Segoe UI", 7)).pack(padx=20, pady=(0, 4))
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

        dlg = tk.Toplevel(self._root)
        dlg.title("Panduan - {}".format(page.capitalize()))
        dlg.geometry("480x400")
        dlg.configure(bg=BG)
        dlg.resizable(True, True)
        dlg.attributes("-topmost", True)

        # Header
        hdr = tk.Frame(dlg, bg=ACC, height=42)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  Panduan: {}".format(page.upper()),
                 bg=ACC, fg=BG, font=("Segoe UI", 11, "bold")).pack(
            side="left", pady=10)
        tk.Button(hdr, text="X", bg=ACC, fg=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                  padx=10, cursor="hand2",
                  command=dlg.destroy).pack(side="right", pady=8, padx=8)

        # Content
        txt = scrolledtext.ScrolledText(
            dlg, bg=CARD, fg=FG, font=("Segoe UI", 10),
            relief="flat", wrap="word", padx=16, pady=12,
            state="normal")
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.insert("1.0", text)
        txt.configure(state="disabled")

        # Tip: navigate to other helps
        nav_f = tk.Frame(dlg, bg=BG)
        nav_f.pack(fill="x", padx=10, pady=(0, 10))
        _lbl(nav_f, "Panduan lain:", fg=MUT, bg=BG,
             font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))
        for pg in ("home", "record", "spy", "schedule", "templates", "sheet", "logs"):
            if pg != page:
                tk.Button(nav_f, text=pg, bg=CARD, fg=MUT,
                          font=("Segoe UI", 7), relief="flat", bd=0,
                          padx=6, pady=2, cursor="hand2",
                          command=lambda p=pg, d=dlg: [
                              d.destroy(), self._show("{}".format(p)),
                              self._root.after(50, self._show_help)
                          ]).pack(side="left", padx=(0, 3))

    def _quit(self):
        """Tampilkan konfirmasi close yang menarik, lalu keluar + logout."""
        dlg = tk.Toplevel(self._root)
        dlg.title("")
        dlg.resizable(False, False)
        dlg.configure(bg="#0D0D14")
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)

        W, H = 360, 210
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        dlg.geometry("{}x{}+{}+{}".format(W, H, (sw - W) // 2, (sh - H) // 2))

        # Border frame
        border = tk.Frame(dlg, bg=ACC, bd=0)
        border.place(x=0, y=0, width=W, height=3)

        # Icon + title
        tk.Label(dlg, text="✕", bg="#0D0D14", fg=ACC,
                 font=("Segoe UI", 22, "bold")).pack(pady=(22, 0))
        tk.Label(dlg, text="Tutup Synthex?", bg="#0D0D14", fg=FG,
                 font=("Segoe UI", 13, "bold")).pack(pady=(6, 0))
        tk.Label(dlg, text="Kamu akan otomatis ter-logout\ndan semua proses akan dihentikan.",
                 bg="#0D0D14", fg=MUT, font=("Segoe UI", 9),
                 justify="center").pack(pady=(6, 16))

        # Separator
        tk.Frame(dlg, bg=CARD, height=1).pack(fill="x", padx=24)

        # Buttons
        btn_row = tk.Frame(dlg, bg="#0D0D14")
        btn_row.pack(pady=16)

        def _do_quit():
            dlg.destroy()
            import os as _os
            token_path = _os.path.join(_os.environ.get("APPDATA", ""), "Synthex", "token.json")
            if _os.path.exists(token_path):
                try: _os.remove(token_path)
                except Exception: pass
            try:
                self.config.set("ui.stay_logged_in", False)
                self.config.set("ui.last_email", "")
                self.config.save()
            except Exception:
                pass
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
            if self._root:
                try: self._root.destroy()
                except Exception: pass
            _os._exit(0)

        tk.Button(btn_row, text="  Ya, Tutup  ", bg=RED,
                  fg="white", relief="flat", font=("Segoe UI", 10, "bold"),
                  cursor="hand2", padx=14, pady=7,
                  command=_do_quit).pack(side="left", padx=(0, 10))
        tk.Button(btn_row, text="  Batal  ", bg=CARD2, fg=FG,
                  relief="flat", font=("Segoe UI", 10),
                  cursor="hand2", padx=14, pady=7,
                  command=dlg.destroy).pack(side="left")

        dlg.grab_set()
        dlg.focus_force()
