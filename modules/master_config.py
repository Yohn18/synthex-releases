"""
modules/master_config.py
Remote config & master controls via Firebase RTDB.
Only the master account (yohanesnzzz777@gmail.com) can write.
All authenticated users can read.
"""
import logging
import time
import requests
import certifi

MASTER_EMAIL = "yohanesnzzz777@gmail.com"
_RTDB = "https://synthex-yohn18-default-rtdb.asia-southeast1.firebasedatabase.app"
_DEFAULT_REKENING_URL = "https://app.apivalidasi.my.id/api/v3/validate"

_url_cache    = [None]
_url_cache_ts = [0.0]
_URL_CACHE_TTL = 300

_rc_cache    = [None]
_rc_cache_ts = [0.0]
_RC_CACHE_TTL = 60

_logger = logging.getLogger("master_config")


def _req(method: str, path: str, token: str, **kw):
    url = "{}/{}.json?auth={}".format(_RTDB, path, token)
    last_exc = None
    for verify in (certifi.where(), False):
        try:
            r = getattr(requests, method)(url, timeout=10, verify=verify, **kw)
            if r.ok:
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


def _email_key(email: str) -> str:
    return email.replace(".", ",").replace("@", "@at@")


# ── Rekening URL ──────────────────────────────────────────────────────────────

def get_rekening_url(token: str) -> str:
    now = time.time()
    if _url_cache[0] and (now - _url_cache_ts[0]) < _URL_CACHE_TTL:
        return _url_cache[0]
    try:
        data = _req("get", "master_config/rekening_url", token)
        if data and isinstance(data, str) and data.startswith("http"):
            _url_cache[0] = data.rstrip("/")
            _url_cache_ts[0] = now
            return _url_cache[0]
    except Exception:
        pass
    return _DEFAULT_REKENING_URL


def set_rekening_url(url: str, token: str) -> bool:
    result = _req("put", "master_config/rekening_url", token,
                  json=url.strip().rstrip("/"))
    if result is not None:
        _url_cache[0] = url.strip().rstrip("/")
        _url_cache_ts[0] = time.time()
        return True
    return False


# ── Broadcast ─────────────────────────────────────────────────────────────────

def send_broadcast(message: str, token: str) -> bool:
    data = {"message": message.strip(), "from": MASTER_EMAIL, "ts": time.time()}
    return _req("put", "master_config/broadcast", token, json=data) is not None


def get_broadcast(token: str) -> dict | None:
    try:
        data = _req("get", "master_config/broadcast", token)
        if data and isinstance(data, dict) and "message" in data:
            return data
    except Exception:
        pass
    return None


# ── Announcement bar ──────────────────────────────────────────────────────────

def set_announcement(text: str, color: str, enabled: bool, token: str) -> bool:
    data = {"text": text.strip(), "color": color, "enabled": enabled, "ts": time.time()}
    return _req("put", "master_config/announcement", token, json=data) is not None


def get_announcement(token: str) -> dict | None:
    try:
        data = _req("get", "master_config/announcement", token)
        if data and isinstance(data, dict) and data.get("enabled"):
            return data
    except Exception:
        pass
    return None


# ── Force update / min version ────────────────────────────────────────────────

def set_min_version(version: str, token: str) -> bool:
    return _req("put", "master_config/min_version", token, json=version.strip()) is not None


def get_min_version(token: str) -> str:
    try:
        data = _req("get", "master_config/min_version", token)
        if data and isinstance(data, str):
            return data
    except Exception:
        pass
    return "0.0.0"


# ── Remote config (feature toggles) ──────────────────────────────────────────

_DEFAULT_RC = {
    "rekening_enabled": True,
    "chat_enabled":     True,
    "blog_enabled":     True,
    "remote_enabled":   True,
    "monitor_enabled":  True,
    "spy_enabled":      True,
}


def set_remote_config(cfg: dict, token: str) -> bool:
    return _req("put", "master_config/remote_config", token, json=cfg) is not None


def get_remote_config(token: str) -> dict:
    now = time.time()
    if _rc_cache[0] and (now - _rc_cache_ts[0]) < _RC_CACHE_TTL:
        return _rc_cache[0]
    try:
        data = _req("get", "master_config/remote_config", token)
        if data and isinstance(data, dict):
            merged = dict(_DEFAULT_RC)
            merged.update(data)
            _rc_cache[0] = merged
            _rc_cache_ts[0] = now
            return merged
    except Exception:
        pass
    return dict(_DEFAULT_RC)


# ── Whitelist ─────────────────────────────────────────────────────────────────

def set_whitelist(enabled: bool, emails: list, token: str) -> bool:
    data = {
        "enabled": enabled,
        "emails":  {_email_key(e): True for e in emails if e.strip()},
    }
    return _req("put", "master_config/whitelist", token, json=data) is not None


def get_whitelist(token: str) -> dict:
    try:
        data = _req("get", "master_config/whitelist", token)
        if data and isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"enabled": False, "emails": {}}


def is_whitelisted(email: str, token: str) -> bool:
    wl = get_whitelist(token)
    if not wl.get("enabled", False):
        return True
    emails = wl.get("emails", {})
    return _email_key(email) in emails


