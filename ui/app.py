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

BG   = "#0A0A0F"; CARD = "#12121A"; SIDE = "#0D0D16"
ACC  = "#6C63FF"; FG   = "#E0DFFF"; MUT  = "#555575"
GRN  = "#4CAF88"; RED  = "#F06070"; YEL  = "#F0C060"
PRP  = "#9D5CF6"

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
        ("Home",     "home"),
        ("Web",      "web"),
        ("Spy",      "spy"),
        ("Record",   "record"),
        ("Schedule", "schedule"),
        ("Sheet",    "sheet"),
        ("Rekening", "rekening"),
        ("History",  "history"),
        ("Settings", "settings"),
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
        self._rec_folder_var        = None
        self._last_selected_rec_idx = None    # tracks last selection for Ctrl+1

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
            icon_path = os.path.join(sys._MEIPASS, 'synthex.ico')
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'synthex.ico')
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
        r.geometry("1100x680")
        r.minsize(860, 560)
        r.resizable(True, True)
        r.configure(bg=BG)
        r.protocol("WM_DELETE_WINDOW", lambda: r.withdraw())
        _apply_styles(r)

        top = tk.Frame(r, bg=SIDE, height=48)
        top.pack(fill="x")
        top.pack_propagate(False)
        _lbl(top, "SYNTHEX", fg=ACC, bg=SIDE,
             font=("Segoe UI", 14, "bold")).pack(side="left", padx=16)
        _lbl(top, "by Yohn18", fg=MUT, bg=SIDE,
             font=("Segoe UI", 9)).pack(side="left")
        ttk.Button(top, text="Exit", style="Danger.TButton",
                   command=self._logout).pack(side="right", padx=12, pady=8)
        if self._email:
            _lbl(top, self._email, fg=GRN, bg=SIDE,
                 font=("Segoe UI", 9)).pack(side="right", padx=8)

        body = tk.Frame(r, bg=BG)
        body.pack(fill="both", expand=True)
        side = tk.Frame(body, bg=SIDE, width=170)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        _lbl(side, "NAVIGATION", fg=MUT, bg=SIDE,
             font=("Segoe UI", 7, "bold")).pack(
            anchor="w", padx=16, pady=(16, 6))
        for label, key in self.NAV:
            b = tk.Button(
                side, text=label, anchor="w", bg=SIDE, fg=MUT,
                activebackground=ACC, activeforeground=BG,
                font=("Segoe UI", 10), relief="flat", bd=0,
                padx=16, pady=8, cursor="hand2",
                command=lambda k=key: self._show(k))
            b.pack(fill="x")
            self._nav[key] = b

        self._content = tk.Frame(body, bg=BG)
        self._content.pack(side="left", fill="both", expand=True)

        bar = tk.Frame(r, bg=SIDE, height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._sv = tk.StringVar(value="Ready.")
        tk.Label(bar, textvariable=self._sv, fg=MUT, bg=SIDE,
                 font=("Segoe UI", 8)).pack(side="left", padx=12)
        _lbl(bar, "Ctrl+1=Play/Pause  Ctrl+3=Record/Stop",
             fg=MUT, bg=SIDE, font=("Segoe UI", 7)).pack(side="left", padx=16)
        self._cl = _lbl(bar, "", fg=MUT, bg=SIDE, font=("Segoe UI", 8))
        self._cl.pack(side="right", padx=12)
        self._tick()

        self._page_builders = {
            "home":     self._pg_home,
            "web":      self._pg_web,
            "spy":      self._pg_spy,
            "record":   self._pg_record,
            "schedule": self._pg_schedule,
            "sheet":    self._pg_sheet,
            "rekening": self._pg_rekening,
            "history":  self._pg_history,
            "settings": self._pg_settings,
        }

        self._show("home")
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry("1100x680+{}+{}".format((sw-1100)//2, (sh-680)//2))
        self._root.after(400, self._maybe_show_onboarding)

    def _show(self, key):
        if self._cur in self._pages:
            self._pages[self._cur].pack_forget()
        for k, b in self._nav.items():
            b.configure(bg=ACC if k == key else SIDE,
                        fg=BG if k == key else MUT)
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
                  "Record and replay actions.")

        # Two mode cards
        cards = tk.Frame(f, bg=BG)
        cards.pack(fill="x", padx=20, pady=(0, 12))

        # Simple Record card
        sc = tk.Frame(cards, bg=CARD, padx=16, pady=14)
        sc.pack(side="left", fill="both", expand=True, padx=(0, 8))
        _lbl(sc, "SIMPLE RECORD", bg=CARD, fg=ACC,
             font=("Segoe UI", 11, "bold")).pack(anchor="w")
        _lbl(sc,
             "Records clicks &\nkeystrokes by\nposition. Fast &\n"
             "easy like\nOP AutoClicker",
             bg=CARD, fg=MUT,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 10))
        tk.Button(sc, text="Start Simple Rec",
                  bg=ACC, fg=BG, font=("Segoe UI", 10, "bold"),
                  relief="flat", bd=0, padx=12, pady=8, cursor="hand2",
                  command=self._start_simple_rec).pack(fill="x")

        # Smart Record card
        ac = tk.Frame(cards, bg=CARD, padx=16, pady=14)
        ac.pack(side="left", fill="both", expand=True)
        _lbl(ac, "SMART RECORD", bg=CARD, fg=GRN,
             font=("Segoe UI", 11, "bold")).pack(anchor="w")
        _lbl(ac,
             "Records web element\nselectors. Works\neven if window moves\n"
             "or resizes.\nNeeds Chrome open.",
             bg=CARD, fg=MUT,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 10))
        tk.Button(ac, text="Start Smart Rec",
                  bg=GRN, fg=BG, font=("Segoe UI", 10, "bold"),
                  relief="flat", bd=0, padx=12, pady=8, cursor="hand2",
                  command=self._start_smart_rec).pack(fill="x")

        # Recordings list
        lc = _card(f, "Recordings")
        lc.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self._recordings_tree = _tree(lc, [
            ("name",     "Name",      140),
            ("type",     "Type",       58),
            ("steps",    "Steps",      50),
            ("last",     "Last Run",  130),
            ("duration", "Duration",   72),
        ])
        self._recordings_tree.tag_configure("simple_tag", foreground=ACC)
        self._recordings_tree.tag_configure("smart_tag",  foreground=GRN)
        self._recordings_tree.bind(
            "<Double-1>", lambda e: self._edit_selected_recording())
        self._recordings_tree.bind(
            "<<TreeviewSelect>>", lambda e: self._on_rec_tree_select())

        act_row = tk.Frame(lc, bg=CARD)
        act_row.pack(fill="x", pady=(6, 0))
        ttk.Button(act_row, text="Play",
                   command=self._play_selected_recording).pack(
            side="left", padx=(0, 4))
        ttk.Button(act_row, text="Edit Steps",
                   command=self._edit_selected_recording).pack(
            side="left", padx=(0, 4))
        ttk.Button(act_row, text="Delete", style="Danger.TButton",
                   command=self._delete_selected_recording).pack(side="left")

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
                url = self._mb_field_vars.get("url")
                if url and isinstance(url, tk.StringVar) and self.engine:
                    threading.Thread(
                        target=self.engine.open_url,
                        args=(url.get(),), daemon=True).start()
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
        import urllib.request, urllib.parse

        BANK_MAP = {
            "BCA":"014","BRI":"002","BNI":"009","MANDIRI":"008","BSI":"451","BTN":"200",
            "BLUEBCA":"501","DIGITALCA":"501","ROYAL":"501","JAGO":"542","SEABANK":"535",
            "ALLO":"567","ALLOBANK":"567","CIMB":"022","DANAMON":"011","PERMATA":"013",
            "PANIN":"019","OCBC":"028","MUAMALAT":"147","BTPN":"213","JENIUS":"213",
            "BTPNSY":"547","DBS":"046","HSBC":"087","CITIBANK":"031","UOB":"023","TMRW":"023",
            "MEGA":"426","MEGASY":"426","NOBU":"503","BUKOPIN":"441","WOKEE":"441",
            "SINARMAS":"153","BJB":"110","COMMONWEALTH":"950","VICTORIA":"566",
            "VICTORIAS":"405","LINEBANK":"484","NAGARI":"118","SUMBAR":"118","SUMUT":"117",
            "JATIM":"114","JATENG":"113","DIY":"112","KALSEL":"122","KALBAR":"123",
            "KALTIM":"124","KALTENG":"125","RIAUKEPRI":"119","SULSELBAR":"126",
            "SULUTGO":"127","SULTENG":"134","SULTRA":"135","BPDBALI":"129","NTT":"130",
            "NTBSY":"128","PAPUA":"132","MALUKU":"131","ACEHSY":"116","ANZ":"061",
            "AMAR":"531","ARTHA":"037","DKI":"111","MASPION":"157","MAYAPADA":"097",
            "MANTAP":"564","ICBC":"166","SHINHAN":"152","WOORI":"212","BENGKULU":"133",
            "LAMPUNG":"121","JAMBI":"115","GANESHA":"161","BRIAGO":"494","MIZUHO":"048",
            "MAYBANK":"016","IBK":"945","INA":"513","INDEX":"558","JAGOSY":"542",
            "JASAJKT":"472","MUTIARA":"095","QNB":"167","RESONA":"047","YUDHA":"490",
            "INDIAINDO":"146","CTBC":"949","CNB":"555","CAPITAL":"054","BNPPARIBAS":"057",
            "BUMIBARTA":"076","MESTIKA":"151","MNC":"485","SUMITOMO":"045","PRIMA":"520",
            "RABOBANK":"060","STANCHAR":"050","MITSUBISHI":"042","BPDbabel":"120",
            "ACEH":"116",
        }
        EWALLET_LIST = {"DANA", "GOPAY", "OVO", "SHOPEEPAY", "LINKAJA", "ISAKU", "GOPAYDRIVER"}
        API_URL = "https://apivalidasi.my.id/api/v3/validate"

        # ── outer page frame ──────────────────────────────────────────
        f = tk.Frame(self._content, bg=BG)
        self._hdr(f, "Cek Rekening", "Bulk bank account checker — format: PROVIDER NOMOR per baris")

        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # ── LEFT: input panel ─────────────────────────────────────────
        left = tk.Frame(body, bg=BG, width=320)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        inp_card = _card(left, "Input Rekening")
        inp_card.pack(fill="x")

        _lbl(inp_card, "Format: PROVIDER NOMOR per baris",
             fg=MUT, bg=CARD, font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))

        txt = tk.Text(inp_card, bg=CARD, fg=FG, insertbackground=FG,
                      font=("Consolas", 10), relief="flat", bd=0,
                      highlightthickness=1, highlightbackground=MUT,
                      highlightcolor=ACC, height=16, wrap="none",
                      selectbackground=ACC, selectforeground=BG)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", "BCA 1234567890\nBNI 0987654321\nMANDIRI 1122334455")

        # progress label
        prog_var = tk.StringVar(value="")
        prog_lbl = _lbl(inp_card, "", fg=MUT, bg=CARD, font=("Segoe UI", 8))
        prog_lbl.configure(textvariable=prog_var)
        prog_lbl.pack(anchor="w", pady=(6, 0))

        btn_row = tk.Frame(inp_card, bg=CARD)
        btn_row.pack(fill="x", pady=(8, 0))

        stop_flag = {"stop": False}

        def _do_stop():
            stop_flag["stop"] = True
            stop_btn.configure(state="disabled")

        def _do_clear():
            txt.delete("1.0", tk.END)
            for row in tree.get_children():
                tree.delete(row)
            prog_var.set("")
            stat_var.set("")

        def _do_check():
            raw = txt.get("1.0", tk.END).strip()
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            if not lines:
                return
            for row in tree.get_children():
                tree.delete(row)
            stop_flag["stop"] = False
            run_btn.configure(state="disabled")
            stop_btn.configure(state="normal")
            prog_var.set("Memproses 0 / {}...".format(len(lines)))
            stat_var.set("")

            def _worker():
                API_KEY = self.config.get("rekening_api_key", "").strip()
                if not API_KEY:
                    tree.after(0, lambda: tree.insert(
                        "", "end",
                        values=("-", "-", "-", "API Key belum diisi — isi di Settings"),
                        tags=("err",)))
                    tree.after(0, lambda: prog_var.set("Gagal: API Key belum diisi."))
                    tree.after(0, lambda: (
                        run_btn.configure(state="normal"),
                        stop_btn.configure(state="disabled")))
                    return

                ok = fail = err = 0
                for i, line in enumerate(lines):
                    if stop_flag["stop"]:
                        break
                    parts = line.split()
                    if len(parts) < 2:
                        tree.after(0, lambda ln=line: tree.insert(
                            "", "end", values=(ln, "-", "-", "Format salah"),
                            tags=("err",)))
                        err += 1
                        continue

                    provider = " ".join(parts[:-1]).upper()
                    nomor    = parts[-1]

                    if provider in EWALLET_LIST:
                        req_type = "ewallet"
                        req_code = provider.lower()
                    else:
                        req_type = "bank"
                        req_code = BANK_MAP.get(provider)

                    if not req_code:
                        tree.after(0, lambda p=provider, n=nomor: tree.insert(
                            "", "end", values=(p, n, "-", "Provider tidak dikenal"),
                            tags=("err",)))
                        err += 1
                        continue

                    # insert pending row
                    iid = tree.insert("", "end",
                                      values=(provider, nomor, "...", "Menunggu..."),
                                      tags=("pend",))

                    try:
                        import requests as _requests
                        response = _requests.get(
                            "https://apivalidasi.my.id/api/v3/validate",
                            params={
                                "type":          req_type,
                                "code":          req_code,
                                "accountNumber": nomor,
                                "api_key":       API_KEY,
                            },
                            headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                "Accept":     "application/json",
                                "Referer":    "https://apivalidasi.my.id/",
                            },
                            timeout=12,
                        )
                        data = response.json()

                        name = (data.get("account_name")
                                or data.get("data", {}).get("account_name")
                                or data.get("name") or "")
                        if name:
                            ok += 1
                            tree.after(0, lambda i=iid, p=provider, n=nomor, nm=name: (
                                tree.item(i, values=(p, n, nm, "VALID"), tags=("ok",))))
                        else:
                            msg = data.get("message") or data.get("msg") or "Tidak ditemukan"
                            fail += 1
                            tree.after(0, lambda i=iid, p=provider, n=nomor, m=msg: (
                                tree.item(i, values=(p, n, "-", m), tags=("fail",))))
                    except _requests.exceptions.HTTPError as e:
                        name = "HTTP {}: {}".format(e.response.status_code, str(e)[:80])
                        err += 1
                        tree.after(0, lambda i=iid, p=provider, n=nomor, m=name: (
                            tree.item(i, values=(p, n, "-", m), tags=("err",))))
                    except _requests.exceptions.ConnectionError as e:
                        name = "Connection Error: {}".format(str(e)[:80])
                        err += 1
                        tree.after(0, lambda i=iid, p=provider, n=nomor, m=name: (
                            tree.item(i, values=(p, n, "-", m), tags=("err",))))
                    except _requests.exceptions.Timeout:
                        name = "Timeout"
                        err += 1
                        tree.after(0, lambda i=iid, p=provider, n=nomor, m=name: (
                            tree.item(i, values=(p, n, "-", m), tags=("err",))))
                    except Exception as e:
                        name = "Error: {}".format(str(e))
                        err += 1
                        tree.after(0, lambda i=iid, p=provider, n=nomor, m=name: (
                            tree.item(i, values=(p, n, "-", m), tags=("err",))))

                    done = i + 1
                    tree.after(0, lambda d=done, t=len(lines): prog_var.set(
                        "Memproses {} / {}...".format(d, t)))

                def _done():
                    run_btn.configure(state="normal")
                    stop_btn.configure(state="disabled")
                    prog_var.set("Selesai: {} valid, {} gagal, {} error".format(ok, fail, err))
                    stat_var.set("{} valid  |  {} gagal  |  {} error".format(ok, fail, err))

                tree.after(0, _done)

            threading.Thread(target=_worker, daemon=True).start()

        run_btn = ttk.Button(btn_row, text="Cek Semua",
                             style="Accent.TButton", command=_do_check)
        run_btn.pack(side="left", padx=(0, 6))

        stop_btn = ttk.Button(btn_row, text="Stop", command=_do_stop,
                              state="disabled")
        stop_btn.pack(side="left", padx=(0, 6))

        ttk.Button(btn_row, text="Clear", command=_do_clear).pack(side="left")

        # ── RIGHT: results panel ──────────────────────────────────────
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        res_card = _card(right, "Hasil")
        res_card.pack(fill="both", expand=True)

        stat_var = tk.StringVar(value="")
        stat_lbl = _lbl(res_card, "", fg=ACC, bg=CARD,
                         font=("Segoe UI", 9, "bold"))
        stat_lbl.configure(textvariable=stat_var)
        stat_lbl.pack(anchor="w", pady=(0, 8))

        cols = [
            ("provider", "Provider",     90),
            ("nomor",    "Nomor",        130),
            ("nama",     "Nama Pemilik", 200),
            ("status",   "Status",       120),
        ]
        tree = _tree(res_card, cols)

        # colour tags
        tree.tag_configure("ok",   foreground=GRN)
        tree.tag_configure("fail", foreground=YEL)
        tree.tag_configure("err",  foreground=RED)
        tree.tag_configure("pend", foreground=MUT)

        # copy name on double-click
        def _copy_name(event):
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0], "values")
            if vals and vals[2] not in ("-", "...", ""):
                self._root.clipboard_clear()
                self._root.clipboard_append(vals[2])
                prog_var.set("Disalin: {}".format(vals[2]))

        tree.bind("<Double-1>", _copy_name)
        _lbl(res_card, "Double-klik baris untuk menyalin nama.",
             fg=MUT, bg=CARD, font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 0))

        return f

    # ================================================================
    #  HISTORY PAGE
    # ================================================================

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

        _lbl(rak, "API Key Validasi Rekening (apivalidasi.my.id)",
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
        name = simpledialog.askstring(
            "Save Element", "Name for this element:", parent=self._root)
        if not name:
            return
        self._ud.elements.append({
            "name":     name,
            "type":     type_map.get(tag, tag.upper()),
            "selector": info.get("css_selector", info.get("selector", "")),
            "xpath":    info.get("xpath", ""),
            "text":     info.get("text", ""),
            "id":       info.get("id", ""),
        })
        self._ud.save()
        self._refresh_spy_elements_tree()
        self._sv.set("Element '{}' saved.".format(name))

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
        """Begin simple recording with 3-second countdown."""
        self._do_countdown(3, self._do_start_simple_rec)

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

    def _do_start_simple_rec(self):
        """Actually start the SimpleRecorder and show mini toolbar."""
        import time as _time
        from modules.macro.simple_recorder import SimpleRecorder
        self._simple_recorder = SimpleRecorder()
        self._simple_recorder.start_recording()
        self._rec = True
        self._rec_start_time = _time.time()
        self._sv.set("Simple recording... perform actions, then click STOP.")
        self._show_rec_toolbar()

    def _show_rec_toolbar(self):
        """Floating mini toolbar: [● REC 00:05] [PAUSE] [STOP]."""
        import time as _time
        win = tk.Toplevel(self._root)
        win.title("")
        win.configure(bg=CARD)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.overrideredirect(True)
        sw = self._root.winfo_screenwidth()
        win.geometry("320x44+{}+10".format(sw // 2 - 160))
        self._rec_toolbar_win = win

        self._rec_timer_var = tk.StringVar(value="Recording... 0 steps")
        self._rec_paused    = False

        tk.Label(win, textvariable=self._rec_timer_var,
                 bg=RED, fg=BG, font=("Consolas", 10, "bold"),
                 padx=10).pack(side="left", fill="y")

        self._rec_pause_var = tk.StringVar(value="PAUSE")
        tk.Button(win, textvariable=self._rec_pause_var,
                  bg=YEL, fg=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=10,
                  command=self._toggle_rec_pause).pack(side="left", fill="y",
                                                       padx=2, pady=4)
        tk.Button(win, text="STOP",
                  bg=ACC, fg=BG, font=("Segoe UI", 9, "bold"),
                  relief="flat", bd=0, padx=10,
                  command=self._stop_simple_rec).pack(side="left", fill="y",
                                                      pady=4)

        def _tick():
            if not (win.winfo_exists() and self._rec):
                return
            if not self._rec_paused and self._simple_recorder:
                n = len(self._simple_recorder.get_actions())
                self._rec_timer_var.set("Recording... {} steps".format(n))
            self._rec_timer_id = win.after(1000, _tick)

        _tick()

    def _toggle_rec_pause(self):
        self._rec_paused = not self._rec_paused
        self._rec_pause_var.set("RESUME" if self._rec_paused else "PAUSE")

    def _stop_simple_rec(self):
        """Stop simple recording and open step editor."""
        self._rec = False
        if self._rec_toolbar_win:
            try:
                self._rec_toolbar_win.destroy()
            except Exception:
                pass
            self._rec_toolbar_win = None
        if self._rec_timer_id:
            try:
                self._root.after_cancel(self._rec_timer_id)
            except Exception:
                pass

        actions = []
        if self._simple_recorder:
            actions = self._simple_recorder.stop_recording()
        self._sv.set("Recording stopped. {} actions captured.".format(
            len(actions)))
        if actions:
            self._show_simple_step_editor(actions)
        else:
            from tkinter import messagebox as _mb
            _mb.showinfo("Simple Record", "No actions were recorded.",
                         parent=self._root)

    def _show_simple_step_editor(self, actions, edit_idx=None):
        """Show editable list of simple recorded actions with full step editing."""
        import uuid as _uuid

        # Existing recording metadata (if editing)
        existing = (self._ud.recordings[edit_idx]
                    if edit_idx is not None and 0 <= edit_idx < len(self._ud.recordings)
                    else None)

        dlg = tk.Toplevel(self._root)
        dlg.title("Simple Recording Editor")
        dlg.geometry("740x640")
        dlg.configure(bg=BG)
        dlg.resizable(True, True)
        dlg.grab_set()

        _lbl(dlg, "Simple Recording Editor",
             font=("Segoe UI", 13, "bold"), bg=BG).pack(
            anchor="w", padx=20, pady=(16, 2))

        # -- Recording metadata: Name, Description, Folder --
        meta = tk.Frame(dlg, bg=CARD, padx=12, pady=10)
        meta.pack(fill="x", padx=20, pady=(0, 8))

        r_name = tk.Frame(meta, bg=CARD)
        r_name.pack(fill="x", pady=2)
        _lbl(r_name, "Name:", fg=MUT, bg=CARD, width=9, anchor="w").pack(side="left")
        name_var = tk.StringVar(
            value=existing.get("name", "") if existing else "")
        tk.Entry(r_name, textvariable=name_var, bg=BG, fg=FG,
                 insertbackground=FG, font=("Segoe UI", 10),
                 relief="flat", bd=0, width=24).pack(
            side="left", padx=(0, 16), ipady=4)
        _lbl(r_name, "Description:", fg=MUT, bg=CARD, width=12,
             anchor="w").pack(side="left")
        desc_var = tk.StringVar(
            value=existing.get("description", "") if existing else "")
        tk.Entry(r_name, textvariable=desc_var, bg=BG, fg=FG,
                 insertbackground=FG, font=("Segoe UI", 10),
                 relief="flat", bd=0).pack(
            side="left", fill="x", expand=True, ipady=4)

        r_folder = tk.Frame(meta, bg=CARD)
        r_folder.pack(fill="x", pady=2)
        _lbl(r_folder, "Folder:", fg=MUT, bg=CARD, width=9,
             anchor="w").pack(side="left")
        folders = sorted({r.get("folder", "General")
                          for r in self._ud.recordings} | {"General", "Work", "Personal"})
        folder_var = tk.StringVar(
            value=existing.get("folder", "General") if existing else "General")
        ttk.Combobox(r_folder, textvariable=folder_var, values=folders,
                     width=20).pack(side="left")

        # -- Steps treeview --
        step_data = list(actions)

        lf = tk.Frame(dlg, bg=CARD, padx=8, pady=8)
        lf.pack(fill="both", expand=True, padx=20, pady=(0, 4))

        st = ttk.Treeview(lf, columns=("no", "type", "details", "delay"),
                          show="headings", selectmode="browse")
        st.heading("no",      text="#")
        st.heading("type",    text="Type")
        st.heading("details", text="Details")
        st.heading("delay",   text="Delay(s)")
        st.column("no",      width=36,  anchor="center")
        st.column("type",    width=78,  anchor="w")
        st.column("details", width=380, anchor="w")
        st.column("delay",   width=72,  anchor="center")
        vsb = ttk.Scrollbar(lf, orient="vertical", command=st.yview)
        st.configure(yscrollcommand=vsb.set)
        st.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        def _refresh_tree(keep_sel=None):
            for row in st.get_children():
                st.delete(row)
            from modules.macro.simple_recorder import SimpleRecorder as _SR
            for i, a in enumerate(step_data, 1):
                st.insert("", "end", values=(
                    i, a.get("type", ""),
                    _SR._action_desc(a),
                    "{:.2f}".format(a.get("delay", 0))))
            if keep_sel is not None and 0 <= keep_sel < len(step_data):
                ch = st.get_children()
                if keep_sel < len(ch):
                    st.selection_set(ch[keep_sel])
                    st.see(ch[keep_sel])

        _refresh_tree()

        # -- Dynamic step editor --
        edit_outer = tk.Frame(dlg, bg=BG)
        edit_outer.pack(fill="x", padx=20, pady=(0, 2))

        fields_frame = tk.Frame(edit_outer, bg=BG)
        fields_frame.pack(fill="x")

        # Shared step-field variables
        _sv_type   = tk.StringVar(value="click")
        _sv_delay  = tk.DoubleVar(value=0.5)
        _sv_x      = tk.IntVar(value=0)
        _sv_y      = tk.IntVar(value=0)
        _sv_button = tk.StringVar(value="left")
        _sv_text   = tk.StringVar(value="")
        _sv_amount = tk.IntVar(value=0)
        _sv_key    = tk.StringVar(value="")

        def _build_fields(atype):
            for w in fields_frame.winfo_children():
                w.destroy()
            row0 = tk.Frame(fields_frame, bg=BG)
            row0.pack(fill="x", pady=2)
            _lbl(row0, "Type:", fg=MUT, bg=BG, width=8, anchor="w").pack(side="left")
            cb = ttk.Combobox(row0, textvariable=_sv_type,
                              values=["click", "type", "scroll", "key"],
                              state="readonly", width=10)
            cb.pack(side="left", padx=(0, 16))
            cb.bind("<<ComboboxSelected>>",
                    lambda e: _build_fields(_sv_type.get()))
            _lbl(row0, "Delay(s):", fg=MUT, bg=BG,
                 width=9, anchor="w").pack(side="left")
            tk.Spinbox(row0, from_=0.0, to=30.0, increment=0.1, width=7,
                       textvariable=_sv_delay,
                       bg=CARD, fg=FG, insertbackground=FG,
                       relief="flat").pack(side="left")

            row1 = tk.Frame(fields_frame, bg=BG)
            row1.pack(fill="x", pady=2)
            if atype == "click":
                for lbl_txt, var, w in [("X:", _sv_x, 6), ("Y:", _sv_y, 6)]:
                    _lbl(row1, lbl_txt, fg=MUT, bg=BG,
                         width=3, anchor="w").pack(side="left")
                    tk.Spinbox(row1, from_=-9999, to=9999, width=w,
                               textvariable=var,
                               bg=CARD, fg=FG, insertbackground=FG,
                               relief="flat").pack(side="left", padx=(0, 8))
                _lbl(row1, "Button:", fg=MUT, bg=BG,
                     width=7, anchor="w").pack(side="left")
                ttk.Combobox(row1, textvariable=_sv_button,
                             values=["left", "right", "middle"],
                             state="readonly", width=8).pack(side="left")
            elif atype == "type":
                _lbl(row1, "Text:", fg=MUT, bg=BG,
                     width=6, anchor="w").pack(side="left")
                tk.Entry(row1, textvariable=_sv_text, bg=CARD, fg=FG,
                         insertbackground=FG, font=("Segoe UI", 10),
                         relief="flat", bd=0).pack(
                    side="left", fill="x", expand=True, ipady=4)
            elif atype == "scroll":
                for lbl_txt, var, w in [("X:", _sv_x, 6), ("Y:", _sv_y, 6)]:
                    _lbl(row1, lbl_txt, fg=MUT, bg=BG,
                         width=3, anchor="w").pack(side="left")
                    tk.Spinbox(row1, from_=-9999, to=9999, width=w,
                               textvariable=var,
                               bg=CARD, fg=FG, insertbackground=FG,
                               relief="flat").pack(side="left", padx=(0, 8))
                _lbl(row1, "Amount:", fg=MUT, bg=BG,
                     width=7, anchor="w").pack(side="left")
                tk.Spinbox(row1, from_=-100, to=100, width=5,
                           textvariable=_sv_amount,
                           bg=CARD, fg=FG, insertbackground=FG,
                           relief="flat").pack(side="left")
            elif atype == "key":
                _lbl(row1, "Key:", fg=MUT, bg=BG,
                     width=6, anchor="w").pack(side="left")
                tk.Entry(row1, textvariable=_sv_key, bg=CARD, fg=FG,
                         insertbackground=FG, font=("Segoe UI", 10),
                         relief="flat", bd=0, width=20).pack(
                    side="left", ipady=4)

        _build_fields("click")

        def _on_step_sel(event):
            s = st.selection()
            if not s:
                return
            i = st.index(s[0])
            if i >= len(step_data):
                return
            a = step_data[i]
            atype = a.get("type", "click")
            _sv_type.set(atype)
            _sv_delay.set(round(a.get("delay", 0), 3))
            if atype in ("click", "scroll"):
                _sv_x.set(a.get("x", 0))
                _sv_y.set(a.get("y", 0))
            if atype == "click":
                _sv_button.set(a.get("button", "left"))
            elif atype == "type":
                _sv_text.set(a.get("text", ""))
            elif atype == "scroll":
                _sv_amount.set(a.get("amount", 0))
            elif atype == "key":
                _sv_key.set(a.get("key", ""))
            _build_fields(atype)

        st.bind("<<TreeviewSelect>>", _on_step_sel)

        def _update_step():
            s = st.selection()
            if not s:
                return
            i = st.index(s[0])
            if i >= len(step_data):
                return
            atype = _sv_type.get()
            try:
                d = float(_sv_delay.get())
            except (ValueError, tk.TclError):
                d = 0.0
            act = {"type": atype, "delay": round(d, 3)}
            if atype == "click":
                try:
                    act["x"] = int(_sv_x.get())
                    act["y"] = int(_sv_y.get())
                except (ValueError, tk.TclError):
                    act["x"] = act["y"] = 0
                act["button"] = _sv_button.get()
            elif atype == "type":
                act["text"] = _sv_text.get()
            elif atype == "scroll":
                try:
                    act["x"] = int(_sv_x.get())
                    act["y"] = int(_sv_y.get())
                    act["amount"] = int(_sv_amount.get())
                except (ValueError, tk.TclError):
                    act["x"] = act["y"] = act["amount"] = 0
            elif atype == "key":
                act["key"] = _sv_key.get()
            step_data[i] = act
            _refresh_tree(keep_sel=i)

        def _delete_step():
            s = st.selection()
            if not s:
                return
            i = st.index(s[0])
            if i < len(step_data):
                del step_data[i]
                _refresh_tree(keep_sel=max(0, i - 1) if step_data else None)

        def _move_up():
            s = st.selection()
            if not s:
                return
            i = st.index(s[0])
            if i > 0:
                step_data[i - 1], step_data[i] = step_data[i], step_data[i - 1]
                _refresh_tree(keep_sel=i - 1)

        def _move_down():
            s = st.selection()
            if not s:
                return
            i = st.index(s[0])
            if i < len(step_data) - 1:
                step_data[i + 1], step_data[i] = step_data[i], step_data[i + 1]
                _refresh_tree(keep_sel=i + 1)

        btn_row = tk.Frame(edit_outer, bg=BG)
        btn_row.pack(fill="x", pady=(4, 0))
        for txt, cmd in [("Update Step", _update_step),
                         ("Delete Step",  _delete_step),
                         ("Move Up",      _move_up),
                         ("Move Down",    _move_down)]:
            ttk.Button(btn_row, text=txt, command=cmd).pack(
                side="left", padx=(0, 4))

        # -- Playback settings + Silent Mode --
        play_frame = tk.Frame(dlg, bg=BG)
        play_frame.pack(fill="x", padx=20, pady=(4, 2))
        _lbl(play_frame, "Speed:", fg=MUT, bg=BG,
             font=("Segoe UI", 9)).pack(side="left")
        speed_var = tk.DoubleVar(
            value=float(existing.get("speed", 1.0)) if existing else 1.0)
        ttk.Combobox(play_frame, textvariable=speed_var,
                     values=[0.5, 1.0, 1.5, 2.0],
                     state="readonly", width=5).pack(side="left", padx=(4, 16))
        _lbl(play_frame, "Repeat:", fg=MUT, bg=BG,
             font=("Segoe UI", 9)).pack(side="left")
        repeat_var = tk.IntVar(
            value=int(existing.get("repeat", 1)) if existing else 1)
        tk.Spinbox(play_frame, from_=1, to=9999, width=5,
                   textvariable=repeat_var,
                   bg=CARD, fg=FG, insertbackground=FG,
                   relief="flat").pack(side="left", padx=(4, 16))
        silent_var = tk.BooleanVar(
            value=bool(existing.get("silent_mode", False)) if existing else False)
        tk.Checkbutton(play_frame, text="Silent Mode",
                       variable=silent_var, bg=BG, fg=FG,
                       activebackground=BG, activeforeground=FG,
                       selectcolor=CARD,
                       font=("Segoe UI", 9)).pack(side="left")
        _lbl(play_frame,
             " (Chrome: clicks without moving cursor)",
             fg=MUT, bg=BG, font=("Segoe UI", 8)).pack(side="left")

        # -- Save / Test Run / Cancel --
        def _save():
            name = name_var.get().strip()
            if not name:
                name = simpledialog.askstring(
                    "Name Your Recording", "Recording name:", parent=dlg)
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
            self._sv.set(
                "Recording '{}' saved ({} steps).".format(name, len(step_data)))

        def _test_run():
            """Run the current steps immediately (without saving) to verify."""
            if not step_data:
                messagebox.showinfo("Test Run", "No steps to run.",
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

        sr = tk.Frame(dlg, bg=BG)
        sr.pack(fill="x", padx=20, pady=(4, 16))
        lbl_save = "Save Changes" if (
            edit_idx is not None and
            0 <= (edit_idx or -1) < len(self._ud.recordings)) else "Save Recording"
        tk.Button(sr, text=lbl_save, bg=ACC, fg=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=16, pady=8, cursor="hand2",
                  command=_save).pack(side="left")
        ttk.Button(sr, text="Test Run",
                   command=_test_run).pack(side="left", padx=(8, 0))
        ttk.Button(sr, text="Cancel",
                   command=dlg.destroy).pack(side="left", padx=(8, 0))

    # -- Smart Record ---------------------------------------------------

    def _start_smart_rec(self):
        """Start browser-based recording (existing logic)."""
        self._rec_mode = "smart"
        self._toggle_rec()

    # -- Smart Record toggle (existing, kept for smart mode) ------------

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

        dlg = tk.Toplevel(self._root)
        dlg.title("Recording Step Editor")
        dlg.geometry("660x520")
        dlg.configure(bg=BG)
        dlg.resizable(True, True)
        dlg.grab_set()

        _lbl(dlg, "Edit Recording Steps",
             font=("Segoe UI", 13, "bold"), bg=BG).pack(
            anchor="w", padx=20, pady=(16, 2))
        _lbl(dlg, "{} steps recorded".format(len(steps)),
             fg=MUT, bg=BG, font=("Segoe UI", 9)).pack(
            anchor="w", padx=20, pady=(0, 8))

        lf = tk.Frame(dlg, bg=CARD, padx=8, pady=8)
        lf.pack(fill="both", expand=True, padx=20, pady=(0, 6))
        st = ttk.Treeview(lf, columns=("no","type","value"),
                          show="headings", selectmode="browse")
        st.heading("no",    text="#")
        st.heading("type",  text="Action Type")
        st.heading("value", text="Value / Selector")
        st.column("no",    width=36, anchor="center")
        st.column("type",  width=110)
        st.column("value", width=400)
        st.pack(fill="both", expand=True)

        step_data = list(steps)

        def refresh():
            for row in st.get_children():
                st.delete(row)
            for i, s in enumerate(step_data, 1):
                st.insert("", "end", values=(i, s["type"], s.get("value","")))

        refresh()

        form     = tk.Frame(dlg, bg=BG)
        form.pack(fill="x", padx=20, pady=(0, 4))
        type_var = tk.StringVar(value=STEP_TYPES[0])
        val_var  = tk.StringVar()

        r1 = tk.Frame(form, bg=BG)
        r1.pack(fill="x", pady=2)
        _lbl(r1, "Type:", fg=MUT, bg=BG, width=8, anchor="w").pack(side="left")
        ttk.Combobox(r1, textvariable=type_var, values=STEP_TYPES,
                     state="readonly", width=16).pack(side="left", padx=(0,8))
        r2 = tk.Frame(form, bg=BG)
        r2.pack(fill="x", pady=2)
        _lbl(r2, "Value:", fg=MUT, bg=BG, width=8, anchor="w").pack(side="left")
        ttk.Entry(r2, textvariable=val_var,
                  font=("Segoe UI", 10)).pack(
            side="left", fill="x", expand=True)

        def on_sel(event):
            s = st.selection()
            if s:
                i = st.index(s[0])
                if i < len(step_data):
                    type_var.set(step_data[i]["type"])
                    val_var.set(step_data[i].get("value",""))
        st.bind("<<TreeviewSelect>>", on_sel)

        def upd():
            s = st.selection()
            if not s:
                return
            i = st.index(s[0])
            if i < len(step_data):
                step_data[i] = {"type": type_var.get(), "value": val_var.get()}
                refresh()

        def add():
            step_data.append({"type": type_var.get(), "value": val_var.get()})
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
                step_data[i-1], step_data[i] = step_data[i], step_data[i-1]
                refresh()

        def move_down():
            s = st.selection()
            if not s:
                return
            i = st.index(s[0])
            if i < len(step_data) - 1:
                step_data[i+1], step_data[i] = step_data[i], step_data[i+1]
                refresh()

        btn_row = tk.Frame(form, bg=BG)
        btn_row.pack(fill="x", pady=(6, 0))
        for txt, cmd in [("Update", upd), ("+ Add", add),
                         ("Delete", delete), ("Up", move_up),
                         ("Down",   move_down)]:
            ttk.Button(btn_row, text=txt, command=cmd).pack(
                side="left", padx=(0, 4))

        def save_rec():
            name = simpledialog.askstring(
                "Name Your Recording", "Recording name:", parent=dlg)
            if not name:
                return
            folder = (self._rec_folder_var.get()
                      if self._rec_folder_var else "General")
            if edit_idx is not None and 0 <= edit_idx < len(
                    self._ud.recordings):
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
            dlg.destroy()
            self._sv.set(
                "Recording '{}' saved ({} steps).".format(name, len(step_data)))

        sr = tk.Frame(dlg, bg=BG)
        sr.pack(fill="x", padx=20, pady=(0, 16))
        tk.Button(sr, text="Save Recording", bg=ACC, fg=BG,
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=16, pady=8, cursor="hand2",
                  command=save_rec).pack(side="left")
        ttk.Button(sr, text="Cancel",
                   command=dlg.destroy).pack(side="left", padx=(8, 0))

    def _play_selected_recording(self):
        if not self._recordings_tree:
            return
        sel = self._recordings_tree.selection()
        if not sel:
            messagebox.showinfo("Play", "Select a recording from the list.",
                                parent=self._root)
            return
        idx = self._recordings_tree.index(sel[0])
        if idx >= len(self._ud.recordings):
            return
        rec   = self._ud.recordings[idx]
        steps = rec.get("steps", [])
        if not steps:
            messagebox.showinfo("Play", "This recording has no steps.",
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
        win.geometry("220x160")
        win.configure(bg=CARD)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        sw = self._root.winfo_screenwidth()
        win.geometry("220x160+{}+40".format(sw - 240))
        win.protocol("WM_DELETE_WINDOW", lambda: None)

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

        pb = tk.Canvas(win, width=196, height=6, bg=BG, highlightthickness=0)
        pb.pack(padx=12, pady=(0, 8))

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
            win._pb_canvas.delete("pb")
            win._pb_canvas.create_rectangle(
                0, 0, int(196 * pct), 6,
                fill=ACC, outline="", tags="pb")
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
                rtype.capitalize(),
                rec.get("step_count", len(rec.get("steps", []))),
                rec.get("last_run", "-"),
                rec.get("duration", "-"),
            ))

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
        name = self._ud.recordings[idx].get("name","")
        if messagebox.askyesno("Delete",
                               "Delete recording '{}'?".format(name),
                               parent=self._root):
            del self._ud.recordings[idx]
            self._ud.save()
            self._refresh_recordings_tree()

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
        """Register global hotkeys Ctrl+1 (play/pause) and Ctrl+3 (record toggle)."""
        try:
            from pynput import keyboard as _kb
            self._hkl = _kb.GlobalHotKeys({
                "<ctrl>+1": lambda: (
                    self._root.after(0, self._hk_play_pause)
                    if self._root else None),
                "<ctrl>+3": lambda: (
                    self._root.after(0, self._hk_record_toggle)
                    if self._root else None),
            })
            self._hkl.daemon = True
            self._hkl.start()
        except Exception:
            pass

    # -- Hotkey actions --

    def _hk_play_pause(self):
        """Ctrl+1: Play / Pause toggle."""
        if self._playback_running and self._playback_pause.is_set():
            # Currently paused -> resume
            self._playback_pause.clear()
            self._show_toast("Resumed", kind="info")
        elif self._playback_running:
            # Currently playing -> pause
            self._playback_pause.set()
            self._show_toast("Paused", kind="info")
        else:
            # Not playing -> start playback of last selected recording
            idx = self._last_selected_rec_idx
            if idx is None or idx >= len(self._ud.recordings):
                self._show_toast("No recording selected", kind="warning")
                return
            rec = self._ud.recordings[idx]
            self._show_toast(
                "Playing: {}".format(rec.get("name", "")), kind="success")
            if rec.get("rec_type", "smart") == "simple":
                self._play_simple_recording(rec, idx)
            else:
                self._hk_play_smart(rec, idx)

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
        """Ctrl+3: Start or stop simple recording."""
        if self._rec:
            actions_count = 0
            if self._simple_recorder:
                actions_count = len(self._simple_recorder.get_actions())
            self._stop_simple_rec()
            self._show_toast(
                "Recording stopped - {} steps recorded".format(actions_count),
                kind="info")
        else:
            self._show_toast("Recording started...", kind="info")
            self._start_simple_rec()

    def _quit(self):
        if self._tray:
            self._tray.stop()
        if self._hkl:
            self._hkl.stop()
        if self._root:
            self._root.destroy()
