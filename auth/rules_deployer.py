"""
auth/rules_deployer.py
Auto-deploy Firebase RTDB rules using stored OAuth2 credentials.
Called by Master Panel and on app startup (if master is logged in).
"""
import json
import os
import requests
import certifi

_RTDB = "https://synthex-yohn18-default-rtdb.asia-southeast1.firebasedatabase.app"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RULES_PATH  = os.path.join(_ROOT, "database.rules.json")
_GTOKEN_PATH = os.path.join(os.environ.get("APPDATA", ""), "Synthex", "gtoken.json")

_MASTER = "auth.token.email == 'yohanesnzzz777@gmail.com'"

_RULES = {
    "rules": {
        "sessions":      {".read": "auth != null", ".write": "auth != null"},
        "chat":          {"messages": {".read": "auth != null", ".write": "auth != null"}},
        "presence":      {".read": "auth != null", ".write": "auth != null"},
        "blog":          {"posts": {".read": "auth != null", ".write": _MASTER}},
        "dm": {
            "$user": {
                ".read":  "auth != null && (" + _MASTER + " || $user == auth.token.email.replace('.', ',').replace('@', '@at@'))",
                ".write": "auth != null && (" + _MASTER + " || $user == auth.token.email.replace('.', ',').replace('@', '@at@'))",
            }
        },
        "master_config": {".read": "auth != null", ".write": _MASTER},
    }
}


def _load_gtoken() -> dict:
    try:
        with open(_GTOKEN_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_gtoken(data: dict):
    os.makedirs(os.path.dirname(_GTOKEN_PATH), exist_ok=True)
    with open(_GTOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _get_access_token() -> str:
    """Return a valid access token, refreshing if needed."""
    g = _load_gtoken()
    access_token = g.get("access_token", "")

    # Try current access token first
    if access_token:
        r = _test_token(access_token)
        if r:
            return access_token

    # Refresh it
    refresh_token = g.get("refresh_token", "")
    client_id     = g.get("client_id",
        "563584335869-fgrhgmd47bqnekij5i8b5pr03ho849e6.apps.googleusercontent.com")
    client_secret = g.get("client_secret", "j9iVZfS8kkCEFUPaAeJV0sAi")

    if not refresh_token:
        raise RuntimeError("Tidak ada refresh token. Jalankan setup OAuth2 dulu.")

    for verify in (certifi.where(), False):
        try:
            r = requests.post("https://oauth2.googleapis.com/token", data={
                "client_id":     client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type":    "refresh_token",
            }, timeout=15, verify=verify)
            if r.ok:
                new_token = r.json()["access_token"]
                g["access_token"] = new_token
                _save_gtoken(g)
                return new_token
        except Exception:
            continue

    raise RuntimeError("Gagal refresh token OAuth2.")


def _test_token(token: str) -> bool:
    """Quick test if token is still valid."""
    try:
        r = requests.get(
            f"{_RTDB}/.settings/rules.json",
            headers={"Authorization": f"Bearer {token}"},
            timeout=8, verify=certifi.where())
        return r.status_code == 200
    except Exception:
        return False


def deploy_rules() -> tuple[bool, str]:
    """
    Deploy RTDB security rules. Returns (success: bool, message: str).
    Automatically refreshes OAuth2 token if expired.
    """
    try:
        token = _get_access_token()
    except RuntimeError as e:
        return False, str(e)

    for verify in (certifi.where(), False):
        try:
            r = requests.put(
                f"{_RTDB}/.settings/rules.json",
                headers={"Authorization": f"Bearer {token}"},
                json=_RULES,
                timeout=20,
                verify=verify,
            )
            if r.ok:
                return True, "✓ Firebase rules berhasil di-deploy."
            return False, f"HTTP {r.status_code}: {r.text[:100]}"
        except Exception as e:
            last_err = str(e)
            continue

    return False, f"Koneksi gagal: {last_err}"
