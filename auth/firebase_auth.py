"""
auth/firebase_auth.py - Firebase REST API authentication for Synthex.
Supports auto-refresh via refresh token — no re-login needed.
Single-session enforcement via Firebase Realtime Database.
"""

import json
import logging
import os
import threading
import time
import uuid
import certifi
import requests
import urllib3

_logger       = logging.getLogger("firebase_auth")
_session_lock = threading.Lock()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_TOKEN_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "Synthex", "token.json")
os.makedirs(os.path.dirname(_TOKEN_FILE), exist_ok=True)

# Firebase ID tokens expire after 1 hour; we refresh proactively at 50 min
_ID_TOKEN_TTL   = 3600        # 1 hour (Firebase hard limit)
_REFRESH_MARGIN = 600         # refresh 10 min before expiry

FIREBASE_SIGNIN_URL  = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
FIREBASE_REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
_RTDB_BASE = "https://synthex-yohn18-default-rtdb.asia-southeast1.firebasedatabase.app"

_session: dict = {
    "token":        None,
    "email":        None,
    "login_time":   None,
    "refresh_token": None,
    "token_issued": None,   # wall time when current ID token was issued
    "api_key":      None,
    "session_id":   None,   # unique ID for this login instance
}

_ERROR_MAP = {
    "EMAIL_NOT_FOUND":           "Email not found.",
    "INVALID_PASSWORD":          "Invalid password.",
    "INVALID_LOGIN_CREDENTIALS": "Invalid email or password.",
    "USER_DISABLED":             "Account disabled. Contact Yohn18.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Try again later.",
    "INVALID_EMAIL":             "Invalid email format.",
}


def _email_key(email: str) -> str:
    """Convert email to a safe Firebase RTDB key (no . / $ # [ ])."""
    return email.replace(".", "_").replace("@", "_at_")


def _rtdb_put(path: str, data: dict, id_token: str) -> bool:
    url = "{}/{}.json?auth={}".format(_RTDB_BASE, path, id_token)
    for verify in (certifi.where(), False):
        try:
            r = requests.put(url, json=data, timeout=8, verify=verify)
            return r.ok
        except Exception:
            continue
    return False


def _rtdb_get(path: str, id_token: str) -> dict | None:
    url = "{}/{}.json?auth={}".format(_RTDB_BASE, path, id_token)
    for verify in (certifi.where(), False):
        try:
            r = requests.get(url, timeout=8, verify=verify)
            if r.ok:
                return r.json()
        except Exception:
            continue
    return None


def _rtdb_delete(path: str, id_token: str):
    url = "{}/{}.json?auth={}".format(_RTDB_BASE, path, id_token)
    for verify in (certifi.where(), False):
        try:
            requests.delete(url, timeout=8, verify=verify)
            return
        except Exception:
            continue


def register_session(email: str, id_token: str) -> str:
    """Write a new session_id to RTDB and return it."""
    sid = str(uuid.uuid4())
    _rtdb_put(
        "sessions/{}".format(_email_key(email)),
        {"session_id": sid, "ts": time.time()},
        id_token,
    )
    _session["session_id"] = sid
    return sid


def get_remote_session_id(email: str, id_token: str) -> str | None:
    """Read the active session_id from RTDB."""
    data = _rtdb_get("sessions/{}".format(_email_key(email)), id_token)
    if isinstance(data, dict):
        return data.get("session_id")
    return None


def clear_session_rtdb(email: str, id_token: str):
    """Remove session entry from RTDB on logout."""
    _rtdb_delete("sessions/{}".format(_email_key(email)), id_token)


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
    with _session_lock:
        key   = api_key       or _session.get("api_key")
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
        reason = "no response" if resp is None else "HTTP {}".format(resp.status_code)
        _logger.warning("refresh_id_token gagal: %s", reason)
        return None

    data     = resp.json()
    id_token = data.get("id_token", "")
    new_rtok = data.get("refresh_token", rtok)
    if not id_token:
        _logger.warning("refresh_id_token: respons OK tapi id_token kosong")
        return None

    now = time.time()
    with _session_lock:
        _session["token"]         = id_token
        _session["refresh_token"] = new_rtok
        _session["token_issued"]  = now
        _session["api_key"]       = key

    _save_token_file(id_token, new_rtok, email, now, key)
    return {"idToken": id_token, "refreshToken": new_rtok, "email": email}


def get_valid_token() -> str | None:
    """Return a valid (non-expired) ID token, auto-refreshing if needed."""
    with _session_lock:
        issued = _session.get("token_issued") or _session.get("login_time")
        token  = _session.get("token")
    if issued and (time.time() - issued) >= (_ID_TOKEN_TTL - _REFRESH_MARGIN):
        refresh_id_token()
        with _session_lock:
            token = _session.get("token")
    return token


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

    with _session_lock:
        _session["token"]         = id_token
        _session["email"]         = result_email
        _session["login_time"]    = now
        _session["refresh_token"] = refresh_tok
        _session["token_issued"]  = now
        _session["api_key"]       = api_key

    # Check ban status before allowing login
    try:
        from modules.master_config import is_banned, is_whitelisted
        if is_banned(result_email, id_token):
            return {"success": False, "error": "Akun kamu diblokir oleh admin. Hubungi admin untuk informasi lebih lanjut."}
        if not is_whitelisted(result_email, id_token):
            return {"success": False, "error": "Akses ditolak. Akunmu belum ada di daftar whitelist. Hubungi admin Synthex."}
    except Exception:
        pass

    # Register single-session — overwrites any existing session on RTDB
    sid = register_session(result_email, id_token)

    _save_token_file(id_token, refresh_tok, result_email, now, api_key)
    return {"success": True, "token": id_token, "email": result_email,
            "session_id": sid}


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
    with _session_lock:
        _session["token"]         = id_token
        _session["email"]         = email
        _session["login_time"]    = issued
        _session["refresh_token"] = refresh_tok
        _session["token_issued"]  = issued
        _session["api_key"]       = api_key

    age = time.time() - issued

    # Fresh token — use directly
    if age < (_ID_TOKEN_TTL - _REFRESH_MARGIN) and id_token:
        sid = register_session(email, id_token)
        return {"success": True, "token": id_token, "email": email,
                "session_id": sid}

    # Stale token — try refresh
    if refresh_tok:
        refreshed = refresh_id_token(api_key=api_key, refresh_token=refresh_tok)
        if refreshed:
            sid = register_session(email, refreshed["idToken"])
            return {"success": True,
                    "token": refreshed["idToken"],
                    "email": email,
                    "session_id": sid}

    # No refresh token and token too old → force login
    return None


def get_token() -> str | None:
    return get_valid_token()


def get_email() -> str | None:
    with _session_lock:
        return _session.get("email")


def is_authenticated() -> bool:
    with _session_lock:
        return bool(_session.get("token") and _session.get("email"))


def logout() -> None:
    with _session_lock:
        email    = _session.get("email")
        id_token = _session.get("token")
    if email and id_token:
        try:
            clear_session_rtdb(email, id_token)
        except Exception:
            pass
    with _session_lock:
        for k in ("token", "email", "login_time", "refresh_token",
                  "token_issued", "api_key", "session_id"):
            _session[k] = None
    if os.path.exists(_TOKEN_FILE):
        try:
            os.remove(_TOKEN_FILE)
        except Exception:
            pass
