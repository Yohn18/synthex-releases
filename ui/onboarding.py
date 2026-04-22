# -*- coding: utf-8 -*-
"""ui/onboarding.py - Animated onboarding wizard for Synthex."""

import json
import math
import os
import threading
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageTk
    _PIL = True
except ImportError:
    _PIL = False

BG   = "#080810"; CARD = "#0F0F1E"; SIDE = "#0C0C18"
ACC  = "#6C4AFF"; FG   = "#C8C8E8"; MUT  = "#505070"
GRN  = "#00D4AA"; RED  = "#FF5555"; YEL  = "#F0C060"
PRP  = "#9D5CF6"; ACL  = "#4A9EFF"
BORDER = "#1E1E38"

_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_FILE = os.path.join(_ROOT, "data", "user_data.json")

_FEATURE_CARDS = [
    ("⚡", ACC,  "Automate Chrome",   "Klik & isi form otomatis"),
    ("📊", GRN,  "Google Sheets",     "Baca & tulis data otomatis"),
    ("⌨️", PRP,  "Macro Recorder",    "Rekam & putar ulang aksi"),
    ("🕐", YEL,  "Task Scheduler",    "Jadwalkan tugas otomatis"),
]

_TEMPLATE_CARDS = [
    {"name": "Update Price to Sheet",   "description": "Ambil harga dari website, simpan ke Google Sheet",
     "icon": "💰", "color": GRN},
    {"name": "Confirm Order on Website","description": "Baca order dari sheet, konfirmasi di website",
     "icon": "✅", "color": ACC},
    {"name": "Monitor Stock Level",     "description": "Pantau stok website, alert jika hampir habis",
     "icon": "📦", "color": YEL},
    {"name": "Copy Data from Web to Sheet","description": "Buka web, ambil data, tempel ke Google Sheet",
     "icon": "📋", "color": PRP},
]


def _lbl(parent, text, fg=FG, bg=BG, font=("Segoe UI", 10), **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg, font=font, **kw)


def _lighten(hex_color, amount=30):
    try:
        r = min(255, int(hex_color[1:3], 16) + amount)
        g = min(255, int(hex_color[3:5], 16) + amount)
        b = min(255, int(hex_color[5:7], 16) + amount)
        return "#{:02X}{:02X}{:02X}".format(r, g, b)
    except Exception:
        return hex_color


def _btn(parent, text, command, bg=ACC, fg=BG,
         font=("Segoe UI", 10, "bold"), padx=18, pady=8):
    b = tk.Button(parent, text=text, command=command,
                  bg=bg, fg=fg, font=font, relief="flat", bd=0,
                  padx=padx, pady=pady, cursor="hand2",
                  activebackground=_lighten(bg), activeforeground=fg)
    b.bind("<Enter>", lambda e: b.configure(bg=_lighten(bg, 20)))
    b.bind("<Leave>", lambda e: b.configure(bg=bg))
    return b


# ── Gradient header ────────────────────────────────────────────────────────────
def _make_header_gradient(W, H=64):
    if not _PIL:
        return None
    img = Image.new("RGB", (W, H), (12, 12, 24))
    draw = ImageDraw.Draw(img)
    # subtle horizontal gradient
    for x in range(W):
        t = x / W
        r = int(12 + 8 * t)
        g = int(12 + 4 * t)
        b = int(24 + 10 * t)
        draw.line([(x, 0), (x, H)], fill=(r, g, b))
    # bottom glow line
    draw.line([(0, H - 1), (W, H - 1)], fill=(108, 74, 255, 80))
    return img


