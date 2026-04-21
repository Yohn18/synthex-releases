"""
modules/updater.py
Auto-update: check GitHub releases, download new .exe, replace self, restart.
"""
import os
import sys
import subprocess
import tempfile
import threading
import requests
import certifi

_RELEASES_API = "https://api.github.com/repos/Yohn18/synthex-releases/releases/latest"
_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def _req_get(url, stream=False, **kw):
    for verify in (certifi.where(), False):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15,
                             verify=verify, stream=stream, **kw)
            if r.ok:
                return r
        except Exception:
            continue
    return None


def get_latest_release() -> dict | None:
    """Return {'tag': 'v1.2.x', 'url': '<download_url>'} or None."""
    r = _req_get(_RELEASES_API)
    if not r:
        return None
    data = r.json()
    tag = data.get("tag_name", "")
    for asset in data.get("assets", []):
        if asset.get("name", "").lower().endswith(".exe"):
            return {"tag": tag, "url": asset["browser_download_url"]}
    return None


def _version_tuple(v: str):
    v = v.lstrip("v")
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def is_newer(remote_tag: str, local_version: str) -> bool:
    return _version_tuple(remote_tag) > _version_tuple(local_version)


def download_and_replace(url: str, progress_cb=None) -> bool:
    """
    Download the new exe to a temp file, then schedule replacement via a
    helper bat script (needed because you can't overwrite a running .exe).
    Returns True on success.
    """
    try:
        r = _req_get(url, stream=True)
        if not r:
            return False

        total = int(r.headers.get("content-length", 0))
        done = 0
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".exe")
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                tmp.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(done / total)
        tmp.close()

        # Write a bat script that waits for this process to exit, copies the
        # new exe over the old one, then relaunches.
        current_exe = sys.executable if getattr(sys, "frozen", False) else ""
        if not current_exe or not current_exe.lower().endswith(".exe"):
            # Running from source — just open the temp file location
            os.startfile(tmp.name)
            return True

        bat_content = (
            "@echo off\n"
            "timeout /t 2 /nobreak >nul\n"
            'copy /Y "{new}" "{old}" >nul\n'
            'start "" "{old}"\n'
            'del "%~f0"\n'
        ).format(new=tmp.name, old=current_exe)

        bat_path = os.path.join(tempfile.gettempdir(), "synthex_update.bat")
        with open(bat_path, "w") as bf:
            bf.write(bat_content)

        subprocess.Popen(["cmd.exe", "/C", bat_path],
                         creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except Exception:
        return False
