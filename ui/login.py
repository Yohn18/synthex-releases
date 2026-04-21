# -*- coding: utf-8 -*-
"""ui/login.py - Premium animated login window for Synthex by Yohn18."""

import json
import math
import os
import random
import subprocess
import sys
import threading
import time
import tkinter as tk
from core.config import Config

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageTk
    _PIL = True
except ImportError:
    _PIL = False

# ── Color palette ─────────────────────────────────────────────────────────────
BG      = "#080810"
PANEL_L = "#0C0C1A"
ACCENT  = "#6C4AFF"
ACCENT2 = "#4A9EFF"
SUCCESS = "#00D4AA"
TEXT    = "#C8C8E8"
DIM     = "#6A6A8A"
BORDER  = "#252540"
RED     = "#FF5555"
FIELD   = "#10101E"
GLOW    = "#8B6AFF"

# ── Attempt tracking (AppData) ────────────────────────────────────────────────
_APPDATA_DIR   = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Synthex")
_ATTEMPTS_FILE = os.path.join(_APPDATA_DIR, "attempts.json")

def _load_attempts():
    try:
        with open(_ATTEMPTS_FILE, "r") as f:
            return json.load(f).get("count", 0)
    except Exception:
        return 0

def _save_attempts(count):
    os.makedirs(_APPDATA_DIR, exist_ok=True)
    with open(_ATTEMPTS_FILE, "w") as f:
        json.dump({"count": count}, f)

def _reset_attempts():
    try:
        os.remove(_ATTEMPTS_FILE)
    except Exception:
        pass

def _self_destruct():
    exe_path    = sys.executable
    appdata_dir = _APPDATA_DIR
    bat_content = (
        "@echo off\r\n"
        "ping 127.0.0.1 -n 3 > nul\r\n"
        "del /F /Q \"{exe}\"\r\n"
        "rmdir /S /Q \"{appdata}\"\r\n"
        "del /F /Q \"%~f0\"\r\n"
    ).format(exe=exe_path, appdata=appdata_dir)
    bat_path = os.path.join(os.environ.get("TEMP", ""), "synthex_cleanup.bat")
    with open(bat_path, "w") as f:
        f.write(bat_content)
    subprocess.Popen(bat_path, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)


# ── PIL image generators ───────────────────────────────────────────────────────
def _make_bg(W, H):
    """Generate dark gradient background with subtle purple/blue glow blobs."""
    img = Image.new("RGB", (W, H), (8, 8, 16))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Left glow blob (purple)
    for r in range(220, 0, -4):
        a = int((220 - r) / 220 * 55)
        cx, cy = int(W * 0.27), int(H * 0.5)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(108, 74, 255, a))
    # Right glow blob (blue)
    for r in range(160, 0, -4):
        a = int((160 - r) / 160 * 40)
        cx, cy = int(W * 0.78), int(H * 0.5)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(74, 158, 255, a))
    # Bottom-right accent
    for r in range(100, 0, -4):
        a = int((100 - r) / 100 * 25)
        draw.ellipse([W - r, H - r, W + r, H + r], fill=(0, 212, 170, a))
    blurred = overlay.filter(ImageFilter.GaussianBlur(40))
    base = img.convert("RGBA")
    result = Image.alpha_composite(base, blurred)
    return result.convert("RGB")


