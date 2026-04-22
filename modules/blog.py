"""
modules/blog.py
Community blog via Firebase RTDB + Storage.
Only admin can write; all auth users can read.
"""
import os
import time
import uuid
import mimetypes
import requests
import certifi

ADMIN_EMAIL = "yohanesnzzz777@gmail.com"
_RTDB    = "https://synthex-yohn18-default-rtdb.asia-southeast1.firebasedatabase.app"
_BUCKET  = "synthex-yohn18.appspot.com"
_STORAGE = "https://firebasestorage.googleapis.com/v0/b/{}/o".format(_BUCKET)


def _req(method: str, path: str, token: str, **kw):
    url = "{}/{}.json?auth={}".format(_RTDB, path, token)
    for verify in (certifi.where(), False):
        try:
            r = getattr(requests, method)(url, timeout=10, verify=verify, **kw)
            if r.ok:
                return r.json()
        except Exception:
            continue
    return None


# ── Storage upload ─────────────────────────────────────────────────────────

def upload_image(local_path: str, token: str) -> str | None:
    """Upload image to Firebase Storage, return public download URL or None."""
    ext = os.path.splitext(local_path)[1].lower() or ".jpg"
    mime = mimetypes.guess_type(local_path)[0] or "image/jpeg"
    name = "blog/{}_{}{}".format(
        int(time.time()), uuid.uuid4().hex[:8], ext)

    with open(local_path, "rb") as fh:
        data = fh.read()

    params = {"name": name, "uploadType": "media"}
    headers = {
        "Authorization": "Bearer {}".format(token),
        "Content-Type":  mime,
    }
    for verify in (certifi.where(), False):
        try:
            r = requests.post(_STORAGE, params=params, headers=headers,
                              data=data, timeout=30, verify=verify)
            if r.ok:
                encoded = name.replace("/", "%2F")
                return ("https://firebasestorage.googleapis.com/v0/b/{}/o/{}"
                        "?alt=media".format(_BUCKET, encoded))
        except Exception:
            continue
    return None


# ── RTDB posts ─────────────────────────────────────────────────────────────

def fetch_posts(token: str) -> list:
    """Return all posts sorted newest-first."""
    data = _req("get", "blog/posts", token)
    if not data or not isinstance(data, dict):
        return []
    posts = [dict(v, _id=k) for k, v in data.items()]
    posts.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return posts


def create_post(title: str, content: str, summary: str,
                author_email: str, token: str,
                media: list | None = None) -> bool:
    if author_email != ADMIN_EMAIL:
        return False
    data = {
        "title":        title.strip(),
        "content":      content.strip(),
        "summary":      summary.strip()[:120],
        "author_email": author_email,
        "author_name":  author_email.split("@")[0],
        "ts":           time.time(),
        "media":        media or [],
    }
    return _req("post", "blog/posts", token, json=data) is not None


def update_post(post_id: str, title: str, content: str,
                summary: str, token: str,
                media: list | None = None) -> bool:
    data = {
        "title":   title.strip(),
        "content": content.strip(),
        "summary": summary.strip()[:120],
        "media":   media if media is not None else [],
    }
    url = "{}/blog/posts/{}.json?auth={}".format(_RTDB, post_id, token)
    for verify in (certifi.where(), False):
        try:
            r = requests.patch(url, json=data, timeout=10, verify=verify)
            return r.ok
        except Exception:
            continue
    return False


def delete_post(post_id: str, token: str) -> bool:
    url = "{}/blog/posts/{}.json?auth={}".format(_RTDB, post_id, token)
    for verify in (certifi.where(), False):
        try:
            r = requests.delete(url, timeout=8, verify=verify)
            return r.ok
        except Exception:
            continue
    return False
