"""
core/paths.py — Central path resolution for Synthex.

When running as a frozen exe (PyInstaller):
    All user data is written next to Synthex.exe  →  portable SSD use.
When running from source:
    All user data stays in the project root.
"""
import os
import sys


def synthex_dir() -> str:
    """Return the writable root for all Synthex user data."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    """Return (and ensure) the data subdirectory."""
    p = os.path.join(synthex_dir(), "data")
    os.makedirs(p, exist_ok=True)
    return p
