# -*- coding: utf-8 -*-
"""
modules/sheets/connector.py
Google Sheets connector for Synthex.
Supports multiple service-account credentials (one per "account").
Active account is stored in config; credentials stored in auth/google_creds/.
"""

import json
import os
import re

_ROOT       = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CREDS_DIR  = os.path.join(_ROOT, "auth", "google_creds")
_LEGACY_PATH = os.path.join(_ROOT, "credentials.json")   # backwards compat
_ACTIVE_FILE = os.path.join(_CREDS_DIR, "_active.txt")   # stores active account name

os.makedirs(_CREDS_DIR, exist_ok=True)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_worksheet_cache: dict = {}
_client = None
_client_account: str | None = None   # which account _client was built for


# ── Account management ────────────────────────────────────────────────────────

def list_accounts() -> list[dict]:
    """Return list of dicts: [{name, path, email, active}]"""
    accounts = []
    active = get_active_account_name()

    # Legacy credentials.json → treat as "default" if no other accounts exist
    legacy_files = [f for f in os.listdir(_CREDS_DIR) if f.endswith(".json")]
    if not legacy_files and os.path.isfile(_LEGACY_PATH):
        try:
            with open(_LEGACY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            email = data.get("client_email", "")
            return [{"name": "default", "path": _LEGACY_PATH,
                     "email": email, "active": True}]
        except Exception:
            pass

    for fname in sorted(legacy_files):
        name = fname[:-5]   # strip .json
        path = os.path.join(_CREDS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            email = data.get("client_email", "")
        except Exception:
            email = "(invalid)"
        accounts.append({
            "name":   name,
            "path":   path,
            "email":  email,
            "active": name == active,
        })
    return accounts


def get_active_account_name() -> str | None:
    try:
        with open(_ACTIVE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except Exception:
        return None


def get_active_creds_path() -> str | None:
    """Return path to the active credentials file, or None."""
    name = get_active_account_name()
    if name:
        p = os.path.join(_CREDS_DIR, name + ".json")
        if os.path.isfile(p):
            return p
    # Fallback: any account in dir
    files = [f for f in os.listdir(_CREDS_DIR) if f.endswith(".json")]
    if files:
        p = os.path.join(_CREDS_DIR, sorted(files)[0])
        return p
    # Final fallback: legacy
    if os.path.isfile(_LEGACY_PATH):
        return _LEGACY_PATH
    return None


def set_active_account(name: str) -> bool:
    """Set the active account by name. Returns True on success."""
    path = os.path.join(_CREDS_DIR, name + ".json")
    if not os.path.isfile(path):
        return False
    try:
        with open(_ACTIVE_FILE, "w", encoding="utf-8") as f:
            f.write(name)
        reset_client()
        return True
    except Exception:
        return False


def add_account(name: str, src_path: str) -> tuple[bool, str]:
    """Copy a credentials JSON file as a named account.
    Returns (ok, error_or_service_account_email).
    """
    name = name.strip().replace(" ", "_").lower()
    if not name:
        return False, "Account name cannot be empty."
    try:
        with open(src_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "client_email" not in data or "private_key" not in data:
            return False, "File is not a valid Google service account key."
        email = data["client_email"]
        dest = os.path.join(_CREDS_DIR, name + ".json")
        import shutil
        shutil.copy2(src_path, dest)
        # If no active account set yet, make this one active
        if not get_active_account_name():
            set_active_account(name)
        reset_client()
        return True, email
    except json.JSONDecodeError:
        return False, "File is not valid JSON."
    except Exception as e:
        return False, str(e)


def remove_account(name: str) -> bool:
    path = os.path.join(_CREDS_DIR, name + ".json")
    try:
        os.remove(path)
        # If we removed the active one, switch to another
        if get_active_account_name() == name:
            files = [f[:-5] for f in os.listdir(_CREDS_DIR) if f.endswith(".json")]
            if files:
                set_active_account(files[0])
            else:
                try:
                    os.remove(_ACTIVE_FILE)
                except Exception:
                    pass
        reset_client()
        return True
    except Exception:
        return False


def get_service_account_email() -> str:
    path = get_active_creds_path()
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("client_email", "")
    except Exception:
        return ""


def credentials_exist() -> bool:
    return get_active_creds_path() is not None


# ── gspread client ────────────────────────────────────────────────────────────

def _get_client():
    global _client, _client_account
    active = get_active_account_name()
    if _client is not None and _client_account == active:
        return _client, None

    creds_path = get_active_creds_path()
    if not creds_path:
        return None, (
            "Google Sheets tidak terhubung. "
            "Buka Settings -> Google Accounts untuk menambah akun."
        )
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_file(creds_path, scopes=_SCOPES)
        _client = gspread.authorize(creds)
        _client_account = active
        return _client, None
    except ImportError:
        return None, "Package tidak terinstall. Jalankan: pip install gspread google-auth"
    except Exception as e:
        return None, "Gagal konek ke Google: {}".format(str(e))


def reset_client():
    global _client, _client_account
    _client = None
    _client_account = None
    _worksheet_cache.clear()


# ── Sheet operations ──────────────────────────────────────────────────────────

def extract_sheet_id(url_or_id: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)
    if re.match(r"^[a-zA-Z0-9_-]{10,}$", url_or_id.strip()):
        return url_or_id.strip()
    return ""


def get_worksheets(sheet_id: str) -> tuple[list, str | None]:
    client, err = _get_client()
    if err:
        return [], err
    try:
        wb    = client.open_by_key(sheet_id)
        names = [ws.title for ws in wb.worksheets()]
        return names, None
    except Exception as e:
        msg = str(e)
        if "PERMISSION_DENIED" in msg or "403" in msg:
            email = get_service_account_email()
            return [], (
                "Akses ditolak. Share sheet ini ke:\n{}\n"
                "(beri akses Editor)".format(email or "service account email")
            )
        if "404" in msg or "not found" in msg.lower():
            return [], "Sheet tidak ditemukan. Cek URL sudah benar."
        return [], "Tidak bisa buka sheet: {}".format(msg)


def connect_sheet(url_or_id: str, worksheet_name: str = "Sheet1"):
    client, err = _get_client()
    if err:
        return None, err
    sheet_id = extract_sheet_id(url_or_id)
    if not sheet_id:
        return None, "Tidak ada Sheet ID yang valid di: {}".format(url_or_id)
    try:
        wb = client.open_by_key(sheet_id)
        ws = wb.worksheet(worksheet_name)
        return ws, None
    except Exception as e:
        msg = str(e)
        if "PERMISSION_DENIED" in msg or "403" in msg:
            email = get_service_account_email()
            return None, (
                "Akses ditolak. Share sheet ini ke:\n{}\n"
                "(beri akses Editor)".format(email or "service account email")
            )
        if "not found" in msg.lower() or "404" in msg:
            return None, "Worksheet '{}' tidak ditemukan.".format(worksheet_name)
        return None, "Tidak bisa konek ke sheet: {}".format(msg)


def _get_ws(sheets_list, sheet_name):
    entry = next((s for s in sheets_list if s.get("name") == sheet_name), None)
    if not entry:
        return None, "Sheet '{}' tidak ada di daftar.".format(sheet_name)
    cache_key = "{}/{}".format(
        entry.get("spreadsheet_id", ""), entry.get("worksheet", "Sheet1"))
    if cache_key in _worksheet_cache:
        return _worksheet_cache[cache_key], None
    ws, err = connect_sheet(
        entry.get("spreadsheet_id", ""), entry.get("worksheet", "Sheet1"))
    if ws:
        _worksheet_cache[cache_key] = ws
    return ws, err


def _validate_cell(cell: str) -> str | None:
    if not re.match(r"^[A-Za-z]{1,3}[0-9]{1,7}$", cell.strip()):
        return "Alamat sel '{}' tidak valid. Gunakan format A1, B2, dst.".format(cell)
    return None


def read_cell(sheets_list, sheet_name, cell):
    cell_err = _validate_cell(cell)
    if cell_err:
        return "", cell_err
    ws, err = _get_ws(sheets_list, sheet_name)
    if err:
        return "", err
    try:
        val = ws.acell(cell).value
        return str(val) if val is not None else "", None
    except Exception as e:
        return "", "Gagal baca sel {}: {}".format(cell, str(e))


def write_cell(sheets_list, sheet_name, cell, value):
    cell_err = _validate_cell(cell)
    if cell_err:
        return False, cell_err
    ws, err = _get_ws(sheets_list, sheet_name)
    if err:
        return False, err
    try:
        ws.update_acell(cell, value)
        return True, None
    except Exception as e:
        msg = str(e)
        if "PERMISSION_DENIED" in msg or "403" in msg:
            email = get_service_account_email()
            return False, (
                "Tidak punya akses. Share sheet ke:\n{}\n"
                "(beri akses Editor)".format(email or "service account email")
            )
        return False, "Gagal tulis ke sel {}: {}".format(cell, msg)


def append_row(sheets_list, sheet_name, values_list):
    ws, err = _get_ws(sheets_list, sheet_name)
    if err:
        return False, err
    try:
        ws.append_row(values_list)
        return True, None
    except Exception as e:
        return False, "Gagal append row: {}".format(str(e))


def preview_data(sheets_list, sheet_name, max_rows=15):
    ws, err = _get_ws(sheets_list, sheet_name)
    if err:
        return [], err
    if ws is None:
        return [], "Worksheet tidak tersedia"
    try:
        all_rows = ws.get_all_values()
        return [row[:10] for row in all_rows[:max_rows]], None
    except Exception as e:
        return [], "Gagal load preview: {}".format(str(e))
