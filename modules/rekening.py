# -*- coding: utf-8 -*-
"""
modules/rekening.py - Rekening & e-wallet account name checker for Synthex.
Uses APIV3: https://apiv3.my.id/api/v3/validate
"""

import json
import os
import time
import threading
import requests

# ── Rate limiter ───────────────────────────────────────────────────────────────
# Prevents HTTP 429 (Too Many Requests) by enforcing a minimum delay between calls.
_rl_lock  = threading.Lock()
_rl_last  = [0.0]
_rl_delay = 1.3   # seconds between consecutive API calls

def _rate_wait():
    """Block the calling thread until it's safe to fire the next request."""
    with _rl_lock:
        now  = time.monotonic()
        gap  = _rl_last[0] + _rl_delay - now
        if gap > 0:
            time.sleep(gap)
        _rl_last[0] = time.monotonic()

# ── Config ────────────────────────────────────────────────────────────────────
_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

def _load_api_key() -> str:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # Cari di root config dulu, fallback ke cfg["settings"]
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

# ── API base ──────────────────────────────────────────────────────────────────
_BASE = "https://apivalidasi.my.id/api/v3/validate"


def check_rekening(provider: str, nomor: str, api_key: str = None) -> dict:
    """
    Check account name for a bank or e-wallet number.

    Args:
        provider: e.g. "BCA", "DANA", "OVO"
        nomor:    account / phone number
        api_key:  override API key (loaded from config.json if not provided)

    Returns:
        {"provider": str, "nomor": str, "name": str, "status": str}
    """
    provider = provider.strip().upper()
    nomor    = nomor.strip()

    if api_key is None:
        api_key = _load_api_key()

    result = {"provider": provider, "nomor": nomor, "name": "-", "status": "Gagal"}

    # ── Input validation ──────────────────────────────────────────────────────
    if not nomor or len(nomor) < 5:
        result["status"] = "Nomor tidak valid"
        return result

    try:
        # api_key opsional — tanpa key tetap jalan (rate limit server),
        # dengan key = unlimited
        if provider in EWALLETS:
            url = "{}?type=ewallet&code={}&accountNumber={}".format(
                _BASE, provider.lower(), nomor)
        else:
            code = BANK_CODES.get(provider, provider.lower())
            url = "{}?type=bank&code={}&accountNumber={}".format(
                _BASE, code, nomor)
        if api_key:
            url += "&api_key={}".format(api_key)

        # ── Rate-limited request with 429 retry ───────────────────────────────
        _rate_wait()
        resp = None
        for _attempt in range(3):
            resp = requests.get(url, timeout=12)
            if resp.status_code == 429:
                # Honour Retry-After if present, otherwise back off progressively
                retry_after = int(resp.headers.get("Retry-After", str(3 * (_attempt + 1))))
                wait_sec    = min(retry_after, 20)
                time.sleep(wait_sec)
                _rate_wait()
                continue
            break

        if resp is None:
            result["status"] = "Tidak ada respons"
            return result

        # API pakai HTTP 200 (berhasil) dan HTTP 400 (tidak ditemukan) —
        # keduanya punya JSON body yang valid, bukan error teknis
        if resp.status_code not in (200, 400):
            result["status"] = "Error: HTTP {}".format(resp.status_code)
            return result

        body = resp.json()

        # {"status": true/false, "data": {"account_name": "..."}}
        if body.get("status") is True or body.get("status") == "success":
            data = body.get("data") or {}
            name = (
                data.get("account_name")
                or data.get("accountName")
                or data.get("name")
                or data.get("nama")
                or "-"
            )
            result["name"]   = name
            result["status"] = "Valid" if name and name != "-" else "Tidak Ditemukan"
        else:
            # 400 atau status false = nomor tidak ditemukan
            result["status"] = "Tidak Ditemukan"

    except requests.Timeout:
        result["status"] = "Timeout — cek koneksi internet, coba lagi"
    except requests.ConnectionError:
        result["status"] = "Tidak ada koneksi — periksa WiFi/internet"
    except Exception as e:
        result["status"] = "Error: {} — coba lagi".format(str(e)[:25])

    return result


def check_rekening_bulk(entries: list, api_key: str = None) -> list:
    """
    Check multiple entries.

    Args:
        entries: list of (provider, nomor) tuples or "PROVIDER NOMOR" / "PROVIDER|NOMOR" strings
        api_key: optional API key override

    Returns:
        list of result dicts
    """
    if api_key is None:
        api_key = _load_api_key()

    results = []
    for entry in entries:
        if isinstance(entry, str):
            # Support "PROVIDER NOMOR", "PROVIDER|NOMOR", "PROVIDER,NOMOR"
            raw = entry.replace("|", " ").replace(",", " ")
            parts = raw.strip().split(None, 1)
            if len(parts) == 2:
                provider, nomor = parts[0].strip(), parts[1].strip()
            else:
                provider, nomor = "BCA", parts[0].strip()
        else:
            provider, nomor = str(entry[0]), str(entry[1])
        results.append(check_rekening(provider, nomor, api_key=api_key))
    return results
