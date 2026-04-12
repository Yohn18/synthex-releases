# -*- coding: utf-8 -*-
"""
modules/sheets/connector.py
Google Sheets connector for Synthex.
Uses gspread with a service account credentials file.
All errors are returned as plain English strings, not exceptions.
"""

import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CREDS_PATH = os.path.join(_ROOT, "credentials.json")

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Cache: sheet_name -> gspread worksheet object
_worksheet_cache = {}
# gspread client singleton
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client, None
    if not os.path.isfile(_CREDS_PATH):
        return None, (
            "Google Sheets not set up yet. "
            "Go to the Sheets tab and click 'Setup Google Sheets' to connect."
        )
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_file(_CREDS_PATH, scopes=_SCOPES)
        _client = gspread.authorize(creds)
        return _client, None
    except ImportError:
        return None, (
            "Required packages not installed. Run:\n"
            "pip install gspread google-auth"
        )
    except Exception as e:
        return None, "Could not connect to Google: {}".format(str(e))


def reset_client():
    """Force re-authentication on next call (call after credentials change)."""
    global _client
    _client = None
    _worksheet_cache.clear()


def get_service_account_email():
    """Return the service account email from credentials.json, or None."""
    try:
        import json
        with open(_CREDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("client_email", "")
    except Exception:
        return ""


def extract_sheet_id(url_or_id):
    """Return the spreadsheet ID from a URL or return the value as-is if it looks like an ID."""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)
    if re.match(r"^[a-zA-Z0-9_-]{10,}$", url_or_id.strip()):
        return url_or_id.strip()
    return ""


def get_worksheets(sheet_id):
    """
    Return list of worksheet names for a spreadsheet ID.
    Returns (list_of_names, error_string_or_None).
    """
    client, err = _get_client()
    if err:
        return [], err
    try:
        wb = client.open_by_key(sheet_id)
        names = [ws.title for ws in wb.worksheets()]
        return names, None
    except Exception as e:
        msg = str(e)
        if "PERMISSION_DENIED" in msg or "403" in msg:
            email = get_service_account_email()
            return [], (
                "Permission denied. Share your Google Sheet with:\n{}\n"
                "(give Editor access)".format(email or "the service account email")
            )
        if "404" in msg or "not found" in msg.lower():
            return [], "Sheet not found. Check the URL is correct and the sheet exists."
        return [], "Could not open sheet: {}".format(msg)


def connect_sheet(url_or_id, worksheet_name="Sheet1"):
    """
    Open a sheet and cache it. Returns (worksheet_object, error_string_or_None).
    """
    client, err = _get_client()
    if err:
        return None, err
    sheet_id = extract_sheet_id(url_or_id)
    if not sheet_id:
        return None, "Could not find a valid Sheet ID in: {}".format(url_or_id)
    try:
        wb = client.open_by_key(sheet_id)
        ws = wb.worksheet(worksheet_name)
        return ws, None
    except Exception as e:
        msg = str(e)
        if "PERMISSION_DENIED" in msg or "403" in msg:
            email = get_service_account_email()
            return None, (
                "Permission denied. Share your Google Sheet with:\n{}\n"
                "(give Editor access)".format(email or "the service account email")
            )
        if "not found" in msg.lower() or "404" in msg:
            return None, (
                "Worksheet '{}' not found. Check the tab name in your sheet.".format(
                    worksheet_name
                )
            )
        return None, "Could not connect to sheet: {}".format(msg)


def _get_ws(sheets_list, sheet_name):
    """Get worksheet for a named sheet entry from user_data sheets list."""
    entry = next((s for s in sheets_list if s.get("name") == sheet_name), None)
    if not entry:
        return None, "Sheet '{}' not found in connected sheets.".format(sheet_name)
    cache_key = "{}/{}".format(entry.get("spreadsheet_id", ""), entry.get("worksheet", "Sheet1"))
    if cache_key in _worksheet_cache:
        return _worksheet_cache[cache_key], None
    ws, err = connect_sheet(
        entry.get("spreadsheet_id", ""),
        entry.get("worksheet", "Sheet1"),
    )
    if ws:
        _worksheet_cache[cache_key] = ws
    return ws, err


def _validate_cell(cell: str):
    """Return an error string if the cell address looks invalid, else None."""
    if not re.match(r"^[A-Za-z]{1,3}[0-9]{1,7}$", cell.strip()):
        return (
            "Cell address '{}' is invalid. "
            "Use a format like A1, B2, or C10.".format(cell)
        )
    return None


def read_cell(sheets_list, sheet_name, cell):
    """
    Read a cell value. Returns (value_string, error_string_or_None).
    """
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
        msg = str(e)
        if "range" in msg.lower() or "out of range" in msg.lower():
            return "", "Cell address is out of range. Use a format like A1, B2, or C10."
        return "", "Could not read cell {}: {}".format(cell, msg)


def write_cell(sheets_list, sheet_name, cell, value):
    """
    Write a value to a cell. Returns (True/False, error_string_or_None).
    """
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
                "No access to this sheet. Make sure you shared it with:\n{}\n"
                "(give Editor access)".format(email or "the service account email")
            )
        if "range" in msg.lower() or "out of range" in msg.lower():
            return False, "Cell address is out of range. Use a format like A1, B2, or C10."
        return False, "Could not write to cell {}: {}".format(cell, msg)


def append_row(sheets_list, sheet_name, values_list):
    """
    Append a row. values_list is a list. Returns (True/False, error_string_or_None).
    """
    ws, err = _get_ws(sheets_list, sheet_name)
    if err:
        return False, err
    try:
        ws.append_row(values_list)
        return True, None
    except Exception as e:
        return False, "Could not append row: {}".format(str(e))


def preview_data(sheets_list, sheet_name, max_rows=15):
    """
    Return list-of-lists for the first max_rows rows (up to 10 columns).
    Returns (rows, error_string_or_None).
    """
    ws, err = _get_ws(sheets_list, sheet_name)
    if err:
        return [], err
    try:
        all_rows = ws.get_all_values()
        trimmed = []
        for row in all_rows[:max_rows]:
            trimmed.append(row[:10])
        return trimmed, None
    except Exception as e:
        return [], "Could not load preview: {}".format(str(e))


def credentials_exist():
    """Return True if credentials.json is present and readable."""
    return os.path.isfile(_CREDS_PATH)
