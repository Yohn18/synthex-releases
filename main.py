import warnings
warnings.filterwarnings("ignore")
import os
os.environ['PYTHONWARNINGS'] = 'ignore'

import sys

# ── DPI awareness: must be set before any GUI/mouse/UIA init ─────────────────
# Ensures pynput (recording), pyautogui (playback), UIA, and ctypes all share
# the same coordinate space (physical pixels).  Without this, on HiDPI displays
# the exe might run as DPI-unaware while hooks report physical coords → offset.
import ctypes as _ctypes
try:
    _ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor DPI aware v1
except Exception:
    try:
        _ctypes.windll.user32.SetProcessDPIAware()    # legacy fallback
    except Exception:
        pass

"""
Synthex - Automation Platform by Yohn18
Entry point: login → load modules → launch dashboard.
"""

import signal

# Fix stdout/stderr for frozen exe (PyInstaller --windowed sets them to None)
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# Only reconfigure encoding when running from source (not frozen)
if not getattr(sys, 'frozen', False):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
from core.config import Config
from core.logger import get_logger

logger = get_logger("main")

# ── Global crash hook: write all unhandled exceptions to log ─────────────────
import threading as _threading

def _excepthook(exc_type, exc_value, exc_tb):
    import traceback as _tb
    logger.critical("UNHANDLED EXCEPTION: %s", "".join(
        _tb.format_exception(exc_type, exc_value, exc_tb)))

def _thread_excepthook(args):
    import traceback as _tb
    logger.critical("UNHANDLED THREAD EXCEPTION in %s: %s",
        getattr(args.thread, 'name', '?'),
        "".join(_tb.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))

sys.excepthook = _excepthook
_threading.excepthook = _thread_excepthook


def handle_shutdown(sig, frame):
    logger.info("Shutdown signal received.")
    sys.exit(0)


