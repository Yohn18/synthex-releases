# -*- coding: utf-8 -*-
"""
ui/onboarding.py - First-time onboarding wizard for Synthex.
Shown once after first login. Re-launchable from Settings -> Setup Guide.
"""

import json
import os
import threading
import tkinter as tk
from tkinter import ttk

BG   = "#0A0A0F"; CARD = "#12121A"; SIDE = "#0D0D16"
ACC  = "#6C63FF"; FG   = "#E0DFFF"; MUT  = "#555575"
GRN  = "#4CAF88"; RED  = "#F06070"; YEL  = "#F0C060"
PRP  = "#9D5CF6"

_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_FILE = os.path.join(_ROOT, "data", "user_data.json")

_FEATURE_CARDS = [
    ("[>]", ACC,  "Connect Chrome",   "Automate websites"),
    ("[#]", GRN,  "Connect Sheets",   "Save data automatically"),
    ("[*]", PRP,  "Build Macros",     "Automate repetitive tasks"),
    ("[~]", YEL,  "Schedule Tasks",   "Run automatically"),
]

_TEMPLATE_CARDS = [
    {
        "name":        "Update Price to Sheet",
        "description": "Get price from a website and save it to Google Sheet",
        "icon":        "[$]",
        "color":       GRN,
    },
    {
        "name":        "Confirm Order on Website",
        "description": "Read order from sheet, confirm on website, update status",
        "icon":        "[v]",
        "color":       ACC,
    },
    {
        "name":        "Monitor Stock Level",
        "description": "Check stock on website, alert if low or out of stock",
        "icon":        "[!]",
        "color":       YEL,
    },
    {
        "name":        "Copy Data from Web to Sheet",
        "description": "Open website, grab values, paste into Google Sheet",
        "icon":        "[=]",
        "color":       PRP,
    },
]


def _lbl(parent, text, fg=FG, bg=BG, font=("Segoe UI", 10), **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg, font=font, **kw)


def _btn(parent, text, command, bg=ACC, fg=BG, font=("Segoe UI", 10, "bold"),
         padx=18, pady=8):
    return tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, font=font,
        relief="flat", bd=0, padx=padx, pady=pady, cursor="hand2",
        activebackground=_lighten(bg), activeforeground=fg,
    )


