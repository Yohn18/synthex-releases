"""
core/logger.py - Centralized logging setup for Synthex.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

import sys as _sys
if getattr(_sys, 'frozen', False):
    # Running as PyInstaller exe — write logs next to the exe
    _BASE = os.path.dirname(_sys.executable)
else:
    _BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR  = os.path.join(_BASE, "logs")
LOG_FILE = os.path.join(LOG_DIR, "synthex.log")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

os.makedirs(LOG_DIR, exist_ok=True)

_handlers_configured = False


def _configure_root(level: str = "INFO"):
    global _handlers_configured
    if _handlers_configured:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    # Prevent UnicodeEncodeError on Windows cp1252 console
    if hasattr(console.stream, 'reconfigure'):
        try:
            console.stream.reconfigure(errors='replace')
        except Exception:
            pass
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
        errors="replace"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    _handlers_configured = True


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    _configure_root(level)
    return logging.getLogger(name)
