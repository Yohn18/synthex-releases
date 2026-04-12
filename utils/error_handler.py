# -*- coding: utf-8 -*-
"""
utils/error_handler.py
Converts technical exceptions into plain-English user messages for Synthex.
"""

import traceback


def friendly_message(exc: Exception) -> str:
    """
    Return a short, plain-English error message for the given exception.
    Technical details are intentionally omitted from the returned string;
    use full_details() to get the full traceback for the 'Show Details' view.
    """
    name = type(exc).__name__
    msg  = str(exc).lower()

    # ── Connection / network ──────────────────────────────────────────
    if isinstance(exc, ConnectionRefusedError):
        return "Chrome is not connected. Click 'Connect Browser' to start."

    if name in ("ConnectionResetError", "BrokenPipeError"):
        return "Connection was lost. Please try again."

    if isinstance(exc, TimeoutError) or "timeout" in msg or "timed out" in msg:
        return "Action took too long. The website may be slow or the element was not found."

    # ── File system ───────────────────────────────────────────────────
    if isinstance(exc, FileNotFoundError):
        return "File not found. Please check the path and try again."

    if isinstance(exc, PermissionError):
        return "Access denied. Close any programs using that file and try again."

    # ── Browser / Playwright ──────────────────────────────────────────
    if "executable doesn't exist" in msg or "chrome not found" in msg:
        return "Google Chrome is not installed. Please install Chrome first."

    if ("user data directory" in msg or "already running" in msg
            or "in use" in msg or "lock" in msg):
        return "Chrome profile is busy. Synthex will use a fresh window instead."

    if "net::err_name_not_resolved" in msg or "name_not_resolved" in msg:
        return "Website not found. Check that the URL is correct and you are online."

    if "net::err_connection_refused" in msg or "connection refused" in msg:
        return "Could not reach the website. It may be down or the URL may be wrong."

    if ("waiting for selector" in msg or "element not found" in msg
            or "no element matches" in msg or "strict mode violation" in msg):
        return "Could not find the element on the page. The website may have changed."

    if "navigation" in msg and ("failed" in msg or "timeout" in msg):
        return "Page did not load in time. Check your internet connection."

    if "browser worker stopped" in msg:
        return "Chrome is not connected. Click 'Connect Browser' to start."

    # ── Google Sheets / gspread ───────────────────────────────────────
    if name == "APIError" or "googleapis" in msg:
        if "permission_denied" in msg or "403" in msg:
            return "No access to this sheet. Make sure you shared it with the Synthex email."
        if "404" in msg or "not found" in msg:
            return "Sheet not found. Check the URL is correct."
        if "quota" in msg or "429" in msg:
            return "Google Sheets rate limit reached. Please wait a moment and try again."
        return "Google Sheets error. Check your internet connection and sheet permissions."

    if "credentials" in msg and ("not found" in msg or "missing" in msg):
        return "Google Sheets not set up yet. Go to the Sheets tab to connect."

    if "invalid_grant" in msg or "token" in msg and "expired" in msg:
        return "Google account session expired. Go to the Sheets tab to reconnect."

    if "range" in msg and ("invalid" in msg or "out of range" in msg):
        return "Cell address is invalid. Use a format like A1, B2, or C10."

    # ── Value / type errors ───────────────────────────────────────────
    if isinstance(exc, ValueError):
        return "Invalid value: {}".format(str(exc)[:80])

    if isinstance(exc, KeyError):
        return "Missing data: '{}' not found. The configuration may be incomplete.".format(
            str(exc).strip("'\""))

    # ── Runtime / import ─────────────────────────────────────────────
    if isinstance(exc, ImportError) or isinstance(exc, ModuleNotFoundError):
        return "A required component is missing. Try reinstalling Synthex."

    if isinstance(exc, RuntimeError):
        if "browser worker stopped" in msg:
            return "Chrome is not connected. Click 'Connect Browser' to start."
        return "Something went wrong: {}. Try again or restart Synthex.".format(
            str(exc)[:80])

    # ── Fallback ──────────────────────────────────────────────────────
    short = str(exc)[:100].rstrip(".")
    if short:
        return "Something went wrong: {}. Try again or restart Synthex.".format(short)
    return "An unexpected error occurred. Try again or restart Synthex."


def full_details(exc: Exception) -> str:
    """Return the full technical traceback as a string (for 'Show Details' button)."""
    return "{}: {}\n\n{}".format(
        type(exc).__name__, exc, traceback.format_exc())
