"""
ui/login.py - Game-style (Point Blank) login window for Synthex by Yohn18.
Theme: #0A0A0F background, #6C4AFF accent (purple), #4A9EFF secondary (blue).
"""

import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
from core.config import Config

# ── Color palette ────────────────────────────────────────────────────────────
BG      = "#0A0A0F"
CARD    = "#12121A"
ACCENT  = "#6C4AFF"
ACCENT2 = "#4A9EFF"
SUCCESS = "#00D4AA"
TEXT    = "#C8C8E8"
DIM     = "#6A6A8A"
BORDER  = "#2A2A4A"
RED     = "#FF5555"
FIELD   = "#12121F"

# ── Attempt tracking (AppData) ───────────────────────────────────────────────
_APPDATA_DIR   = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Synthex")
_ATTEMPTS_FILE = os.path.join(_APPDATA_DIR, "attempts.json")


def _load_attempts() -> int:
    try:
        with open(_ATTEMPTS_FILE, "r") as f:
            return json.load(f).get("count", 0)
    except Exception:
        return 0


def _save_attempts(count: int):
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
    subprocess.Popen(
        bat_path, shell=True,
        creationflags=subprocess.CREATE_NO_WINDOW)


# ── LoginWindow ───────────────────────────────────────────────────────────────
class LoginWindow:
    """Standalone login window. Call .show() to block until result."""

    _W = 750
    _H = 460

    def __init__(self, config: Config):
        self.config = config
        self._result: dict | None = None
        self._spinner_running  = False
        self._spinner_idx      = 0
        self._show_pass        = False
        self._scanline_offset  = 0
        self._progress_val     = 0.0
        self._progress_running = False
        self._cursor_visible   = True

    # ── Public ─────────────────────────────────────────────────────────────
    def show(self) -> dict:
        self._root = tk.Tk()
        if hasattr(sys, '_MEIPASS'):
            icon_path = os.path.join(sys._MEIPASS, 'synthex.ico')
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'synthex.ico')
        if os.path.exists(icon_path):
            self._root.iconbitmap(icon_path)
        self._root.title("Synthex")
        self._root.resizable(False, False)
        self._root.configure(bg=BG)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x  = (sw - self._W) // 2
        y  = (sh - self._H) // 2
        self._root.geometry(f"{self._W}x{self._H}+{x}+{y}")
        self._root.overrideredirect(False)
        self._root.lift()
        self._root.focus_force()
        self._build_ui()
        self._root.mainloop()
        return self._result or {"success": False}

    # ── UI construction ────────────────────────────────────────────────────
    def _build_ui(self):
        W, H = self._W, self._H

        # ── Root canvas (scanlines + background) ──────────────────────────
        self._bg_canvas = tk.Canvas(
            self._root, width=W, height=H,
            bg=BG, highlightthickness=0)
        self._bg_canvas.place(x=0, y=0)

        # Draw scanlines once (static thin lines, we shift them via scroll)
        self._scanline_ids = []
        for y in range(0, H + 6, 6):
            lid = self._bg_canvas.create_line(
                0, y, W, y, fill="#0F0F1A", width=1)
            self._scanline_ids.append(lid)

        # Vertical separator glow
        sep_x = int(W * 0.40)
        self._bg_canvas.create_line(sep_x, 20, sep_x, H - 20,
                                    fill=BORDER, width=1)
        self._bg_canvas.create_line(sep_x + 1, 20, sep_x + 1, H - 20,
                                    fill="#1A1A2E", width=1)

        # Corner brackets decoration
        brk = 18
        col = "#2A2A5A"
        for bx, by, dx, dy in [(10, 10, 1, 1), (W - 10, 10, -1, 1),
                                (10, H - 10, 1, -1), (W - 10, H - 10, -1, -1)]:
            self._bg_canvas.create_line(bx, by, bx + brk * dx, by,
                                        fill=col, width=2)
            self._bg_canvas.create_line(bx, by, bx, by + brk * dy,
                                        fill=col, width=2)

        # ── LEFT panel ────────────────────────────────────────────────────
        lf = tk.Frame(self._root, bg=BG, width=sep_x, height=H)
        lf.place(x=0, y=0)

        # Top accent stripe
        tk.Frame(lf, bg=ACCENT, height=3, width=sep_x - 20).place(x=10, y=0)

        # Logo
        tk.Label(lf, text="SYNTHEX", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 32, "bold")).place(
                     relx=0.5, rely=0.32, anchor="center")
        tk.Label(lf, text="AUTOMATION PLATFORM", bg=BG, fg=ACCENT2,
                 font=("Segoe UI", 9, "bold")).place(
                     relx=0.5, rely=0.47, anchor="center")

        # Decorative line under subtitle
        tk.Frame(lf, bg=BORDER, height=1, width=sep_x - 60).place(
            x=30, rely=0.54, anchor="w")

        tk.Label(lf, text="by Yohn18", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).place(
                     relx=0.5, rely=0.63, anchor="center")
        tk.Label(lf, text="v3.0", bg=BG, fg="#3A3A5A",
                 font=("Segoe UI", 8)).place(
                     relx=0.5, rely=0.73, anchor="center")

        # Bottom accent stripe
        tk.Frame(lf, bg=ACCENT, height=3, width=sep_x - 20).place(
            x=10, y=H - 3)

        # ── RIGHT panel ───────────────────────────────────────────────────
        rx = sep_x + 1
        rw = W - rx
        rf = tk.Frame(self._root, bg=BG, width=rw, height=H)
        rf.place(x=rx, y=0)

        # "MASUK" header
        tk.Label(rf, text="MASUK", bg=BG, fg=TEXT,
                 font=("Segoe UI", 16, "bold")).place(
                     relx=0.5, y=44, anchor="center")
        tk.Frame(rf, bg=ACCENT, height=2, width=80).place(
            relx=0.5, y=68, anchor="center")

        inner_x  = 30
        inner_w  = rw - 60

        # ── Email field ───────────────────────────────────────────────────
        tk.Label(rf, text="EMAIL", bg=BG, fg=DIM,
                 font=("Segoe UI", 8, "bold")).place(x=inner_x, y=98)

        ef_frame = tk.Frame(rf, bg=BORDER, padx=1, pady=1)
        ef_frame.place(x=inner_x, y=114, width=inner_w, height=34)
        ef_inner = tk.Frame(ef_frame, bg=FIELD)
        ef_inner.pack(fill="both", expand=True)

        tk.Label(ef_inner, text="✉", bg=FIELD, fg=DIM,
                 font=("Segoe UI", 10), padx=8).pack(side="left")
        tk.Frame(ef_inner, bg=BORDER, width=1).pack(side="left", fill="y", pady=4)

        self._email_var = tk.StringVar(value=self.config.get("ui.last_email", ""))
        self._email_entry = tk.Entry(
            ef_inner, textvariable=self._email_var,
            bg=FIELD, fg=TEXT, insertbackground=ACCENT,
            font=("Segoe UI", 10), relief="flat",
            bd=6, highlightthickness=0)
        self._email_entry.pack(side="left", fill="both", expand=True)
        self._email_entry.bind("<FocusIn>",  lambda e: ef_frame.configure(bg=ACCENT))
        self._email_entry.bind("<FocusOut>", lambda e: ef_frame.configure(bg=BORDER))

        # ── Password field ────────────────────────────────────────────────
        tk.Label(rf, text="PASSWORD", bg=BG, fg=DIM,
                 font=("Segoe UI", 8, "bold")).place(x=inner_x, y=166)

        pf_frame = tk.Frame(rf, bg=BORDER, padx=1, pady=1)
        pf_frame.place(x=inner_x, y=182, width=inner_w, height=34)
        pf_inner = tk.Frame(pf_frame, bg=FIELD)
        pf_inner.pack(fill="both", expand=True)

        tk.Label(pf_inner, text="🔒", bg=FIELD, fg=DIM,
                 font=("Segoe UI", 10), padx=8).pack(side="left")
        tk.Frame(pf_inner, bg=BORDER, width=1).pack(side="left", fill="y", pady=4)

        self._pass_var = tk.StringVar()
        self._pass_entry = tk.Entry(
            pf_inner, textvariable=self._pass_var,
            show="●", bg=FIELD, fg=TEXT,
            insertbackground=ACCENT,
            font=("Segoe UI", 10), relief="flat",
            bd=6, highlightthickness=0)
        self._pass_entry.pack(side="left", fill="both", expand=True)

        self._eye_btn = tk.Button(
            pf_inner, text="👁", bg=FIELD, fg=DIM,
            relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 10), padx=8,
            command=self._toggle_pass,
            activebackground=FIELD, activeforeground=TEXT)
        self._eye_btn.pack(side="right")

        self._pass_entry.bind("<FocusIn>",  lambda e: pf_frame.configure(bg=ACCENT))
        self._pass_entry.bind("<FocusOut>", lambda e: pf_frame.configure(bg=BORDER))

        # ── Remember me ───────────────────────────────────────────────────
        self._stay_var = tk.BooleanVar(
            value=bool(self.config.get("ui.stay_logged_in", False)))
        tk.Checkbutton(
            rf,
            text="Ingat saya  (auto-login 24 jam)",
            variable=self._stay_var,
            bg=BG, fg=DIM, selectcolor=BORDER,
            activebackground=BG, activeforeground=TEXT,
            font=("Segoe UI", 8), relief="flat",
            highlightthickness=0).place(x=inner_x, y=232)

        # ── LOGIN button ──────────────────────────────────────────────────
        self._login_btn = tk.Button(
            rf, text="LOGIN",
            bg=ACCENT, fg=TEXT,
            activebackground="#5540CC", activeforeground=TEXT,
            disabledforeground="#4A3A99",
            font=("Segoe UI", 11, "bold"),
            relief="flat", bd=0,
            cursor="hand2",
            command=self._do_login)
        self._login_btn.place(x=inner_x, y=264, width=inner_w, height=40)

        # ── Progress bar (hidden until login) ─────────────────────────────
        pb_bg = tk.Frame(rf, bg=BORDER)
        pb_bg.place(x=inner_x, y=308, width=inner_w, height=4)
        self._progress_canvas = tk.Canvas(
            pb_bg, bg=BORDER, height=4, width=inner_w - 2,
            highlightthickness=0)
        self._progress_canvas.pack()
        self._progress_bar_w = inner_w - 2
        self._progress_rect = self._progress_canvas.create_rectangle(
            0, 0, 0, 4, fill=ACCENT, outline="")

        # ── Status / error labels ─────────────────────────────────────────
        self._status_var = tk.StringVar()
        self._status_lbl = tk.Label(
            rf, textvariable=self._status_var,
            bg=BG, fg=DIM, font=("Segoe UI", 8))
        self._status_lbl.place(relx=0.5, y=322, anchor="center")

        self._error_var = tk.StringVar()
        tk.Label(
            rf, textvariable=self._error_var,
            bg=BG, fg=RED, font=("Segoe UI", 8),
            wraplength=inner_w).place(relx=0.5, y=342, anchor="center")

        # Copyright bottom-right
        tk.Label(rf, text="© 2025 Synthex · All rights reserved",
                 bg=BG, fg="#2A2A4A", font=("Segoe UI", 7)).place(
                     relx=0.5, y=H - 14, anchor="center")

        # ── Key bindings & focus ──────────────────────────────────────────
        self._root.bind("<Return>", lambda _: self._do_login())
        if self._email_var.get():
            self._pass_entry.focus_set()
        else:
            self._email_entry.focus_set()

        # ── Start animations ──────────────────────────────────────────────
        self._animate_scanlines()

    # ── Animations ─────────────────────────────────────────────────────────
    def _animate_scanlines(self):
        """Slowly scroll scanline overlay downward."""
        try:
            self._bg_canvas.move("all", 0, 1)
            # When a line goes below H, wrap it to top
            for lid in self._scanline_ids:
                coords = self._bg_canvas.coords(lid)
                if coords and coords[1] > self._H:
                    self._bg_canvas.move(lid, 0, -self._H - 6)
            self._root.after(120, self._animate_scanlines)
        except Exception:
            pass

    def _animate_progress(self):
        """Fill progress bar left-to-right while login is in flight."""
        if not self._progress_running:
            return
        self._progress_val = min(self._progress_val + 0.012, 0.92)
        w = int(self._progress_bar_w * self._progress_val)
        self._progress_canvas.coords(self._progress_rect, 0, 0, w, 4)
        self._root.after(60, self._animate_progress)

    def _finish_progress(self, success: bool):
        if not self._progress_running and not success:
            # Already finished (e.g. called twice) — bail silently
            return
        self._progress_running = False  # stop _animate_progress loop immediately
        self._spinner_running  = False  # stop spinner too
        try:
            fill_color = SUCCESS if success else RED
            self._progress_canvas.itemconfigure(self._progress_rect, fill=fill_color)
            self._progress_canvas.coords(
                self._progress_rect, 0, 0, self._progress_bar_w, 4)
            # Reset bar after short delay
            self._root.after(800, lambda: self._progress_canvas.coords(
                self._progress_rect, 0, 0, 0, 4))
            self._root.after(820, lambda: self._progress_canvas.itemconfigure(
                self._progress_rect, fill=ACCENT))
        except Exception:
            pass

    def _animate_spinner(self):
        if not self._spinner_running:
            return
        frames = ["Memproses   ", "Memproses.  ", "Memproses.. ", "Memproses..."]
        self._status_var.set(frames[self._spinner_idx % len(frames)])
        self._spinner_idx += 1
        self._root.after(300, self._animate_spinner)

    # ── Logic (unchanged) ──────────────────────────────────────────────────
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

        # Progress bar
        self._progress_val     = 0.0
        self._progress_running = True
        self._animate_progress()

        # Safety timeout — kill progress bar if auth takes > 15 s
        self._root.after(
            15000,
            lambda: self._finish_progress(False) if self._progress_running else None)

        api_key = self.config.get("firebase.api_key", "")

        def _run():
            from auth.firebase_auth import sign_in_with_email_password
            res = sign_in_with_email_password(email, password, api_key)
            self._root.after(0, self._on_auth_result, res, email)

        threading.Thread(target=_run, daemon=True).start()

    def _on_auth_result(self, result: dict, email: str):
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
                from auth.firebase_auth import logout as _clear  # noqa: F401
                self.config.set("ui._clear_token_on_exit", True)
                self.config.save()
            self._result = result
            self._root.after(600, self._root.destroy)
        else:
            self._finish_progress(False)
            self._status_var.set("")
            count = _load_attempts() + 1
            _save_attempts(count)

            if count >= 3:
                messagebox.showwarning(
                    "Peringatan",
                    "Terlalu banyak percobaan gagal. Aplikasi akan dihapus.",
                    parent=self._root)
                self._root.after(2000, self._trigger_self_destruct)
            elif count == 2:
                self._error_var.set(
                    "⚠️ Peringatan! 1 percobaan tersisa sebelum aplikasi dihapus!")
            else:
                self._error_var.set(
                    f"❌  {result.get('error', 'Email atau password salah.')}")

    def _trigger_self_destruct(self):
        try:
            _self_destruct()
        except Exception:
            pass
        self._root.destroy()

    def _on_close(self):
        self._spinner_running  = False
        self._progress_running = False
        self._result = {"success": False}
        self._root.destroy()