def _lighten(hex_color):
    """Return a slightly lighter version of a hex color for hover states."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        r = min(255, r + 30)
        g = min(255, g + 30)
        b = min(255, b + 30)
        return "#{:02X}{:02X}{:02X}".format(r, g, b)
    except Exception:
        return hex_color


class OnboardingWizard:
    """
    Full-window overlay wizard shown after first login.
    Parameters
    ----------
    parent       : tk root/Toplevel that owns this wizard
    engine       : core Engine instance (for browser/sheets access)
    user_data    : UserData instance
    config       : Config instance
    on_complete  : callable() called when wizard finishes or is skipped
    open_template: callable(template_dict) called when user picks a template
                   (should navigate to macro builder with template pre-loaded)
    """

    STEPS = [
        "Welcome",
        "Connect Chrome",
        "Connect Sheet",
        "First Task",
        "All Set",
    ]

    def __init__(self, parent, engine, user_data, config,
                 on_complete=None, open_template=None):
        self._parent       = parent
        self._engine       = engine
        self._ud           = user_data
        self._config       = config
        self._on_complete  = on_complete
        self._open_tpl     = open_template
        self._step         = 0          # 0-indexed
        self._chrome_ok    = False
        self._chrome_info  = ""
        self._sheet_done   = False
        self._win          = None
        self._content_area = None
        self._dot_labels   = []
        self._step_title   = None

    # ------------------------------------------------------------------ public

    def show(self):
        """Build and display the wizard window."""
        win = self._win = tk.Toplevel(self._parent)
        win.title("Synthex Setup Wizard")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.grab_set()

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        w, h = 740, 560
        win.geometry("{}x{}+{}+{}".format(w, h, (sw - w) // 2, (sh - h) // 2))
        win.protocol("WM_DELETE_WINDOW", self._finish)

        self._build_shell()
        self._render_step()

    # ----------------------------------------------------------------- private

    def _build_shell(self):
        win = self._win

        # ── Header bar ──────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg=SIDE, padx=28, pady=16)
        hdr.pack(fill="x")

        _lbl(hdr, "SYNTHEX", fg=ACC, bg=SIDE,
             font=("Segoe UI", 15, "bold")).pack(side="left")
        _lbl(hdr, "  Setup Wizard", fg=MUT, bg=SIDE,
             font=("Segoe UI", 11)).pack(side="left")

        # Step indicator dots
        dot_row = tk.Frame(hdr, bg=SIDE)
        dot_row.pack(side="right")
        for i, name in enumerate(self.STEPS):
            col = tk.Frame(dot_row, bg=SIDE)
            col.pack(side="left", padx=6)
            dot = tk.Label(col, text="  ", bg=MUT, fg=BG, width=2,
                           font=("Segoe UI", 8, "bold"), relief="flat")
            dot.pack()
            lbl = _lbl(col, name, fg=MUT, bg=SIDE, font=("Segoe UI", 7))
            lbl.pack()
            self._dot_labels.append((dot, lbl))

        # ── Content area ────────────────────────────────────────────────────
        self._content_area = tk.Frame(win, bg=BG)
        self._content_area.pack(fill="both", expand=True, padx=0, pady=0)

    def _update_dots(self):
        for i, (dot, lbl) in enumerate(self._dot_labels):
            if i < self._step:
                dot.configure(bg=GRN, fg=BG, text="v")
                lbl.configure(fg=GRN)
            elif i == self._step:
                dot.configure(bg=ACC, fg=BG, text=str(i + 1))
                lbl.configure(fg=ACC)
            else:
                dot.configure(bg=MUT, fg=BG, text=" ")
                lbl.configure(fg=MUT)

    def _clear_content(self):
        for w in self._content_area.winfo_children():
            w.destroy()

    def _render_step(self):
        self._update_dots()
        self._clear_content()
        builders = [
            self._step_welcome,
            self._step_chrome,
            self._step_sheet,
            self._step_task,
            self._step_done,
        ]
        builders[self._step]()

    def _next(self):
        if self._step < len(self.STEPS) - 1:
            self._step += 1
            self._render_step()

    def _finish(self):
        """Mark onboarding complete and close."""
        self._mark_complete()
        if self._on_complete:
            self._on_complete()
        if self._win:
            self._win.destroy()
            self._win = None

    def _mark_complete(self):
        """Write onboarding_complete: true to user_data.json."""
        try:
            data = {}
            if os.path.exists(_DATA_FILE):
                with open(_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["onboarding_complete"] = True
            os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # ---------------------------------------------------------------- step 1 : Welcome

    def _step_welcome(self):
        ca = self._content_area

        # Centered content wrapper
        wrap = tk.Frame(ca, bg=BG)
        wrap.pack(expand=True, fill="both", padx=48, pady=20)

        _lbl(wrap, "Welcome to Synthex!", fg=FG,
             font=("Segoe UI", 22, "bold")).pack(pady=(10, 4))
        _lbl(wrap, "Let's set up your workspace in 4 quick steps.",
             fg=MUT, font=("Segoe UI", 11)).pack(pady=(0, 24))

        # 2x2 feature card grid
        grid = tk.Frame(wrap, bg=BG)
        grid.pack(fill="x", pady=(0, 24))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        for idx, (icon, color, title, desc) in enumerate(_FEATURE_CARDS):
            row_i = idx // 2
            col_i = idx % 2
            card = tk.Frame(grid, bg=CARD, padx=18, pady=14)
            card.grid(row=row_i, column=col_i, padx=6, pady=6, sticky="nsew")

            top_row = tk.Frame(card, bg=CARD)
            top_row.pack(anchor="w")
            _lbl(top_row, icon, fg=color, bg=CARD,
                 font=("Segoe UI", 18, "bold")).pack(side="left", padx=(0, 10))
            col_frame = tk.Frame(top_row, bg=CARD)
            col_frame.pack(side="left")
            _lbl(col_frame, title, fg=FG, bg=CARD,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
            _lbl(col_frame, desc, fg=MUT, bg=CARD,
                 font=("Segoe UI", 9)).pack(anchor="w")

        # Separator
        tk.Frame(wrap, bg=CARD, height=1).pack(fill="x", pady=(0, 18))

        # Get Started button
        _btn(wrap, "Get Started  ->", self._next,
             bg=ACC, fg=BG, font=("Segoe UI", 12, "bold"),
             padx=28, pady=10).pack()

    # ---------------------------------------------------------------- step 2 : Chrome

    def _step_chrome(self):
        ca = self._content_area
        wrap = tk.Frame(ca, bg=BG)
        wrap.pack(expand=True, fill="both", padx=60, pady=30)

        _lbl(wrap, "Step 1: Connect Your Browser", fg=ACC,
             font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 6))
        _lbl(wrap, "Synthex uses Chrome to automate websites.\n"
                   "Connecting Chrome lets Synthex open pages, click buttons,\n"
                   "and extract data on your behalf.",
             fg=MUT, font=("Segoe UI", 10), justify="left").pack(anchor="w",
                                                                   pady=(0, 22))

        # Status area
        status_frame = tk.Frame(wrap, bg=CARD, padx=18, pady=14)
        status_frame.pack(fill="x", pady=(0, 18))

        self._chrome_status_lbl = _lbl(
            status_frame, "Not connected", fg=MUT, bg=CARD,
            font=("Segoe UI", 11, "bold"))
        self._chrome_status_lbl.pack(anchor="w")

        self._chrome_info_lbl = _lbl(
            status_frame, "", fg=MUT, bg=CARD,
            font=("Segoe UI", 9))
        self._chrome_info_lbl.pack(anchor="w")

        # Pre-fill if browser was already connected during module load
        if (self._engine and self._engine.browser and
                getattr(self._engine.browser, "_ready", False)):
            self._chrome_ok = True
            profile = self._config.get("browser.profile_path", "")
            self._chrome_info = "Profile: {}".format(profile) if profile else ""
            self._chrome_status_lbl.configure(text="Chrome Connected!", fg=GRN)
            if self._chrome_info:
                self._chrome_info_lbl.configure(text=self._chrome_info, fg=GRN)

        # Buttons row
        btn_row = tk.Frame(wrap, bg=BG)
        btn_row.pack(anchor="w", pady=(0, 8))
        _btn(btn_row, "Connect Chrome", self._try_connect_chrome,
             bg=ACC, fg=BG).pack(side="left", padx=(0, 12))

        # Skip
        skip_lbl = tk.Label(wrap, text="Skip for now", fg=MUT, bg=BG,
                             font=("Segoe UI", 9, "underline"), cursor="hand2")
        skip_lbl.pack(anchor="w")
        skip_lbl.bind("<Button-1>", lambda e: self._next())

        # Next (only visible once connected)
        self._chrome_next_btn = _btn(wrap, "Next  ->", self._next,
                                      bg=GRN, fg=BG)
        if self._chrome_ok:
            self._chrome_next_btn.pack(anchor="w", pady=(14, 0))

    def _try_connect_chrome(self):
        self._chrome_status_lbl.configure(text="Connecting...", fg=YEL)
        self._chrome_info_lbl.configure(text="")

        def _run():
            ok = False
            info = ""
            try:
                if self._engine and self._engine.browser:
                    # Attempt to navigate to a blank page to verify connectivity
                    result = self._engine.browser.navigate("about:blank")
                    ok = True
                    profile = self._config.get("browser.profile_path", "")
                    info = "Profile: {}".format(profile) if profile else "Chrome ready"
                else:
                    info = "Browser module not initialized"
            except Exception as e:
                info = "Error: {}".format(str(e)[:80])

            self._chrome_ok = ok
            self._chrome_info = info
            self._win.after(0, lambda: self._update_chrome_ui(ok, info))

        threading.Thread(target=_run, daemon=True).start()

    def _update_chrome_ui(self, ok, info):
        if ok:
            self._chrome_status_lbl.configure(text="Chrome Connected!", fg=GRN)
            self._chrome_info_lbl.configure(text=info, fg=GRN)
            self._chrome_next_btn.pack(anchor="w", pady=(14, 0))
        else:
            self._chrome_status_lbl.configure(text="Not connected", fg=RED)
            self._chrome_info_lbl.configure(text=info, fg=RED)

    # ---------------------------------------------------------------- step 3 : Sheet

    def _step_sheet(self):
        ca = self._content_area
        wrap = tk.Frame(ca, bg=BG)
        wrap.pack(expand=True, fill="both", padx=60, pady=30)

        _lbl(wrap, "Step 2: Connect Your Google Sheet", fg=ACC,
             font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 6))
        _lbl(wrap, "Connect a Google Sheet so Synthex can read and write\n"
                   "data automatically during task execution.",
             fg=MUT, font=("Segoe UI", 10), justify="left").pack(anchor="w",
                                                                   pady=(0, 22))

        # Status area
        status_frame = tk.Frame(wrap, bg=CARD, padx=18, pady=14)
        status_frame.pack(fill="x", pady=(0, 18))

        self._sheet_status_lbl = _lbl(status_frame, "", fg=MUT, bg=CARD,
                                       font=("Segoe UI", 11, "bold"))
        self._sheet_status_lbl.pack(anchor="w")

        self._sheet_name_lbl = _lbl(status_frame, "", fg=MUT, bg=CARD,
                                     font=("Segoe UI", 9))
        self._sheet_name_lbl.pack(anchor="w")

        self._update_sheet_status()

        # Buttons
        btn_row = tk.Frame(wrap, bg=BG)
        btn_row.pack(anchor="w", pady=(0, 8))
        _btn(btn_row, "Connect Sheet", self._open_sheet_wizard,
             bg=ACC, fg=BG).pack(side="left", padx=(0, 12))

        skip_lbl = tk.Label(wrap, text="Skip for now", fg=MUT, bg=BG,
                             font=("Segoe UI", 9, "underline"), cursor="hand2")
        skip_lbl.pack(anchor="w")
        skip_lbl.bind("<Button-1>", lambda e: self._next())

        self._sheet_next_btn = _btn(wrap, "Next  ->", self._next, bg=GRN, fg=BG)
        if self._sheet_done:
            self._sheet_next_btn.pack(anchor="w", pady=(14, 0))

    def _update_sheet_status(self):
        sheets = self._ud.sheets if self._ud else []
        if sheets:
            self._sheet_done = True
            self._sheet_status_lbl.configure(
                text="Sheet Connected!", fg=GRN)
            self._sheet_name_lbl.configure(
                text=sheets[0].get("name", ""), fg=GRN)
        else:
            self._sheet_done = False
            self._sheet_status_lbl.configure(
                text="No sheet connected yet.", fg=MUT)
            self._sheet_name_lbl.configure(text="", fg=MUT)

    def _open_sheet_wizard(self):
        try:
            from modules.sheets.auth_wizard import SheetsAuthWizard

            def _on_done(entry):
                self._ud._d["sheets"].append(entry)
                self._ud.save()
                self._update_sheet_status()
                if hasattr(self, "_sheet_next_btn"):
                    self._sheet_next_btn.pack(anchor="w", pady=(14, 0))

            wizard = SheetsAuthWizard(self._win, on_done=_on_done)
            wizard.start_wizard()
        except Exception as e:
            self._sheet_status_lbl.configure(
                text="Error: {}".format(str(e)[:80]), fg=RED)

    # ---------------------------------------------------------------- step 4 : Task

    def _step_task(self):
        ca = self._content_area
        wrap = tk.Frame(ca, bg=BG)
        wrap.pack(expand=True, fill="both", padx=48, pady=20)

        _lbl(wrap, "Step 3: Create Your First Task", fg=ACC,
             font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 6))
        _lbl(wrap, "Choose a template to get started quickly.",
             fg=MUT, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 18))

        # 2x2 template card grid
        grid = tk.Frame(wrap, bg=BG)
        grid.pack(fill="x", pady=(0, 16))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        for idx, tpl in enumerate(_TEMPLATE_CARDS):
            row_i = idx // 2
            col_i = idx % 2
            color = tpl["color"]

            card = tk.Frame(grid, bg=CARD, padx=16, pady=12, cursor="hand2",
                            relief="flat", bd=2)
            card.grid(row=row_i, column=col_i, padx=5, pady=5, sticky="nsew")

            top_row = tk.Frame(card, bg=CARD)
            top_row.pack(anchor="w", pady=(0, 6))
            _lbl(top_row, tpl["icon"], fg=color, bg=CARD,
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=(0, 8))
            _lbl(top_row, tpl["name"], fg=FG, bg=CARD,
                 font=("Segoe UI", 9, "bold")).pack(side="left", anchor="w")

            _lbl(card, tpl["description"], fg=MUT, bg=CARD,
                 font=("Segoe UI", 8), wraplength=260,
                 justify="left").pack(anchor="w", pady=(0, 8))

            use_btn = tk.Button(
                card, text="Use Template", bg=color, fg=BG,
                font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                padx=10, pady=4, cursor="hand2",
                command=lambda t=tpl: self._pick_template(t))
            use_btn.pack(anchor="w")

            # Hover highlight
            def _on_enter(e, f=card):
                f.configure(bg=SIDE)
            def _on_leave(e, f=card):
                f.configure(bg=CARD)
            for widget in [card, top_row]:
                widget.bind("<Enter>", _on_enter)
                widget.bind("<Leave>", _on_leave)

        # Separator and skip
        tk.Frame(wrap, bg=CARD, height=1).pack(fill="x", pady=(8, 10))
        skip_row = tk.Frame(wrap, bg=BG)
        skip_row.pack(anchor="w")
        _lbl(skip_row, "Prefer to start from scratch? ", fg=MUT,
             font=("Segoe UI", 9)).pack(side="left")
        skip_lbl = tk.Label(skip_row, text="Skip for now", fg=ACC, bg=BG,
                             font=("Segoe UI", 9, "underline"), cursor="hand2")
        skip_lbl.pack(side="left")
        skip_lbl.bind("<Button-1>", lambda e: self._next())

    def _pick_template(self, template_card):
        """Load real template from templates.json matching by name, then open builder."""
        import json as _json
        tpl_path = os.path.join(_ROOT, "data", "templates.json")
        matched = None
        try:
            templates = _json.load(open(tpl_path, "r", encoding="utf-8"))
            for t in templates:
                if t.get("name") == template_card["name"]:
                    matched = t
                    break
        except Exception:
            pass

        self._mark_complete()
        if self._win:
            self._win.destroy()
            self._win = None
        if self._on_complete:
            self._on_complete()
        if self._open_tpl and matched:
            self._open_tpl(matched)

    # ---------------------------------------------------------------- step 5 : Done

    def _step_done(self):
        ca = self._content_area
        wrap = tk.Frame(ca, bg=BG)
        wrap.pack(expand=True, fill="both", padx=60, pady=30)

        _lbl(wrap, "You're all set!", fg=GRN,
             font=("Segoe UI", 22, "bold")).pack(pady=(10, 6))
        _lbl(wrap, "Synthex is ready to automate your workflow.",
             fg=MUT, font=("Segoe UI", 11)).pack(pady=(0, 28))

        # Summary card
        summ = tk.Frame(wrap, bg=CARD, padx=20, pady=16)
        summ.pack(fill="x", pady=(0, 28))

        _lbl(summ, "Setup Summary", fg=ACC, bg=CARD,
             font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 10))

        def _row(label, status, color):
            row = tk.Frame(summ, bg=CARD)
            row.pack(fill="x", pady=2)
            _lbl(row, label, fg=MUT, bg=CARD, font=("Segoe UI", 9),
                 width=20, anchor="w").pack(side="left")
            _lbl(row, status, fg=color, bg=CARD,
                 font=("Segoe UI", 9, "bold")).pack(side="left")

        chrome_status = "Connected" if self._chrome_ok else "Skipped"
        chrome_color  = GRN if self._chrome_ok else MUT

        sheets = self._ud.sheets if self._ud else []
        sheet_status = sheets[0].get("name", "Connected") if sheets else "Skipped"
        sheet_color  = GRN if sheets else MUT

        _row("Chrome Browser:", chrome_status, chrome_color)
        _row("Google Sheet:", sheet_status, sheet_color)
        _row("Templates:", "Ready to use", GRN)

        _lbl(wrap,
             "You can re-run this wizard anytime from\nSettings -> Setup Guide.",
             fg=MUT, font=("Segoe UI", 9), justify="left").pack(anchor="w",
                                                                  pady=(0, 18))

        _btn(wrap, "Open Synthex  ->", self._finish,
             bg=ACC, fg=BG, font=("Segoe UI", 12, "bold"),
             padx=28, pady=10).pack(anchor="w")


# ─────────────────────────────────────────────────────────────────────────────
# Convenience helpers
# ─────────────────────────────────────────────────────────────────────────────

def onboarding_needed():
    """Return True if the user has not completed onboarding yet."""
    try:
        data = json.load(open(_DATA_FILE, "r", encoding="utf-8"))
        return not data.get("onboarding_complete", False)
    except Exception:
        return True  # fresh install — show wizard