class OnboardingWizard:
    STEPS = ["Welcome", "Connect Chrome", "Connect Sheet", "First Task", "All Set"]

    def __init__(self, parent, engine, user_data, config,
                 on_complete=None, open_template=None):
        self._parent      = parent
        self._engine      = engine
        self._ud          = user_data
        self._config      = config
        self._on_complete = on_complete
        self._open_tpl    = open_template
        self._step        = 0
        self._chrome_ok   = False
        self._chrome_info = ""
        self._sheet_done  = False
        self._win         = None
        self._content_area = None
        self._dot_labels   = []
        self._animating    = True
        self._pulse_step   = 0
        self._hdr_photo    = None

    # ──────────────────────────────────────────────── public

    def show(self):
        win = self._win = tk.Toplevel(self._parent)
        win.title("Synthex Setup Wizard")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.grab_set()
        win.attributes("-alpha", 0.0)

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        w, h = 760, 560
        win.geometry("{}x{}+{}+{}".format(w, h, (sw - w) // 2, (sh - h) // 2))
        win.protocol("WM_DELETE_WINDOW", self._finish)

        self._W = w
        self._H = h
        self._build_shell()
        self._render_step()

        # Fade in
        self._fade_in_win(0)

    # ──────────────────────────────────────────────── shell

    def _build_shell(self):
        win = self._win

        # ── Header ────────────────────────────────────────────────────────────
        hdr_h = 64
        hdr_canvas = tk.Canvas(win, width=self._W, height=hdr_h,
                                bg=SIDE, highlightthickness=0)
        hdr_canvas.pack(fill="x")

        # PIL gradient header
        if _PIL:
            def _apply_hdr():
                try:
                    hdr_img = _make_header_gradient(self._W, hdr_h)
                    self._hdr_photo = ImageTk.PhotoImage(hdr_img)
                    hdr_canvas.create_image(0, 0, anchor="nw",
                                            image=self._hdr_photo)
                    hdr_canvas.tag_lower("all")
                except Exception:
                    pass
            threading.Thread(target=lambda: win.after(50, _apply_hdr),
                             daemon=True).start()

        # Accent left stripe
        hdr_canvas.create_rectangle(0, 0, 4, hdr_h, fill=ACC, outline="")

        # Logo + title
        hdr_canvas.create_text(26, 22, text="⚡ SYNTHEX",
                                font=("Segoe UI", 14, "bold"),
                                fill=ACC, anchor="w")
        hdr_canvas.create_text(26, 45, text="Setup Wizard",
                                font=("Segoe UI", 9),
                                fill=MUT, anchor="w")

        # Step dots (right side)
        dot_x_start = self._W - (len(self.STEPS) * 70) - 20
        self._dot_labels = []
        for i, name in enumerate(self.STEPS):
            cx = dot_x_start + i * 70 + 24
            cy_dot = 28
            dot_oval = hdr_canvas.create_oval(cx - 10, cy_dot - 10,
                                               cx + 10, cy_dot + 10,
                                               fill=MUT, outline="")
            dot_text = hdr_canvas.create_text(cx, cy_dot,
                                               text=str(i + 1),
                                               font=("Segoe UI", 8, "bold"),
                                               fill=BG)
            dot_lbl  = hdr_canvas.create_text(cx, cy_dot + 20,
                                               text=name,
                                               font=("Segoe UI", 7),
                                               fill=MUT)
            self._dot_labels.append((hdr_canvas, dot_oval, dot_text, dot_lbl))

        self._hdr_canvas = hdr_canvas
        self._pulse_dots()

        # ── Content area ──────────────────────────────────────────────────────
        self._content_area = tk.Frame(win, bg=BG)
        self._content_area.pack(fill="both", expand=True)

    def _update_dots(self):
        for i, (canvas, oval, dtxt, dlbl) in enumerate(self._dot_labels):
            if i < self._step:
                canvas.itemconfigure(oval, fill=GRN)
                canvas.itemconfigure(dtxt, text="✓")
                canvas.itemconfigure(dlbl, fill=GRN)
            elif i == self._step:
                canvas.itemconfigure(oval, fill=ACC)
                canvas.itemconfigure(dtxt, text=str(i + 1))
                canvas.itemconfigure(dlbl, fill=ACC)
            else:
                canvas.itemconfigure(oval, fill=MUT)
                canvas.itemconfigure(dtxt, text=str(i + 1))
                canvas.itemconfigure(dlbl, fill=MUT)

    def _pulse_dots(self):
        if not self._animating:
            return
        try:
            self._pulse_step += 1
            t = self._pulse_step * 0.08
            scale = 0.85 + 0.15 * (math.sin(t) + 1) * 0.5
            # pulse the active dot oval
            if self._dot_labels:
                canvas, oval, _, _ = self._dot_labels[self._step]
                # scale via coordinate adjustment
                coords = canvas.coords(oval)
                if len(coords) == 4:
                    cx = (coords[0] + coords[2]) / 2
                    cy = (coords[1] + coords[3]) / 2
                    base_r = 10
                    r = base_r * scale
                    canvas.coords(oval, cx - r, cy - r, cx + r, cy + r)
            self._win.after(60, self._pulse_dots)
        except Exception:
            pass

    # ── Content rendering ─────────────────────────────────────────────────────
    def _clear_content(self):
        for w in self._content_area.winfo_children():
            w.destroy()

    def _render_step(self, direction=1):
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
        self._slide_in(direction)

    def _slide_in(self, direction=1, step=0):
        if not self._animating:
            return
        try:
            children = self._content_area.winfo_children()
            if not children:
                return
            total_steps = 12
            start_x = direction * 60
            x = start_x * (1 - step / total_steps)
            alpha_factor = step / total_steps
            for child in children:
                child.place_configure(x=int(x)) if child.winfo_manager() == "place" else None
            if step < total_steps:
                self._win.after(20, self._slide_in, direction, step + 1)
        except Exception:
            pass

    def _next(self, direction=1):
        if self._step < len(self.STEPS) - 1:
            self._step += 1
            self._render_step(direction=1)

    def _back(self):
        if self._step > 0:
            self._step -= 1
            self._render_step(direction=-1)

    def _finish(self):
        self._animating = False
        self._mark_complete()
        if self._on_complete:
            self._on_complete()
        if self._win:
            self._win.destroy()
            self._win = None

    def _mark_complete(self):
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

    # ── Fade animations ────────────────────────────────────────────────────────
    def _fade_in_win(self, step):
        target, total = 0.97, 18
        alpha = min(target, step / total * target)
        try:
            self._win.attributes("-alpha", alpha)
        except Exception:
            pass
        if step < total:
            self._win.after(18, self._fade_in_win, step + 1)

    # ── Step helpers ─────────────────────────────────────────────────────────
    def _card_frame(self, parent, accent=None):
        """Bordered card with accent left stripe."""
        outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        inner = tk.Frame(outer, bg=CARD, padx=16, pady=12)
        inner.pack(fill="both", expand=True)
        if accent:
            tk.Frame(inner, bg=accent, width=3).pack(side="left", fill="y", padx=(0, 10))
        return outer, inner

    def _section_title(self, parent, text, sub=None, accent=ACC):
        tk.Label(parent, text=text, bg=BG, fg=accent,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 4))
        if sub:
            tk.Label(parent, text=sub, bg=BG, fg=MUT,
                     font=("Segoe UI", 10), justify="left").pack(anchor="w", pady=(0, 18))

    # ── Step 1: Welcome ────────────────────────────────────────────────────────
    def _step_welcome(self):
        ca = self._content_area
        wrap = tk.Frame(ca, bg=BG)
        wrap.pack(expand=True, fill="both", padx=50, pady=24)

        # Hero area
        hero = tk.Frame(wrap, bg=BG)
        hero.pack(fill="x", pady=(0, 20))

        tk.Label(hero, text="⚡", bg=BG, fg=ACC,
                 font=("Segoe UI", 36)).pack(side="left", padx=(0, 16))
        txt_col = tk.Frame(hero, bg=BG)
        txt_col.pack(side="left", anchor="w")
        tk.Label(txt_col, text="Welcome to Synthex!",
                 bg=BG, fg=FG, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(txt_col, text="Mari setup workspace kamu dalam 4 langkah cepat.",
                 bg=BG, fg=MUT, font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 0))

        # Separator
        tk.Frame(wrap, bg=BORDER, height=1).pack(fill="x", pady=(0, 18))

        # Feature cards — 2x2 grid
        grid = tk.Frame(wrap, bg=BG)
        grid.pack(fill="x", pady=(0, 22))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        for idx, (icon, color, title, desc) in enumerate(_FEATURE_CARDS):
            row_i = idx // 2
            col_i = idx % 2
            card = tk.Frame(grid, bg=CARD, cursor="hand2")
            card.grid(row=row_i, column=col_i, padx=5, pady=5, sticky="nsew")

            # Left color stripe
            tk.Frame(card, bg=color, width=3).pack(side="left", fill="y")
            body = tk.Frame(card, bg=CARD, padx=14, pady=12)
            body.pack(side="left", fill="both", expand=True)

            top_row = tk.Frame(body, bg=CARD)
            top_row.pack(anchor="w")
            tk.Label(top_row, text=icon, bg=CARD, fg=color,
                     font=("Segoe UI", 16)).pack(side="left", padx=(0, 8))
            col_f = tk.Frame(top_row, bg=CARD)
            col_f.pack(side="left")
            tk.Label(col_f, text=title, bg=CARD, fg=FG,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(col_f, text=desc, bg=CARD, fg=MUT,
                     font=("Segoe UI", 8)).pack(anchor="w")

            def _hover_on(e, f=card, c=color):
                f.configure(bg=SIDE)
                for ch in f.winfo_children():
                    _set_bg_deep(ch, SIDE)
            def _hover_off(e, f=card):
                f.configure(bg=CARD)
                for ch in f.winfo_children():
                    _set_bg_deep(ch, CARD)
            card.bind("<Enter>", _hover_on)
            card.bind("<Leave>", _hover_off)

        # CTA
        _btn(wrap, "Mulai Sekarang  →", self._next,
             bg=ACC, fg=BG, font=("Segoe UI", 12, "bold"),
             padx=28, pady=11).pack(anchor="w")

    # ── Step 2: Chrome ─────────────────────────────────────────────────────────
    def _step_chrome(self):
        ca = self._content_area
        wrap = tk.Frame(ca, bg=BG)
        wrap.pack(expand=True, fill="both", padx=60, pady=32)

        self._section_title(wrap, "Step 1: Hubungkan Chrome",
                            "Synthex menggunakan Chrome untuk otomatisasi website.\n"
                            "Hubungkan agar Synthex bisa membuka halaman, klik, dan mengambil data.")

        status_outer, status_inner = self._card_frame(wrap, accent=ACL)
        status_outer.pack(fill="x", pady=(0, 18))

        # Pre-fill if already connected
        already_ok = (self._engine and self._engine.browser and
                      getattr(self._engine.browser, "_ready", False))
        if already_ok:
            self._chrome_ok = True

        status_text = "✅  Chrome Terhubung!" if self._chrome_ok else "⚪  Belum terhubung"
        status_fg   = GRN if self._chrome_ok else MUT

        self._chrome_status_lbl = tk.Label(
            status_inner, text=status_text, bg=CARD, fg=status_fg,
            font=("Segoe UI", 11, "bold"))
        self._chrome_status_lbl.pack(anchor="w")
        self._chrome_info_lbl = tk.Label(status_inner, text="", bg=CARD, fg=MUT,
                                          font=("Segoe UI", 9))
        self._chrome_info_lbl.pack(anchor="w")

        btn_row = tk.Frame(wrap, bg=BG)
        btn_row.pack(anchor="w", pady=(0, 8))
        _btn(btn_row, "🔗  Connect Chrome", self._try_connect_chrome,
             bg=ACL, fg=BG).pack(side="left", padx=(0, 12))

        skip_lbl = tk.Label(wrap, text="Lewati untuk sekarang", fg=MUT, bg=BG,
                             font=("Segoe UI", 9, "underline"), cursor="hand2")
        skip_lbl.pack(anchor="w")
        skip_lbl.bind("<Button-1>", lambda e: self._next())

        self._chrome_next_btn = _btn(wrap, "Lanjut  →", self._next, bg=GRN, fg=BG)
        if self._chrome_ok:
            self._chrome_next_btn.pack(anchor="w", pady=(14, 0))

    def _try_connect_chrome(self):
        self._chrome_status_lbl.configure(text="⏳  Menghubungkan...", fg=YEL)
        self._chrome_info_lbl.configure(text="")

        def _run():
            ok, info = False, ""
            try:
                if self._engine and self._engine.browser:
                    self._engine.browser.navigate("about:blank")
                    ok = True
                    profile = self._config.get("browser.profile_path", "")
                    info = "Profile: {}".format(profile) if profile else "Chrome siap"
                else:
                    info = "Browser module belum diinisialisasi"
            except Exception as e:
                info = "Error: {}".format(str(e)[:80])
            self._chrome_ok   = ok
            self._chrome_info = info
            self._win.after(0, lambda: self._update_chrome_ui(ok, info))

        threading.Thread(target=_run, daemon=True).start()

    def _update_chrome_ui(self, ok, info):
        if ok:
            self._chrome_status_lbl.configure(text="✅  Chrome Terhubung!", fg=GRN)
            self._chrome_info_lbl.configure(text=info, fg=GRN)
            self._chrome_next_btn.pack(anchor="w", pady=(14, 0))
        else:
            self._chrome_status_lbl.configure(text="❌  Gagal terhubung", fg=RED)
            self._chrome_info_lbl.configure(text=info, fg=RED)

    # ── Step 3: Sheet ──────────────────────────────────────────────────────────
    def _step_sheet(self):
        ca = self._content_area
        wrap = tk.Frame(ca, bg=BG)
        wrap.pack(expand=True, fill="both", padx=60, pady=32)

        self._section_title(wrap, "Step 2: Hubungkan Google Sheet",
                            "Hubungkan Google Sheet agar Synthex dapat membaca\n"
                            "dan menulis data secara otomatis.")

        status_outer, status_inner = self._card_frame(wrap, accent=GRN)
        status_outer.pack(fill="x", pady=(0, 18))

        self._sheet_status_lbl = tk.Label(status_inner, text="", bg=CARD, fg=MUT,
                                           font=("Segoe UI", 11, "bold"))
        self._sheet_status_lbl.pack(anchor="w")
        self._sheet_name_lbl = tk.Label(status_inner, text="", bg=CARD, fg=MUT,
                                         font=("Segoe UI", 9))
        self._sheet_name_lbl.pack(anchor="w")
        self._update_sheet_status()

        btn_row = tk.Frame(wrap, bg=BG)
        btn_row.pack(anchor="w", pady=(0, 8))
        _btn(btn_row, "📊  Connect Sheet", self._open_sheet_wizard,
             bg=GRN, fg=BG).pack(side="left", padx=(0, 12))

        skip_lbl = tk.Label(wrap, text="Lewati untuk sekarang", fg=MUT, bg=BG,
                             font=("Segoe UI", 9, "underline"), cursor="hand2")
        skip_lbl.pack(anchor="w")
        skip_lbl.bind("<Button-1>", lambda e: self._next())

        self._sheet_next_btn = _btn(wrap, "Lanjut  →", self._next, bg=GRN, fg=BG)
        if self._sheet_done:
            self._sheet_next_btn.pack(anchor="w", pady=(14, 0))

    def _update_sheet_status(self):
        sheets = self._ud.sheets if self._ud else []
        if sheets:
            self._sheet_done = True
            self._sheet_status_lbl.configure(text="✅  Sheet Terhubung!", fg=GRN)
            self._sheet_name_lbl.configure(text=sheets[0].get("name", ""), fg=GRN)
        else:
            self._sheet_done = False
            self._sheet_status_lbl.configure(text="⚪  Belum ada sheet.", fg=MUT)
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

            SheetsAuthWizard(self._win, on_done=_on_done).start_wizard()
        except Exception as e:
            self._sheet_status_lbl.configure(
                text="Error: {}".format(str(e)[:80]), fg=RED)

    # ── Step 4: Template task ──────────────────────────────────────────────────
    def _step_task(self):
        ca = self._content_area
        wrap = tk.Frame(ca, bg=BG)
        wrap.pack(expand=True, fill="both", padx=48, pady=24)

        self._section_title(wrap, "Step 3: Buat Task Pertamamu",
                            "Pilih template untuk mulai lebih cepat.")

        grid = tk.Frame(wrap, bg=BG)
        grid.pack(fill="x", pady=(0, 14))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        for idx, tpl in enumerate(_TEMPLATE_CARDS):
            row_i = idx // 2
            col_i = idx % 2
            color = tpl["color"]

            card = tk.Frame(grid, bg=CARD, cursor="hand2")
            card.grid(row=row_i, column=col_i, padx=5, pady=5, sticky="nsew")

            # Left color stripe
            tk.Frame(card, bg=color, width=3).pack(side="left", fill="y")
            body = tk.Frame(card, bg=CARD, padx=14, pady=10)
            body.pack(side="left", fill="both", expand=True)

            top = tk.Frame(body, bg=CARD)
            top.pack(anchor="w", pady=(0, 4))
            tk.Label(top, text=tpl["icon"], bg=CARD, fg=color,
                     font=("Segoe UI", 14)).pack(side="left", padx=(0, 6))
            tk.Label(top, text=tpl["name"], bg=CARD, fg=FG,
                     font=("Segoe UI", 9, "bold")).pack(side="left", anchor="w")

            tk.Label(body, text=tpl["description"], bg=CARD, fg=MUT,
                     font=("Segoe UI", 8), wraplength=240,
                     justify="left").pack(anchor="w", pady=(0, 6))

            use_btn = tk.Button(body, text="Gunakan Template",
                                bg=color, fg=BG,
                                font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                                padx=8, pady=3, cursor="hand2",
                                command=lambda t=tpl: self._pick_template(t))
            use_btn.pack(anchor="w")

            def _hover_on(e, f=card):
                f.configure(bg=SIDE)
                for ch in f.winfo_children():
                    _set_bg_deep(ch, SIDE)
            def _hover_off(e, f=card):
                f.configure(bg=CARD)
                for ch in f.winfo_children():
                    _set_bg_deep(ch, CARD)
            card.bind("<Enter>", _hover_on)
            card.bind("<Leave>", _hover_off)

        tk.Frame(wrap, bg=BORDER, height=1).pack(fill="x", pady=(4, 8))
        skip_row = tk.Frame(wrap, bg=BG)
        skip_row.pack(anchor="w")
        tk.Label(skip_row, text="Mau mulai dari kosong? ", fg=MUT, bg=BG,
                 font=("Segoe UI", 9)).pack(side="left")
        skip_lbl = tk.Label(skip_row, text="Lewati", fg=ACC, bg=BG,
                             font=("Segoe UI", 9, "underline"), cursor="hand2")
        skip_lbl.pack(side="left")
        skip_lbl.bind("<Button-1>", lambda e: self._next())

    def _pick_template(self, template_card):
        import json as _json
        tpl_path = os.path.join(_ROOT, "data", "templates.json")
        matched = None
        try:
            with open(tpl_path, "r", encoding="utf-8") as _f:
                templates = _json.load(_f)
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

    # ── Step 5: Done ───────────────────────────────────────────────────────────
    def _step_done(self):
        ca = self._content_area
        wrap = tk.Frame(ca, bg=BG)
        wrap.pack(expand=True, fill="both", padx=60, pady=28)

        # Animated success icon
        icon_lbl = tk.Label(wrap, text="🎉", bg=BG,
                             font=("Segoe UI", 44))
        icon_lbl.pack(pady=(4, 0))
        self._animate_icon_bounce(icon_lbl, 0)

        tk.Label(wrap, text="Kamu sudah siap!", bg=BG, fg=GRN,
                 font=("Segoe UI", 22, "bold")).pack(pady=(6, 4))
        tk.Label(wrap, text="Synthex siap untuk mengotomatiskan workflow kamu.",
                 bg=BG, fg=MUT, font=("Segoe UI", 10)).pack(pady=(0, 24))

        # Summary card
        outer, inner = self._card_frame(wrap, accent=GRN)
        outer.pack(fill="x", pady=(0, 22))

        tk.Label(inner, text="Ringkasan Setup", bg=CARD, fg=ACC,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))

        sheets = self._ud.sheets if self._ud else []

        rows = [
            ("Chrome Browser",
             "✅ Terhubung" if self._chrome_ok else "— Dilewati",
             GRN if self._chrome_ok else MUT),
            ("Google Sheet",
             "✅ " + (sheets[0].get("name", "Terhubung") if sheets else "—"),
             GRN if sheets else MUT),
            ("Templates", "✅ Siap digunakan", GRN),
        ]
        for label, status, color in rows:
            row = tk.Frame(inner, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, bg=CARD, fg=MUT,
                     font=("Segoe UI", 9), width=18, anchor="w").pack(side="left")
            tk.Label(row, text=status, bg=CARD, fg=color,
                     font=("Segoe UI", 9, "bold")).pack(side="left")

        tk.Label(wrap, text="Kamu bisa menjalankan wizard ini kapan saja\ndari Pengaturan → Setup Guide.",
                 bg=BG, fg=MUT, font=("Segoe UI", 9),
                 justify="left").pack(anchor="w", pady=(0, 18))

        _btn(wrap, "Buka Synthex  →", self._finish,
             bg=ACC, fg=BG, font=("Segoe UI", 12, "bold"),
             padx=28, pady=11).pack(anchor="w")

    def _animate_icon_bounce(self, lbl, step):
        if not self._animating:
            return
        try:
            sizes = [44, 46, 48, 46, 44, 42, 44]
            sz = sizes[step % len(sizes)]
            lbl.configure(font=("Segoe UI", sz))
            self._win.after(120, self._animate_icon_bounce, lbl, step + 1)
        except Exception:
            pass


# ── Utility ────────────────────────────────────────────────────────────────────
def _set_bg_deep(widget, color):
    try:
        widget.configure(bg=color)
        for child in widget.winfo_children():
            _set_bg_deep(child, color)
    except Exception:
        pass


def onboarding_needed():
    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return not data.get("onboarding_complete", False)
    except Exception:
        return True
