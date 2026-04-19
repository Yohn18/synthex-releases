# -*- coding: utf-8 -*-
"""
core/updater.py
Version check & auto-update system for Synthex.

Flow:
  1. Fetch version info from GitHub Gist
  2. Compare local version with min_version
  3. If local < min_version → block login, show update screen with auto-download
  4. If update available (not forced) → show optional banner
"""

import json
import os
import re
import sys
import certifi
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Version manifest — GitHub Gist publik (repo tetap private, update cukup edit gist ini)
# Gist ID: 3920fa0dd0e4c2a400c69940ad614d3b
_RTDB_URL = "https://gist.githubusercontent.com/Yohn18/3920fa0dd0e4c2a400c69940ad614d3b/raw/version.json"
_TIMEOUT  = 6  # seconds


def _http_get(url: str, timeout: int = _TIMEOUT) -> dict | None:
    """GET with SSL fallback. Returns parsed JSON or None."""
    for verify in (certifi.where(), False):
        try:
            r = requests.get(url, timeout=timeout, verify=verify)
            if r.ok:
                return r.json()
        except Exception:
            continue
    return None


def _parse_version(v: str) -> tuple[int, ...]:
    """'1.2.3' → (1, 2, 3). Returns (0,) on error."""
    try:
        return tuple(int(x) for x in re.findall(r"\d+", str(v)))
    except Exception:
        return (0,)


def check_version(local_version: str) -> dict:
    """
    Check local_version against server. Also checks maintenance mode.

    Returns dict:
      {
        "ok":               bool,   # True = allowed to run
        "force_update":     bool,   # True = must update before login
        "maintenance":      bool,   # True = app in maintenance mode
        "maintenance_msg":  str,    # maintenance message from server
        "has_update":       bool,   # True = newer version available
        "latest":           str,    # latest version string
        "min_version":      str,    # minimum required version
        "download_url":     str,    # URL to download latest exe
        "changelog":        str,    # what's new
        "error":            str,    # error message if check failed
      }
    """
    result = {
        "ok":               True,
        "force_update":     False,
        "maintenance":      False,
        "maintenance_msg":  "",
        "has_update":       False,
        "latest":           local_version,
        "min_version":      local_version,
        "download_url":     "",
        "changelog":        "",
        "error":            "",
    }

    data = _http_get(_RTDB_URL)
    if data is None:
        result["error"] = "Tidak bisa cek versi (offline). Melanjutkan..."
        return result

    # ── Maintenance check ─────────────────────────────────────────────────
    if data.get("maintenance", False):
        result["ok"]              = False
        result["maintenance"]     = True
        result["maintenance_msg"] = data.get(
            "maintenance_msg",
            "Aplikasi sedang dalam maintenance. Hubungi 082228885859 untuk info lebih lanjut.")
        return result

    # ── Version check ─────────────────────────────────────────────────────
    latest_str = data.get("latest_version", local_version)
    min_str    = data.get("min_version",    local_version)
    download   = data.get("download_url",   "")
    changelog  = data.get("changelog",      "")

    local_t  = _parse_version(local_version)
    latest_t = _parse_version(latest_str)
    min_t    = _parse_version(min_str)

    result["latest"]       = latest_str
    result["min_version"]  = min_str
    result["download_url"] = download
    result["changelog"]    = changelog
    result["has_update"]   = latest_t > local_t

    if local_t < min_t:
        result["ok"]           = False
        result["force_update"] = True

    return result


def auto_download_update(download_url: str, on_progress=None) -> tuple[bool, str]:
    """
    Download .exe baru ke folder temp, lalu jalankan bat script yang:
      1. Tunggu proses Synthex lama tutup
      2. Ganti Synthex.exe lama dengan yang baru
      3. Jalankan Synthex.exe baru

    Args:
        download_url:  URL ke file .exe terbaru
        on_progress:   callback(pct: int, msg: str) untuk update progress bar

    Returns:
        (True, "") jika berhasil dijadwalkan
        (False, pesan_error) jika gagal
    """
    try:
        import tempfile, subprocess

        if on_progress:
            on_progress(0, "Menghubungi server...")

        # Tentukan path exe yang sedang berjalan
        if getattr(sys, "frozen", False):
            current_exe = sys.executable
        else:
            current_exe = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "dist", "Synthex.exe")

        tmp_dir  = tempfile.gettempdir()
        new_exe  = os.path.join(tmp_dir, "Synthex_new.exe")
        bat_path = os.path.join(tmp_dir, "synthex_update.bat")

        # Download dengan progress
        resp = requests.get(download_url, stream=True, timeout=60, verify=certifi.where())
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(new_exe, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total and on_progress:
                        pct = int(downloaded / total * 90)
                        on_progress(pct, "Mengunduh... {}%".format(pct))

        if on_progress:
            on_progress(92, "Menyiapkan update...")

        # Buat bat script yang replace exe setelah proses selesai
        bat_content = (
            "@echo off\n"
            "timeout /t 2 /nobreak >nul\n"
            ":wait\n"
            "tasklist /FI \"IMAGENAME eq Synthex.exe\" 2>nul | find /I \"Synthex.exe\" >nul\n"
            "if not errorlevel 1 (\n"
            "    timeout /t 1 /nobreak >nul\n"
            "    goto wait\n"
            ")\n"
            "copy /Y \"{new}\" \"{cur}\"\n"
            "start \"\" \"{cur}\"\n"
            "del \"%~f0\"\n"
        ).format(new=new_exe, cur=current_exe)

        with open(bat_path, "w") as f:
            f.write(bat_content)

        if on_progress:
            on_progress(98, "Memulai update...")

        # Jalankan bat di background, lalu app akan tutup sendiri
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )

        if on_progress:
            on_progress(100, "Selesai! Synthex akan restart otomatis.")

        return True, ""

    except requests.Timeout:
        return False, "Timeout saat download — coba lagi"
    except Exception as e:
        return False, str(e)[:80]
