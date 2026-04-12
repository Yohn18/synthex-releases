import warnings
warnings.filterwarnings("ignore")
import os
os.environ['PYTHONWARNINGS'] = 'ignore'

# Suppress PyInstaller temp directory warning
import sys
if hasattr(sys, '_MEIPASS'):
    import logging
    logging.disable(logging.CRITICAL)

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


def handle_shutdown(sig, frame):
    logger.info("Shutdown signal received.")
    sys.exit(0)


if __name__ == "__main__":
    logger.info("Starting Synthex Automation Platform...")

    config = Config("config.json")

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

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
    # If stay_logged_in is off, delete the saved token so next launch requires login
    if config.get("ui._clear_token_on_exit", False):
        from auth.firebase_auth import logout as _clear
        _clear()
        config.set("ui._clear_token_on_exit", False)
        config.save()
