"""
core/paths.py — Central path resolution for Synthex.

When running as a frozen exe (PyInstaller):
    All user data is written next to Synthex.exe  →  portable SSD use.
When running from source:
    Config/tokens stay in AppData\\Synthex (same as before, API keys preserved).
    Data files (json, db, etc.) stay in project root/data.
"""
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def synthex_dir() -> str:
    """Return the writable root for config and auth files.
    Frozen: folder containing Synthex.exe (portable SSD).
    Source: AppData\\Synthex (preserves stored API keys and tokens).
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Synthex")


def data_dir() -> str:
    """Return (and ensure) the data subdirectory for runtime files.
    Frozen: exe_dir/data.
    Source: project_root/data  (same as the original behavior).
    """
    if getattr(sys, 'frozen', False):
        p = os.path.join(os.path.dirname(sys.executable), "data")
    else:
        p = os.path.join(_PROJECT_ROOT, "data")
    os.makedirs(p, exist_ok=True)
    return p
