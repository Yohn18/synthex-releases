"""
modules/chat.py
Group chat + presence via Firebase RTDB for Synthex users.
"""
import logging
import time
import requests
import certifi

_RTDB   = "https://synthex-yohn18-default-rtdb.asia-southeast1.firebasedatabase.app"
_logger = logging.getLogger("chat")


def _email_key(email: str) -> str:
    return email.replace(".", "_").replace("@", "_at_")


def _req(method: str, path: str, token: str, **kw):
    url = "{}/{}.json?auth={}".format(_RTDB, path, token)
    last_exc = None
    for verify in (certifi.where(), False):
        try:
            r = getattr(requests, method)(url, timeout=8, verify=verify, **kw)
            if r.ok:
                if not verify:
                    _logger.warning("SSL verification dinonaktifkan untuk %s %s", method, path)
                return r.json()
        except requests.Timeout:
            last_exc = "timeout"
        except requests.ConnectionError:
            last_exc = "connection error"
        except Exception as e:
            last_exc = str(e)
    if last_exc:
        _logger.debug("_req %s %s gagal: %s", method, path, last_exc)
    return None


def send_message(email: str, text: str, token: str) -> bool:
    name = email.split("@")[0]
    data = {"from": email, "name": name, "text": text.strip(), "ts": time.time()}
    return _req("post", "chat/messages", token, json=data) is not None


def fetch_messages(token: str, limit: int = 80):
    """Return up to `limit` recent messages sorted oldest-first.

    Returns:
        list            – success (may be empty)
        "AUTH_EXPIRED"  – Firebase returned 401 (token stale)
        None            – network / other error
    """
    url = ("{}/chat/messages.json?auth={}"
           "&orderBy=\"$key\"&limitToLast={}").format(_RTDB, token, limit)
    for verify in (certifi.where(), False):
        try:
            r = requests.get(url, timeout=8, verify=verify)
            if r.ok:
                if not verify:
                    _logger.warning("SSL verification dinonaktifkan untuk fetch_messages")
                data = r.json()
                if not data or not isinstance(data, dict):
                    return []
                return [dict(v, _key=k) for k, v in sorted(data.items())]
            if r.status_code == 401:
                return "AUTH_EXPIRED"
        except Exception:
            continue
    return None


def update_presence(email: str, token: str, online: bool = True):
    data = {"email": email, "online": online, "last_seen": time.time()}
    _req("put", "presence/{}".format(_email_key(email)), token, json=data)


def fetch_online_users(token: str, stale_sec: int = 90) -> list:
    """Return list of {email, last_seen} for recently active users."""
    data = _req("get", "presence", token)
    if not data or not isinstance(data, dict):
        return []
    now = time.time()
    result = []
    for val in data.values():
        if (isinstance(val, dict)
                and val.get("online")
                and now - val.get("last_seen", 0) < stale_sec):
            email = val.get("email", "")
            if email:
                result.append({"email": email, "last_seen": val.get("last_seen", 0)})
    result.sort(key=lambda x: x["last_seen"], reverse=True)
    return result
