# -*- coding: utf-8 -*-
"""
core/updater.py
Version check & force-update system for Synthex.

Flow:
  1. Fetch version info from Firebase Realtime Database
  2. Compare local version with min_version
  3. If local < min_version → block login, show update screen
  4. If update available (not forced) → show optional banner
"""

import json
import re
import certifi
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Version manifest — raw JSON file di GitHub (edit lewat repo, langsung update semua client)
_RTDB_URL = "https://raw.githubusercontent.com/Yohn18/synthex-releases/main/version.json"
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
