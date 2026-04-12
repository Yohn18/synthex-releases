"""
auth/firebase_auth.py - Firebase REST API authentication for Synthex.
Returns structured result dicts; stores session token in auth/token.json.
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
_SESSION_TIMEOUT = 86400  # 24 hours

FIREBASE_SIGNIN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
)

_session: dict = {"token": None, "email": None, "login_time": None}

_ERROR_MAP = {
    "EMAIL_NOT_FOUND": "Email not found.",
    "INVALID_PASSWORD": "Invalid password.",
    "INVALID_LOGIN_CREDENTIALS": "Invalid email or password.",
    "USER_DISABLED": "Account disabled. Contact Yohn18.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Try again later.",
    "INVALID_EMAIL": "Invalid email format.",
}


def sign_in_with_email_password(email: str, password: str, api_key: str) -> dict:
    """Authenticate via Firebase REST API.

    Returns:
        {"success": True, "token": "...", "email": "..."}
        {"success": False, "error": "..."}
    """
    payload = {"email": email, "password": password, "returnSecureToken": True}
    params = {"key": api_key}

    resp = None
    for verify in (certifi.where(), False):
        try:
            resp = requests.post(
                FIREBASE_SIGNIN_URL,
                params=params,
                json=payload,
                timeout=10,
                verify=verify,
            )
            break
        except Exception:
            continue

    if resp is None:
        return {"success": False, "error": "Network error. Check connection."}

    if not resp.ok:
        raw_err = resp.json().get("error", {}).get("message", "Authentication failed")
        return {"success": False, "error": _ERROR_MAP.get(raw_err, raw_err)}

    data = resp.json()
    token = data.get("idToken", "")
    result_email = data.get("email", email)
    now = time.time()

    _session["token"] = token
    _session["email"] = result_email
    _session["login_time"] = now

    try:
        with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "idToken": token,
                    "refreshToken": data.get("refreshToken", ""),
                    "email": result_email,
                    "loginTime": now,
                },
                f,
                indent=2,
            )
    except Exception:
        pass

    return {"success": True, "token": token, "email": result_email}


def load_saved_session() -> dict | None:
    """Return saved session if the token is less than 24 hours old, else None."""
    if not os.path.exists(_TOKEN_FILE):
        return None
    try:
        with open(_TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        login_time = data.get("loginTime", 0)
        if time.time() - login_time > _SESSION_TIMEOUT:
            return None
        token = data.get("idToken", "")
        email = data.get("email", "")
        if not token:
            return None
        _session["token"] = token
        _session["email"] = email
        _session["login_time"] = login_time
        return {"success": True, "token": token, "email": email}
    except Exception:
        return None


def get_token() -> str | None:
    return _session["token"]


def get_email() -> str | None:
    return _session["email"]


def is_authenticated() -> bool:
    if not _session["token"] or not _session["login_time"]:
        return False
    return (time.time() - _session["login_time"]) < _SESSION_TIMEOUT


def logout() -> None:
    _session["token"] = None
    _session["email"] = None
    _session["login_time"] = None
    if os.path.exists(_TOKEN_FILE):
        try:
            os.remove(_TOKEN_FILE)
        except Exception:
            pass