if __name__ == "__main__":
    logger.info("Starting Synthex Automation Platform...")

    config = Config("config.json")

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # ── 0. Version check ──────────────────────────────────────────────────────
    local_ver = config.get("app.version", "1.0.0")
    try:
        from core.updater import check_version
        ver = check_version(local_ver)
        if ver["error"]:
            logger.warning(ver["error"])
        if not ver["ok"]:
            import tkinter as tk
            import webbrowser
            _is_maint = ver.get("maintenance", False)
            _wa_url   = "https://wa.me/6282228885859"
            _title    = "Maintenance" if _is_maint else "Update Diperlukan"
            _hdr_col  = "#E67E22" if _is_maint else "#6C4AFF"
            _h        = 300 if _is_maint else 260
            _r = tk.Tk()
            _r.title(_title)
            _r.configure(bg="#0A0A0F")
            _r.resizable(False, False)
            _r.update_idletasks()
            _sw = _r.winfo_screenwidth()
            _sh = _r.winfo_screenheight()
            _r.geometry("460x{}+{}+{}".format(
                _h, (_sw - 460) // 2, (_sh - _h) // 2))
            # Header
            _hdr = tk.Frame(_r, bg=_hdr_col, height=44)
            _hdr.pack(fill="x")
            _hdr.pack_propagate(False)
            _icon = "  🔧  " if _is_maint else "  ⚡  "
            tk.Label(_hdr, text=_icon + _title, bg=_hdr_col, fg="white",
                     font=("Segoe UI", 12, "bold")).pack(side="left", pady=10)
            # Body
            _body = tk.Frame(_r, bg="#0A0A0F", padx=28, pady=18)
            _body.pack(fill="both", expand=True)
            if _is_maint:
                tk.Label(_body,
                         text="Aplikasi sedang dalam maintenance.",
                         bg="#0A0A0F", fg="#C8C8E8",
                         font=("Segoe UI", 11, "bold")).pack(anchor="w")
                _msg = ver.get("maintenance_msg", "")
                if _msg:
                    tk.Label(_body, text=_msg,
                             bg="#0A0A0F", fg="#6A6A8A",
                             font=("Segoe UI", 9),
                             wraplength=400, justify="left").pack(
                                 anchor="w", pady=(8, 0))
                tk.Label(_body,
                         text="Hubungi admin untuk info lebih lanjut:",
                         bg="#0A0A0F", fg="#6A6A8A",
                         font=("Segoe UI", 9)).pack(anchor="w", pady=(12, 0))
                tk.Label(_body, text="WhatsApp: +62 82228885859",
                         bg="#0A0A0F", fg="#00D4AA",
                         font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 0))
                _btn_row = tk.Frame(_body, bg="#0A0A0F")
                _btn_row.pack(anchor="w", pady=(16, 0))
                tk.Button(_btn_row, text="💬 Chat WhatsApp",
                          bg="#25D366", fg="white",
                          font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                          padx=16, pady=8, cursor="hand2",
                          command=lambda: webbrowser.open(_wa_url)
                          ).pack(side="left", padx=(0, 10))
                tk.Button(_btn_row, text="Tutup",
                          bg="#2A2A4A", fg="#C8C8E8",
                          font=("Segoe UI", 9), relief="flat", bd=0,
                          padx=12, pady=8, cursor="hand2",
                          command=_r.destroy).pack(side="left")
            else:
                tk.Label(_body,
                         text="Versi kamu ({}) sudah tidak didukung.".format(local_ver),
                         bg="#0A0A0F", fg="#C8C8E8",
                         font=("Segoe UI", 11, "bold")).pack(anchor="w")
                tk.Label(_body,
                         text="Versi minimum yang diperlukan: {}".format(ver["min_version"]),
                         bg="#0A0A0F", fg="#6A6A8A",
                         font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
                if ver.get("changelog"):
                    tk.Label(_body, text="Yang baru: " + ver["changelog"],
                             bg="#0A0A0F", fg="#00D4AA",
                             font=("Segoe UI", 9),
                             wraplength=400, justify="left").pack(
                                 anchor="w", pady=(8, 0))
                tk.Label(_body,
                         text="Butuh bantuan? Hubungi: +62 82228885859",
                         bg="#0A0A0F", fg="#6A6A8A",
                         font=("Segoe UI", 8)).pack(anchor="w", pady=(8, 0))
                _btn_row = tk.Frame(_body, bg="#0A0A0F")
                _btn_row.pack(anchor="w", pady=(12, 0))
                if ver.get("download_url"):
                    tk.Button(_btn_row, text="Download Versi Terbaru",
                              bg="#6C4AFF", fg="white",
                              font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                              padx=16, pady=8, cursor="hand2",
                              command=lambda: webbrowser.open(ver["download_url"])
                              ).pack(side="left", padx=(0, 10))
                tk.Button(_btn_row, text="💬 Chat WhatsApp",
                          bg="#25D366", fg="white",
                          font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                          padx=12, pady=8, cursor="hand2",
                          command=lambda: webbrowser.open(_wa_url)
                          ).pack(side="left", padx=(0, 10))
                tk.Button(_btn_row, text="Tutup",
                          bg="#2A2A4A", fg="#C8C8E8",
                          font=("Segoe UI", 9), relief="flat", bd=0,
                          padx=12, pady=8, cursor="hand2",
                          command=_r.destroy).pack(side="left")
            _r.mainloop()
            sys.exit(0)
        elif ver["has_update"]:
            logger.info("Update tersedia: {} -> {}".format(
                local_ver, ver["latest"]))
    except Exception as _e:
        logger.warning("Version check error: {}".format(_e))

    # ── 1. Try to resume a saved session ─────────────────────────────────────
    auth_result = None
    if config.get("ui.stay_logged_in", False):
        from auth.firebase_auth import load_saved_session
        auth_result = load_saved_session()
        if auth_result:
            logger.info(f"Resuming session for {auth_result.get('email')}")

    # ── 2. Show login window if no valid session ──────────────────────────────
    if not auth_result:
        from ui.login import LoginWindow
        auth_result = LoginWindow(config).show()
        if not auth_result.get("success"):
            logger.info("Login cancelled — exiting.")
            sys.exit(0)

    logger.info(f"Authenticated as: {auth_result.get('email')}")

    # ── 3. Create engine, pass auth info, start (shows loading → dashboard) ──
    from core.engine import Engine
    engine = Engine(config)
    engine.app.set_auth(auth_result["email"], auth_result.get("token", ""))

    try:
        engine.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

    # ── 4. Post-exit cleanup ──────────────────────────────────────────────────
    # Only clear token if user explicitly chose NOT to stay logged in
    stay = config.get("ui.stay_logged_in", False)
    if not stay and config.get("ui._clear_token_on_exit", False):
        from auth.firebase_auth import logout as _clear
        _clear()
    # Always reset the flag; token is kept when stay_logged_in is True
    config.set("ui._clear_token_on_exit", False)
    config.save()