# ── Ban / Kick ────────────────────────────────────────────────────────────────

def ban_user(email: str, token: str) -> bool:
    return _req("put", "master_config/banned/{}".format(_email_key(email)),
                token, json=True) is not None


def unban_user(email: str, token: str) -> bool:
    return _req("delete", "master_config/banned/{}".format(_email_key(email)),
                token) is not None


def is_banned(email: str, token: str) -> bool:
    try:
        data = _req("get", "master_config/banned/{}".format(_email_key(email)), token)
        return data is True
    except Exception:
        return False


def kick_user(email: str, token: str) -> bool:
    """Force logout user by deleting their session from RTDB."""
    return _req("delete", "sessions/{}".format(_email_key(email)), token) is not None


def get_banned_list(token: str) -> list:
    try:
        data = _req("get", "master_config/banned", token)
        if not data or not isinstance(data, dict):
            return []
        return [k.replace(",", ".").replace("@at@", "@") for k, v in data.items() if v]
    except Exception:
        return []


# ── Changelog / Release notes ─────────────────────────────────────────────────

def set_changelog(version: str, notes: str, token: str) -> bool:
    data = {"version": version.strip(), "notes": notes.strip(), "ts": time.time()}
    return _req("put", "master_config/changelog", token, json=data) is not None


def get_changelog(token: str) -> dict | None:
    try:
        data = _req("get", "master_config/changelog", token)
        if data and isinstance(data, dict) and "version" in data:
            return data
    except Exception:
        pass
    return None


# ── DM (Direct Message from master to user) ───────────────────────────────────

def send_dm(to_email: str, message: str, token: str) -> bool:
    data = {"from": MASTER_EMAIL, "message": message.strip(), "ts": time.time(), "read": False}
    return _req("post", "dm/{}".format(_email_key(to_email)), token, json=data) is not None


def reply_dm(my_email: str, message: str, token: str) -> bool:
    """User sends a reply — stored in same thread, from=my_email."""
    data = {"from": my_email, "message": message.strip(), "ts": time.time(), "read": True}
    return _req("post", "dm/{}".format(_email_key(my_email)), token, json=data) is not None


def get_dm(my_email: str, token: str) -> list:
    try:
        data = _req("get", "dm/{}".format(_email_key(my_email)), token)
        if not data or not isinstance(data, dict):
            return []
        msgs = [dict(v, _key=k) for k, v in data.items()]
        msgs.sort(key=lambda x: x.get("ts", 0))
        return msgs
    except Exception:
        return []


def count_unread_dm(my_email: str, token: str) -> int:
    """How many unread messages FROM master for this user."""
    try:
        msgs = get_dm(my_email, token)
        return sum(1 for m in msgs
                   if m.get("from") == MASTER_EMAIL and not m.get("read", False))
    except Exception:
        return 0


def get_all_dm_threads(token: str) -> list:
    """Master: get summary of all user DM threads, sorted by latest message."""
    try:
        data = _req("get", "dm", token)
        if not data or not isinstance(data, dict):
            return []
        result = []
        for email_key, messages in data.items():
            if not isinstance(messages, dict):
                continue
            email = email_key.replace(",", ".").replace("@at@", "@")
            msgs = sorted(messages.values(), key=lambda x: x.get("ts", 0))
            last = msgs[-1] if msgs else {}
            unread_from_user = sum(
                1 for m in msgs
                if m.get("from", "") != MASTER_EMAIL and not m.get("read", False))
            result.append({
                "email":        email,
                "email_key":    email_key,
                "last_message": last.get("message", ""),
                "last_ts":      last.get("ts", 0),
                "last_from":    last.get("from", ""),
                "unread":       unread_from_user,
            })
        return sorted(result, key=lambda x: x["last_ts"], reverse=True)
    except Exception:
        return []


def mark_dm_read(my_email: str, key: str, token: str):
    _req("patch", "dm/{}/{}".format(_email_key(my_email), key),
         token, json={"read": True})


def mark_all_dm_read(my_email: str, token: str):
    """Mark all master→user messages as read."""
    try:
        data = _req("get", "dm/{}".format(_email_key(my_email)), token)
        if not data or not isinstance(data, dict):
            return
        for k, v in data.items():
            if v.get("from") == MASTER_EMAIL and not v.get("read", False):
                _req("patch", "dm/{}/{}".format(_email_key(my_email), k),
                     token, json={"read": True})
    except Exception:
        pass


# ── User stats ────────────────────────────────────────────────────────────────

def get_all_sessions(token: str) -> list:
    try:
        data = _req("get", "sessions", token)
        if not data or not isinstance(data, dict):
            return []
        result = []
        for email_key, info in data.items():
            if isinstance(info, dict):
                result.append({
                    "email": email_key.replace(",", ".").replace("@at@", "@"),
                    "sid":   info.get("sid", ""),
                    "ts":    info.get("ts", 0),
                })
        return sorted(result, key=lambda x: x.get("ts", 0), reverse=True)
    except Exception:
        return []


def get_online_count(token: str, stale_sec: int = 120) -> int:
    try:
        from modules.chat import fetch_online_users
        return len(fetch_online_users(token, stale_sec=stale_sec))
    except Exception:
        return 0
