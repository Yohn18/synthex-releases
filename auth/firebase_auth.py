"""
auth/firebase_auth.py - Firebase REST API authentication for Synthex.
Supports auto-refresh via refresh token — no re-login needed.
"""

import json
import os
import time
import certifi
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_TOKEN_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "Synthex", "token.json")
os.makedirs(os.path.dirname(_TOKEN_FILE), exist_ok=True)

# Firebase ID tokens expire after 1 hour; we refresh proactively at 50 min
_ID_TOKEN_TTL   = 3600        # 1 hour (Firebase hard limit)
_REFRESH_MARGIN = 600         # refresh 10 min before expiry

FIREBASE_SIGNIN_URL  = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
FIREBASE_REFRESH_URL = "https://securetoken.googleapis.com/v1/token"

_session: dict = {
    "token":        None,
    "email":        None,
    "login_time":   None,
    "refresh_token": None,
    "token_issued": None,   # wall time when current ID token was issued
    "api_key":      None,
}

_ERROR_MAP = {
    "EMAIL_NOT_FOUND":           "Email not found.",
    "INVALID_PASSWORD":          "Invalid password.",
    "INVALID_LOGIN_CREDENTIALS": "Invalid email or password.",
    "USER_DISABLED":             "Account disabled. Contact Yohn18.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Try again later.",
    "INVALID_EMAIL":             "Invalid email format.",
}


def _http_post(url, params=None, json_body=None, data=None, timeout=10):
    """POST with automatic SSL fallback."""
    for verify in (certifi.where(), False):
        try:
            return requests.post(
                url, params=params, json=json_body, data=data,
                timeout=timeout, verify=verify)
        except Exception:
            continue
    return None


def _save_token_file(id_token: str, refresh_token: str,
                     email: str, issued_at: float, api_key: str):
    try:
        with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "idToken":      id_token,
                "refreshToken": refresh_token,
                "email":        email,
                "loginTime":    issued_at,
                "tokenIssued":  issued_at,
                "apiKey":       api_key,
            }, f, indent=2)
    except Exception:
        pass


def refresh_id_token(api_key: str = None, refresh_token: str = None) -> dict | None:
    """Exchange a refresh token for a new ID token.

    Uses in-memory values when parameters are omitted.
    Returns {"idToken": ..., "refreshToken": ..., "email": ...} or None.
    """
    key   = api_key      or _session.get("api_key")
    rtok  = refresh_token or _session.get("refresh_token")
    email = _session.get("email", "")

    if not key or not rtok:
        return None

    resp = _http_post(
        FIREBASE_REFRESH_URL,
        params={"key": key},
        data={"grant_type": "refresh_token", "refresh_token": rtok},
    )
    if resp is None or not resp.ok:
        return None

    data     = resp.json()
    id_token = data.get("id_token", "")
    new_rtok = data.get("refresh_token", rtok)
    if not id_token:
        return None

    now = time.time()
    _session["token"]        = id_token
    _session["refresh_token"] = new_rtok
    _session["token_issued"] = now
    _session["api_key"]      = key

    _save_token_file(id_token, new_rtok, email, now, key)
    return {"idToken": id_token, "refreshToken": new_rtok, "email": email}


def get_valid_token() -> str | None:
    """Return a valid (non-expired) ID token, auto-refreshing if needed."""
    issued = _session.get("token_issued") or _session.get("login_time")
    if issued and (time.time() - issued) >= (_ID_TOKEN_TTL - _REFRESH_MARGIN):
        refresh_id_token()
    return _session.get("token")


def sign_in_with_email_password(email: str, password: str, api_key: str) -> dict:
    """Authenticate via Firebase REST API."""
    resp = _http_post(
        FIREBASE_SIGNIN_URL,
        params={"key": api_key},
        json_body={"email": email, "password": password, "returnSecureToken": True},
    )

    if resp is None:
        return {"success": False, "error": "Network error. Check connection."}
    if not resp.ok:
        raw_err = resp.json().get("error", {}).get("message", "Authentication failed")
        return {"success": False, "error": _ERROR_MAP.get(raw_err, raw_err)}

    data         = resp.json()
    id_token     = data.get("idToken", "")
    refresh_tok  = data.get("refreshToken", "")
    result_email = data.get("email", email)
    now          = time.time()

    _session["token"]         = id_token
    _session["email"]         = result_email
    _session["login_time"]    = now
    _session["refresh_token"] = refresh_tok
    _session["token_issued"]  = now
    _session["api_key"]       = api_key

    _save_token_file(id_token, refresh_tok, result_email, now, api_key)
    return {"success": True, "token": id_token, "email": result_email}


def load_saved_session() -> dict | None:
    """Load persisted session.

    - If ID token is still fresh (< 50 min old) → use as-is.
    - If stale but refresh token exists → silently refresh.
    - If no refresh token and too old → return None (force login).
    """
    if not os.path.exists(_TOKEN_FILE):
        return None
    try:
        with open(_TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    id_token    = data.get("idToken", "")
    refresh_tok = data.get("refreshToken", "")
    email       = data.get("email", "")
    issued      = data.get("tokenIssued") or data.get("loginTime", 0)
    api_key     = data.get("apiKey", "")

    if not email:
        return None

    # Populate session so refresh_id_token() can use in-memory values
    _session["token"]         = id_token
    _session["email"]         = email
    _session["login_time"]    = issued
    _session["refresh_token"] = refresh_tok
    _session["token_issued"]  = issued
    _session["api_key"]       = api_key

    age = time.time() - issued

    # Fresh token — use directly
    if age < (_ID_TOKEN_TTL - _REFRESH_MARGIN) and id_token:
        return {"success": True, "token": id_token, "email": email}

    # Stale token — try refresh
    if refresh_tok:
        refreshed = refresh_id_token(api_key=api_key, refresh_token=refresh_tok)
        if refreshed:
            return {"success": True,
                    "token": refreshed["idToken"],
                    "email": email}

    # No refresh token and token too old → force login
    return None


def get_token() -> str | None:
    return get_valid_token()


def get_email() -> str | None:
    return _session.get("email")


def is_authenticated() -> bool:
    return bool(_session.get("token") and _session.get("email"))


def logout() -> None:
    for k in ("token", "email", "login_time", "refresh_token",
              "token_issued", "api_key"):
        _session[k] = None
    if os.path.exists(_TOKEN_FILE):
        try:
            os.remove(_TOKEN_FILE)
        except Exception:
            pass
