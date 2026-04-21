# -*- coding: utf-8 -*-
"""
modules/rekening.py - Rekening & e-wallet account name checker for Synthex.
Uses APIV3: https://apivalidasi.my.id/api/v3/validate
"""

import json
import os
import time
import threading
import requests

# ── Rate limiter ───────────────────────────────────────────────────────────────
_rl_lock  = threading.Lock()
_rl_last  = [0.0]
_rl_delay = 1.3

def _rate_wait():
    with _rl_lock:
        now = time.monotonic()
        gap = _rl_last[0] + _rl_delay - now
        _rl_last[0] = now + max(gap, 0)
    if gap > 0:
        time.sleep(gap)

# ── Config ────────────────────────────────────────────────────────────────────
_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

def _load_api_key() -> str:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return (cfg.get("rekening_api_key")
                or cfg.get("settings", {}).get("rekening_api_key", "")
                or "")
    except Exception:
        return ""

# ── Bank code mapping ─────────────────────────────────────────────────────────
BANK_CODES = {
    "BCA":      "014",
    "BRI":      "002",
    "BNI":      "009",
    "MANDIRI":  "008",
    "BSI":      "451",
    "BTN":      "200",
    "CIMB":     "022",
    "PERMATA":  "013",
    "DANAMON":  "011",
    "OCBC":     "028",
    "BLUEBCA":  "501",
    "TMRW":     "023",
    "JENIUS":   "213",
    "SEABANK":  "535",
    "JAGO":     "542",
    "LINE":     "484",
    "BJB":      "110",
    "MUAMALAT": "147",
    "PANIN":    "019",
    "MEGA":     "426",
    "BNP":      "057",
    "SINARMAS": "153",
    "MAYBANK":  "016",
    "BUKOPIN":  "441",
}

# ── E-wallet providers ────────────────────────────────────────────────────────
EWALLETS = {"DANA", "OVO", "GOPAY", "SHOPEEPAY", "LINKAJA"}

# ── API base — fetched from Firebase so master can change remotely ────────────
_BASE_DEFAULT = "https://app.apivalidasi.my.id/api/v3/validate"

def _get_base() -> str:
    try:
        from auth.firebase_auth import get_valid_token
        from modules.master_config import get_rekening_url
        tok = get_valid_token()
        if tok:
            return get_rekening_url(tok)
    except Exception:
        pass
    return _BASE_DEFAULT


def check_rekening(provider: str, nomor: str, api_key: str = None) -> dict:
    """
    Check account name for a bank or e-wallet number.

    Returns:
        {"provider": str, "nomor": str, "name": str, "status": str}
    """
    provider = provider.strip().upper()
    nomor    = nomor.strip()

    if api_key is None:
        api_key = _load_api_key()

    result = {"provider": provider, "nomor": nomor, "name": "-", "status": "Gagal"}

    if not nomor or len(nomor) < 5:
        result["status"] = "Nomor tidak valid"
        return result

    try:
        _base = _get_base()
        if provider in EWALLETS:
            url = "{}?type=ewallet&code={}&accountNumber={}".format(
                _base, provider.lower(), nomor)
        else:
            code = BANK_CODES.get(provider, provider.lower())
            url = "{}?type=bank&code={}&accountNumber={}".format(
                _base, code, nomor)
        if api_key:
            url += "&api_key={}".format(api_key)

        _rate_wait()
        resp = None
        for attempt in range(3):
            resp = requests.get(url, timeout=12)
            if resp.status_code == 429:
                wait = min(int(resp.headers.get("Retry-After", str(3 * (attempt + 1)))), 20)
                time.sleep(wait)
                _rate_wait()
                continue
            break

        if resp is None:
            result["status"] = "Tidak ada respons"
            return result

        if resp.status_code == 401:
            result["status"] = "API key tidak valid atau habis masa berlaku"
            return result
        if resp.status_code == 403:
            result["status"] = "Layanan cek rekening sedang tidak tersedia"
            return result
        if resp.status_code not in (200, 400):
            result["status"] = "Error: HTTP {}".format(resp.status_code)
            return result

        # Hosting suspended — server balik HTML bukan JSON
        ct = resp.headers.get("Content-Type", "")
        if "text/html" in ct:
            result["status"] = "Layanan cek rekening sedang tidak tersedia"
            return result

        body = resp.json()

        if body.get("status") is True or body.get("status") == "success":
            data = body.get("data") or {}
            name = (data.get("account_name") or data.get("accountName")
                    or data.get("name") or data.get("nama") or "-")
            result["name"]   = name
            result["status"] = "Valid" if name and name != "-" else "Tidak Ditemukan"
        else:
            result["status"] = "Tidak Ditemukan"

    except requests.Timeout:
        result["status"] = "Timeout — server sedang down, coba lagi nanti"
    except requests.ConnectionError:
        result["status"] = "Tidak ada koneksi — periksa WiFi/internet"
    except Exception as e:
        result["status"] = "Error: {}".format(str(e)[:25])

    return result


def check_rekening_bulk(entries: list, api_key: str = None) -> list:
    """
    Check multiple entries.

    Args:
        entries: list of (provider, nomor) tuples or "PROVIDER NOMOR" / "PROVIDER|NOMOR" strings
    """
    if api_key is None:
        api_key = _load_api_key()

    results = []
    for entry in entries:
        if isinstance(entry, str):
            raw   = entry.replace("|", " ").replace(",", " ")
            parts = raw.strip().split(None, 1)
            if len(parts) == 2:
                provider, nomor = parts[0].strip(), parts[1].strip()
            else:
                provider, nomor = "BCA", parts[0].strip()
        else:
            provider, nomor = str(entry[0]), str(entry[1])
        results.append(check_rekening(provider, nomor, api_key=api_key))
    return results