def _make_logo(size=96):
    """Generate Synthex lightning-bolt logo on circular background."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size // 2
    r = size // 2 - 4
    # Outer glow rings
    for i in range(6, 0, -1):
        a = int(i / 6 * 50)
        rg = r + i * 2
        draw.ellipse([cx - rg, cy - rg, cx + rg, cy + rg],
                     outline=(108, 74, 255, a), width=2)
    # Main circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 fill=(13, 13, 30, 240), outline=(108, 74, 255, 220), width=2)
    # Inner ring
    ri = r - 5
    draw.ellipse([cx - ri, cy - ri, cx + ri, cy + ri],
                 outline=(74, 158, 255, 70), width=1)
    # Lightning bolt
    bw = size * 0.28
    bh = size * 0.52
    bx = cx - bw * 0.2
    by = cy - bh * 0.5
    bolt = [
        (bx + bw * 0.6, by),
        (bx, by + bh * 0.48),
        (bx + bw * 0.45, by + bh * 0.44),
        (bx - bw * 0.1, by + bh),
        (bx + bw * 0.5, by + bh * 0.52),
        (bx + bw * 0.15, by + bh * 0.56),
    ]
    bolt = [(int(x), int(y)) for x, y in bolt]
    draw.polygon(bolt, fill=(180, 140, 255, 255))
    # Bright inner bolt
    scale = 0.7
    cx2 = sum(x for x, _ in bolt) / len(bolt)
    cy2 = sum(y for _, y in bolt) / len(bolt)
    ibolt = [(int(cx2 + (x - cx2) * scale), int(cy2 + (y - cy2) * scale))
             for x, y in bolt]
    draw.polygon(ibolt, fill=(220, 200, 255, 255))
    return img.filter(ImageFilter.GaussianBlur(0.4))


def _make_logo_glow(size=96, intensity=1.0):
    """Glow ring around the logo for pulse animation."""
    img = Image.new("RGBA", (size + 40, size + 40), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = (size + 40) // 2
    r_base = size // 2 + 2
    for i in range(12, 0, -1):
        a = int(i / 12 * 80 * intensity)
        rg = r_base + i * 2
        draw.ellipse([cx - rg, cy - rg, cx + rg, cy + rg],
                     outline=(108, 74, 255, a), width=3)
    return img.filter(ImageFilter.GaussianBlur(3))


# ── Particle system ────────────────────────────────────────────────────────────
_PARTICLE_COLORS = [
    (108, 74, 255),   # purple
    (74, 158, 255),   # blue
    (0, 212, 170),    # teal
    (180, 100, 255),  # violet
]

class _Particle:
    def __init__(self, W, H, start_random=True):
        self.W = W
        self.H = H
        self.reset(start_random)

    def reset(self, random_y=False):
        self.x  = random.uniform(0, self.W)
        self.y  = random.uniform(0, self.H) if random_y else self.H + 5
        self.vx = random.uniform(-0.25, 0.25)
        self.vy = random.uniform(-0.5, -0.9)
        self.r  = random.uniform(1.2, 2.8)
        self.alpha = random.uniform(0.25, 0.75)
        self.color = random.choice(_PARTICLE_COLORS)
        self.phase = random.uniform(0, math.pi * 2)

    def update(self, t):
        self.x += self.vx + math.sin(t * 0.3 + self.phase) * 0.15
        self.y += self.vy
        if self.y < -10:
            self.reset(False)
        if self.x < -10:
            self.x = self.W + 5
        elif self.x > self.W + 10:
            self.x = -5

    @property
    def hex_color(self):
        r, g, b = self.color
        a = self.alpha
        # blend with bg (#080810)
        br, bg_, bb = 8, 8, 16
        fr = int(br + (r - br) * a)
        fg_ = int(bg_ + (g - bg_) * a)
        fb = int(bb + (b - bb) * a)
        return "#{:02x}{:02x}{:02x}".format(
            min(255, fr), min(255, fg_), min(255, fb))


# ── LoginWindow ────────────────────────────────────────────────────────────────
class LoginWindow:
    """Animated premium login window. Call .show() to block until result."""

    _W = 840
    _H = 490

    def __init__(self, config: Config):
        self.config = config
        self._result           = None
        self._spinner_running  = False
        self._spinner_idx      = 0
        self._show_pass        = False
        self._progress_val     = 0.0
        self._progress_running = False
        self._particles        = []
        self._part_t           = 0.0
        self._part_ids         = []
        self._alpha            = 0.0
        self._pulse_phase      = 0.0
        self._logo_photo       = None
        self._bg_photo         = None
        self._glow_photo       = None
        self._animating        = True
        self._field_anim       = {}   # field -> (current_hex, target_hex, step)
        self._drag_x           = 0
        self._drag_y           = 0

    # ── Public ────────────────────────────────────────────────────────────────
    def show(self) -> dict:
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.configure(bg=BG)
        self._root.resizable(False, False)
        self._root.attributes("-alpha", 0.0)

        # Icon
        _base = sys._MEIPASS if hasattr(sys, "_MEIPASS") else \
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for _ic in [os.path.join(_base, "assets", "synthex.ico"),
                    os.path.join(_base, "synthex.ico")]:
            if os.path.exists(_ic):
                try:
                    self._root.iconbitmap(_ic)
                except Exception:
                    pass
                break

        # Center on screen
        W, H = self._W, self._H
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x  = (sw - W) // 2
        y  = (sh - H) // 2
        self._root.geometry("{W}x{H}+{x}+{y}".format(W=W, H=H, x=x, y=y))
        self._root.deiconify()

        self._build_ui()

        # Pre-generate PIL images in background so UI opens instantly
        threading.Thread(target=self._load_pil_images, daemon=True).start()

        self._fade_in()
        self._root.mainloop()
        return self._result or {"success": False}

    # ── PIL asset loading ─────────────────────────────────────────────────────
    def _load_pil_images(self):
        if not _PIL:
            return
        try:
            bg_pil  = _make_bg(self._W, self._H)
            logo_pil = _make_logo(96)
            glow_pil = _make_logo_glow(96, 1.0)

            def _apply():
                try:
                    self._bg_photo   = ImageTk.PhotoImage(bg_pil)
                    self._logo_photo = ImageTk.PhotoImage(logo_pil)
                    self._glow_photo = ImageTk.PhotoImage(glow_pil)
                    # Place background image at canvas bottom layer
                    self._bg_canvas.create_image(0, 0, anchor="nw",
                                                 image=self._bg_photo, tags="bg")
                    self._bg_canvas.tag_lower("bg")
                    # Place logo
                    lx = int(self._W * 0.205)
                    ly = int(self._H * 0.32)
                    self._logo_canvas.create_image(
                        lx, ly, anchor="center",
                        image=self._logo_photo, tags="logo_img")
                    self._glow_canvas_img = self._logo_canvas.create_image(
                        lx, ly, anchor="center",
                        image=self._glow_photo, tags="glow_img")
                    self._logo_lx = lx
                    self._logo_ly = ly
                    self._pulse_phase = 0.0
                    self._animate_pulse()
                except Exception:
                    pass
            self._root.after(0, _apply)
        except Exception:
            pass

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        W, H = self._W, self._H
        LEFT_W  = int(W * 0.39)   # ~328 px
        RIGHT_X = LEFT_W + 1
        RIGHT_W = W - RIGHT_X

        # ── Background canvas (particles + gradient) ──────────────────────────
        self._bg_canvas = tk.Canvas(
            self._root, width=W, height=H, bg=BG,
            highlightthickness=0)
        self._bg_canvas.place(x=0, y=0)

        # ── Custom titlebar ───────────────────────────────────────────────────
        tb = tk.Frame(self._root, bg="#06060F", height=26)
        tb.place(x=0, y=0, width=W)
        tb.lift()

        tk.Label(tb, text="  ⚡  SYNTHEX", bg="#06060F", fg=DIM,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=4)

        close_btn = tk.Label(tb, text=" ✕ ", bg="#06060F", fg=DIM,
                              font=("Segoe UI", 9), cursor="hand2")
        close_btn.pack(side="right", padx=2)
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>",    lambda e: close_btn.configure(bg=RED, fg="white"))
        close_btn.bind("<Leave>",    lambda e: close_btn.configure(bg="#06060F", fg=DIM))

        min_btn = tk.Label(tb, text=" — ", bg="#06060F", fg=DIM,
                           font=("Segoe UI", 9), cursor="hand2")
        min_btn.pack(side="right", padx=2)
        min_btn.bind("<Button-1>", lambda e: self._minimize())
        min_btn.bind("<Enter>",    lambda e: min_btn.configure(bg=BORDER))
        min_btn.bind("<Leave>",    lambda e: min_btn.configure(bg="#06060F"))

        # Drag the titlebar
        tb.bind("<ButtonPress-1>",   self._drag_start)
        tb.bind("<B1-Motion>",       self._drag_move)

        # ── Left panel overlay ────────────────────────────────────────────────
        lf = tk.Frame(self._root, bg=PANEL_L, width=LEFT_W, height=H - 26)
        lf.place(x=0, y=26)
        lf.pack_propagate(False)

        # Top gradient stripe (2-color)
        stripe_h = 3
        tk.Frame(lf, bg=ACCENT,  height=stripe_h,
                 width=LEFT_W // 2).place(x=0, y=0)
        tk.Frame(lf, bg=ACCENT2, height=stripe_h,
                 width=LEFT_W // 2).place(x=LEFT_W // 2, y=0)

        # Bottom gradient stripe
        tk.Frame(lf, bg=ACCENT,  height=stripe_h,
                 width=LEFT_W // 2).place(x=0, y=H - 26 - stripe_h)
        tk.Frame(lf, bg=ACCENT2, height=stripe_h,
                 width=LEFT_W // 2).place(x=LEFT_W // 2, y=H - 26 - stripe_h)

        # Logo canvas (receives PIL logo image later)
        self._logo_canvas = tk.Canvas(
            lf, width=LEFT_W, height=H - 26,
            bg=PANEL_L, highlightthickness=0)
        self._logo_canvas.place(x=0, y=0)
        self._logo_lx = int(LEFT_W * 0.5)
        self._logo_ly = int((H - 26) * 0.30)

        # Fallback text logo (shown until PIL image loads)
        self._logo_canvas.create_text(
            LEFT_W // 2, int((H - 26) * 0.30),
            text="⚡", font=("Segoe UI", 30),
            fill=ACCENT, tags="fallback_icon")

        # SYNTHEX text
        self._logo_canvas.create_text(
            LEFT_W // 2, int((H - 26) * 0.50),
            text="SYNTHEX", font=("Segoe UI", 34, "bold"),
            fill=ACCENT, tags="brand_text")

        # Subtitle
        self._logo_canvas.create_text(
            LEFT_W // 2, int((H - 26) * 0.62),
            text="AUTOMATION PLATFORM", font=("Segoe UI", 9, "bold"),
            fill=ACCENT2, tags="sub_text")

        # Divider
        dw = int(LEFT_W * 0.65)
        self._logo_canvas.create_line(
            LEFT_W // 2 - dw // 2, int((H - 26) * 0.71),
            LEFT_W // 2 + dw // 2, int((H - 26) * 0.71),
            fill=BORDER, width=1)

        # by Yohn18
        self._logo_canvas.create_text(
            LEFT_W // 2, int((H - 26) * 0.80),
            text="by Yohn18", font=("Segoe UI", 9),
            fill=DIM)

        # Version
        ver = self.config.get("app.version", "1.2.2")
        self._logo_canvas.create_text(
            LEFT_W // 2, int((H - 26) * 0.89),
            text="v{}".format(ver), font=("Segoe UI", 8),
            fill="#333358")

        # Vertical separator (subtle glow line)
        tk.Frame(self._root, bg="#1A1A35", width=1, height=H - 26).place(x=LEFT_W, y=26)
        tk.Frame(self._root, bg=BORDER,   width=1, height=H - 26).place(x=LEFT_W + 1, y=26)

        # ── Right panel ───────────────────────────────────────────────────────
        rf = tk.Frame(self._root, bg=BG, width=RIGHT_W, height=H - 26)
        rf.place(x=RIGHT_X, y=26)
        rf.pack_propagate(False)
        rf.lift()

        # Top accent bar
        tk.Frame(rf, bg=ACCENT, height=3, width=RIGHT_W).place(x=0, y=0)

        inner_x = 34
        inner_w = RIGHT_W - 68

        # Header
        tk.Label(rf, text="WELCOME BACK", bg=BG, fg=TEXT,
                 font=("Segoe UI", 17, "bold")).place(relx=0.5, y=36, anchor="center")

        # Accent underline
        ul_w = 90
        self._ul_canvas = tk.Canvas(rf, width=ul_w, height=3, bg=BG,
                                     highlightthickness=0)
        self._ul_canvas.place(relx=0.5, y=57, anchor="center")
        self._ul_rect = self._ul_canvas.create_rectangle(0, 0, ul_w, 3,
                                                          fill=ACCENT, outline="")
        self._animate_underline(0)

        # Tagline
        tk.Label(rf, text="Masukkan kredensial untuk melanjutkan",
                 bg=BG, fg=DIM, font=("Segoe UI", 8)).place(relx=0.5, y=72, anchor="center")

        # ── Email field ───────────────────────────────────────────────────────
        tk.Label(rf, text="EMAIL", bg=BG, fg=DIM,
                 font=("Segoe UI", 8, "bold")).place(x=inner_x, y=94)

        self._ef_frame = tk.Frame(rf, bg=BORDER, padx=1, pady=1)
        self._ef_frame.place(x=inner_x, y=110, width=inner_w, height=36)
        ef_inner = tk.Frame(self._ef_frame, bg=FIELD)
        ef_inner.pack(fill="both", expand=True)

        tk.Label(ef_inner, text="✉", bg=FIELD, fg=DIM,
                 font=("Segoe UI", 11), padx=9).pack(side="left")
        tk.Frame(ef_inner, bg=BORDER, width=1).pack(side="left", fill="y", pady=4)

        self._email_var = tk.StringVar(value=self.config.get("ui.last_email", ""))
        self._email_entry = tk.Entry(
            ef_inner, textvariable=self._email_var,
            bg=FIELD, fg=TEXT, insertbackground=ACCENT,
            font=("Segoe UI", 10), relief="flat", bd=6, highlightthickness=0)
        self._email_entry.pack(side="left", fill="both", expand=True)
        self._email_entry.bind("<FocusIn>",  lambda e: self._field_focus(self._ef_frame, True))
        self._email_entry.bind("<FocusOut>", lambda e: self._field_focus(self._ef_frame, False))

        # ── Password field ────────────────────────────────────────────────────
        tk.Label(rf, text="PASSWORD", bg=BG, fg=DIM,
                 font=("Segoe UI", 8, "bold")).place(x=inner_x, y=162)

        self._pf_frame = tk.Frame(rf, bg=BORDER, padx=1, pady=1)
        self._pf_frame.place(x=inner_x, y=178, width=inner_w, height=36)
        pf_inner = tk.Frame(self._pf_frame, bg=FIELD)
        pf_inner.pack(fill="both", expand=True)

        tk.Label(pf_inner, text="🔒", bg=FIELD, fg=DIM,
                 font=("Segoe UI", 11), padx=9).pack(side="left")
        tk.Frame(pf_inner, bg=BORDER, width=1).pack(side="left", fill="y", pady=4)

        self._pass_var = tk.StringVar()
        self._pass_entry = tk.Entry(
            pf_inner, textvariable=self._pass_var,
            show="●", bg=FIELD, fg=TEXT, insertbackground=ACCENT,
            font=("Segoe UI", 10), relief="flat", bd=6, highlightthickness=0)
        self._pass_entry.pack(side="left", fill="both", expand=True)

        self._eye_btn = tk.Button(
            pf_inner, text="👁", bg=FIELD, fg=DIM,
            relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 10), padx=9,
            command=self._toggle_pass,
            activebackground=FIELD, activeforeground=TEXT)
        self._eye_btn.pack(side="right")
        self._pass_entry.bind("<FocusIn>",  lambda e: self._field_focus(self._pf_frame, True))
        self._pass_entry.bind("<FocusOut>", lambda e: self._field_focus(self._pf_frame, False))

        # ── Remember me ───────────────────────────────────────────────────────
        self._stay_var = tk.BooleanVar(
            value=bool(self.config.get("ui.stay_logged_in", False)))
        tk.Checkbutton(
            rf, text="Ingat saya  (auto-login 24 jam)",
            variable=self._stay_var,
            bg=BG, fg=DIM, selectcolor=BORDER,
            activebackground=BG, activeforeground=TEXT,
            font=("Segoe UI", 8), relief="flat",
            highlightthickness=0).place(x=inner_x, y=228)

        # ── LOGIN button ──────────────────────────────────────────────────────
        self._login_btn = tk.Button(
            rf, text="LOGIN",
            bg=ACCENT, fg="white",
            activebackground=GLOW, activeforeground="white",
            disabledforeground="#4A3A99",
            font=("Segoe UI", 11, "bold"),
            relief="flat", bd=0, cursor="hand2",
            command=self._do_login)
        self._login_btn.place(x=inner_x, y=258, width=inner_w, height=42)
        self._login_btn.bind("<Enter>", self._btn_hover_on)
        self._login_btn.bind("<Leave>", self._btn_hover_off)

        # Shimmer line under button
        self._sh_canvas = tk.Canvas(rf, width=inner_w, height=2, bg=BG,
                                     highlightthickness=0)
        self._sh_canvas.place(x=inner_x, y=302)
        self._sh_pos  = 0
        self._sh_rect = self._sh_canvas.create_rectangle(0, 0, 0, 2,
                                                          fill=GLOW, outline="")
        self._animate_shimmer()

        # ── Progress bar ──────────────────────────────────────────────────────
        pb_bg = tk.Frame(rf, bg=BORDER)
        pb_bg.place(x=inner_x, y=308, width=inner_w, height=4)
        self._progress_canvas = tk.Canvas(
            pb_bg, bg=BORDER, height=4, width=inner_w - 2,
            highlightthickness=0)
        self._progress_canvas.pack()
        self._progress_bar_w = inner_w - 2
        self._progress_rect  = self._progress_canvas.create_rectangle(
            0, 0, 0, 4, fill=ACCENT, outline="")

        # ── Status labels ─────────────────────────────────────────────────────
        self._status_var = tk.StringVar()
        self._status_lbl = tk.Label(
            rf, textvariable=self._status_var,
            bg=BG, fg=DIM, font=("Segoe UI", 8))
        self._status_lbl.place(relx=0.5, y=322, anchor="center")

        self._error_var = tk.StringVar()
        tk.Label(
            rf, textvariable=self._error_var,
            bg=BG, fg=RED, font=("Segoe UI", 8),
            wraplength=inner_w).place(relx=0.5, y=344, anchor="center")

        # Copyright
        tk.Label(rf, text="© 2025 Synthex  ·  All rights reserved",
                 bg=BG, fg="#1E1E38",
                 font=("Segoe UI", 7)).place(relx=0.5, y=H - 40, anchor="center")

        # ── Key bindings & focus ──────────────────────────────────────────────
        self._root.bind("<Return>", lambda _: self._do_login())
        if self._email_var.get():
            self._pass_entry.focus_set()
        else:
            self._email_entry.focus_set()

        # ── Start particle animation ──────────────────────────────────────────
        self._init_particles()
        self._animate_particles()

    # ── Drag ─────────────────────────────────────────────────────────────────
    def _drag_start(self, e):
        self._drag_x = e.x_root - self._root.winfo_x()
        self._drag_y = e.y_root - self._root.winfo_y()

    def _drag_move(self, e):
        x = e.x_root - self._drag_x
        y = e.y_root - self._drag_y
        self._root.geometry("+{}+{}".format(x, y))

    def _minimize(self):
        try:
            self._root.overrideredirect(False)
            self._root.iconify()
            def _restore_override():
                try:
                    self._root.overrideredirect(True)
                    self._root.deiconify()
                except Exception:
                    pass
            self._root.bind("<Map>", lambda e: (_restore_override(), None))
        except Exception:
            pass

    # ── Particles ─────────────────────────────────────────────────────────────
    def _init_particles(self):
        W, H = self._W, self._H
        self._particles = [_Particle(W, H, start_random=True) for _ in range(22)]
        self._part_ids  = [None] * len(self._particles)

    def _animate_particles(self):
        if not self._animating:
            return
        try:
            canvas = self._bg_canvas
            self._part_t += 0.04
            for i, p in enumerate(self._particles):
                p.update(self._part_t)
                cid = self._part_ids[i]
                x0, y0 = p.x - p.r, p.y - p.r
                x1, y1 = p.x + p.r, p.y + p.r
                col = p.hex_color
                if cid is None:
                    self._part_ids[i] = canvas.create_oval(
                        x0, y0, x1, y1, fill=col, outline="")
                else:
                    canvas.coords(cid, x0, y0, x1, y1)
                    canvas.itemconfigure(cid, fill=col)
            self._root.after(40, self._animate_particles)   # ~25 fps
        except Exception:
            pass

    # ── Logo pulse animation ──────────────────────────────────────────────────
    def _animate_pulse(self):
        if not self._animating or not _PIL:
            return
        try:
            self._pulse_phase += 0.05
            intensity = (math.sin(self._pulse_phase) + 1) * 0.5  # 0..1
            glow_pil = _make_logo_glow(96, intensity * 0.9 + 0.1)
            self._glow_photo = ImageTk.PhotoImage(glow_pil)
            if self._glow_canvas_img:
                self._logo_canvas.itemconfigure(
                    self._glow_canvas_img, image=self._glow_photo)
            self._root.after(60, self._animate_pulse)   # ~17 fps
        except Exception:
            pass

    # ── Underline pulse ────────────────────────────────────────────────────────
    def _animate_underline(self, step):
        if not self._animating:
            return
        try:
            phase = step * 0.04
            w = int(40 + 50 * (math.sin(phase) + 1) * 0.5)
            cx = 45   # center of 90px canvas
            self._ul_canvas.coords(self._ul_rect, cx - w // 2, 0, cx + w // 2, 3)
            self._root.after(50, self._animate_underline, step + 1)
        except Exception:
            pass

    # ── Button shimmer ─────────────────────────────────────────────────────────
    def _animate_shimmer(self):
        if not self._animating:
            return
        try:
            W = self._progress_bar_w
            self._sh_pos = (self._sh_pos + 3) % (W + 60)
            p = self._sh_pos - 30
            self._sh_canvas.coords(self._sh_rect,
                                   max(0, p), 0, min(W, p + 60), 2)
            col = GLOW if self._login_btn["state"] == "normal" else BORDER
            self._sh_canvas.itemconfigure(self._sh_rect, fill=col)
            self._root.after(25, self._animate_shimmer)
        except Exception:
            pass

    # ── Button hover ──────────────────────────────────────────────────────────
    def _btn_hover_on(self, _=None):
        try:
            self._login_btn.configure(bg=GLOW)
        except Exception:
            pass

    def _btn_hover_off(self, _=None):
        try:
            if self._login_btn["state"] == "normal":
                self._login_btn.configure(bg=ACCENT)
        except Exception:
            pass

    # ── Field focus glow ──────────────────────────────────────────────────────
    def _field_focus(self, frame, on):
        target = ACCENT if on else BORDER
        self._animate_field_color(frame, target)

    def _animate_field_color(self, frame, target_hex, steps=8):
        try:
            current = frame.cget("bg")
            cr, cg, cb = int(current[1:3], 16), int(current[3:5], 16), int(current[5:7], 16)
            tr, tg, tb = int(target_hex[1:3], 16), int(target_hex[3:5], 16), int(target_hex[5:7], 16)
            if steps <= 0 or current == target_hex:
                frame.configure(bg=target_hex)
                return
            nr = cr + (tr - cr) // steps
            ng = cg + (tg - cg) // steps
            nb = cb + (tb - cb) // steps
            new_hex = "#{:02x}{:02x}{:02x}".format(
                max(0, min(255, nr)), max(0, min(255, ng)), max(0, min(255, nb)))
            frame.configure(bg=new_hex)
            self._root.after(16, self._animate_field_color, frame, target_hex, steps - 1)
        except Exception:
            pass

    # ── Fade animations ────────────────────────────────────────────────────────
    def _fade_in(self, step=0):
        target = 0.97
        steps  = 20
        alpha  = min(target, step / steps * target)
        try:
            self._root.attributes("-alpha", alpha)
        except Exception:
            pass
        if step < steps:
            self._root.after(18, self._fade_in, step + 1)

    def _fade_out(self, callback, step=0):
        steps = 16
        alpha = max(0.0, 1.0 - step / steps)
        try:
            self._root.attributes("-alpha", alpha)
        except Exception:
            pass
        if step < steps:
            self._root.after(16, self._fade_out, callback, step + 1)
        else:
            callback()

    # ── Progress bar ─────────────────────────────────────────────────────────
    def _animate_progress(self):
        if not self._progress_running:
            return
        self._progress_val = min(self._progress_val + 0.012, 0.92)
        w = int(self._progress_bar_w * self._progress_val)
        self._progress_canvas.coords(self._progress_rect, 0, 0, w, 4)
        self._root.after(60, self._animate_progress)

    def _finish_progress(self, success):
        self._progress_running = False
        self._spinner_running  = False
        try:
            fill = SUCCESS if success else RED
            self._progress_canvas.itemconfigure(self._progress_rect, fill=fill)
            self._progress_canvas.coords(
                self._progress_rect, 0, 0, self._progress_bar_w, 4)
            self._root.after(600, lambda: self._progress_canvas.coords(
                self._progress_rect, 0, 0, 0, 4))
            self._root.after(620, lambda: self._progress_canvas.itemconfigure(
                self._progress_rect, fill=ACCENT))
        except Exception:
            pass

    def _animate_spinner(self):
        if not self._spinner_running:
            return
        frames = ["Memproses   ", "Memproses.  ", "Memproses.. ", "Memproses..."]
        self._status_var.set(frames[self._spinner_idx % len(frames)])
        self._spinner_idx += 1
        self._root.after(280, self._animate_spinner)

    # ── Logic ────────────────────────────────────────────────────────────────
    def _toggle_pass(self):
        self._show_pass = not self._show_pass
        self._pass_entry.configure(show="" if self._show_pass else "●")

    def _do_login(self):
        email    = self._email_var.get().strip()
        password = self._pass_var.get()
        if not email:
            self._error_var.set("❌  Masukkan alamat email")
            return
        if not password:
            self._error_var.set("❌  Masukkan password")
            return
        if "@" not in email:
            email += "@gmail.com"

        self._login_btn.configure(state="disabled", bg="#3D3A88")
        self._error_var.set("")
        self._spinner_running = True
        self._spinner_idx     = 0
        self._status_lbl.configure(fg=DIM)
        self._animate_spinner()
        self._progress_val     = 0.0
        self._progress_running = True
        self._animate_progress()
        self._root.after(
            15000,
            lambda: self._finish_progress(False) if self._progress_running else None)

        api_key = self.config.get("firebase.api_key", "")

        def _run():
            from auth.firebase_auth import sign_in_with_email_password
            res = sign_in_with_email_password(email, password, api_key)
            self._root.after(0, self._on_auth_result, res, email)

        threading.Thread(target=_run, daemon=True).start()

    def _on_auth_result(self, result, email):
        self._spinner_running = False
        self._login_btn.configure(state="normal", bg=ACCENT)

        if result.get("success"):
            _reset_attempts()
            self._finish_progress(True)
            self._status_var.set("✅  Berhasil masuk!")
            self._status_lbl.configure(fg=SUCCESS)
            stay = self._stay_var.get()
            self.config.set("ui.stay_logged_in", stay)
            self.config.set("ui.last_email", email)
            self.config.save()
            if not stay:
                from auth.firebase_auth import logout as _clear  # noqa
                self.config.set("ui._clear_token_on_exit", True)
                self.config.save()
            self._result = result
            # Fade out then destroy
            self._root.after(500, lambda: self._fade_out(self._root.destroy))
        else:
            self._finish_progress(False)
            self._status_var.set("")
            count = _load_attempts() + 1
            _save_attempts(count)
            if count >= 3:
                self._dark_alert(
                    "Peringatan",
                    "Terlalu banyak percobaan gagal.\nAplikasi akan dihapus.",
                    accent=RED)
                self._root.after(2000, self._trigger_self_destruct)
            elif count == 2:
                self._error_var.set(
                    "⚠️ Peringatan! 1 percobaan tersisa sebelum aplikasi dihapus!")
            else:
                self._error_var.set(
                    "❌  {}".format(result.get("error", "Email atau password salah.")))

    def _dark_alert(self, title, message, accent=None):
        accent = accent or ACCENT
        dlg = tk.Toplevel(self._root)
        dlg.title("")
        dlg.resizable(False, False)
        dlg.configure(bg="#0A0A14")
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        W, H = 360, 180
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        dlg.geometry("{}x{}+{}+{}".format(W, H, (sw - W) // 2, (sh - H) // 2))
        # Animated top border
        bc = tk.Canvas(dlg, width=W, height=3, bg=accent, highlightthickness=0)
        bc.place(x=0, y=0)
        tk.Label(dlg, text=title, bg="#0A0A14", fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(pady=(22, 0))
        tk.Label(dlg, text=message, bg="#0A0A14", fg=DIM,
                 font=("Segoe UI", 9), justify="center",
                 wraplength=310).pack(pady=(8, 12))
        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x", padx=20)
        tk.Button(dlg, text="  OK  ", bg=accent, fg="white",
                  relief="flat", font=("Segoe UI", 10, "bold"),
                  cursor="hand2", padx=12, pady=5,
                  command=dlg.destroy).pack(pady=12)
        dlg.grab_set()
        dlg.focus_force()
        dlg.wait_window(dlg)

    def _trigger_self_destruct(self):
        try:
            _self_destruct()
        except Exception:
            pass
        self._root.destroy()

    def _on_close(self):
        self._animating       = False
        self._spinner_running = False
        self._progress_running = False
        self._result = {"success": False}
        self._fade_out(self._root.destroy)
