# -*- coding: utf-8 -*-
"""
modules/wa_bot.py
WhatsApp auto-reply bot via ADB notification monitoring + AI reply.
"""
import json
import os
import re
import threading
import time
from core.logger import get_logger

logger = get_logger("wa_bot")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_ai_cfg() -> dict:
    try:
        with open(os.path.join(_ROOT, "config.json"), encoding="utf-8") as f:
            return json.load(f).get("ai", {})
    except Exception:
        return {}


def _ai_reply(sender: str, message: str, context: str,
               api_key: str, provider: str, model: str) -> str:
    """Generate a reply using AI."""
    import requests, certifi

    system = (
        "Kamu adalah asisten auto-reply WhatsApp yang sopan dan singkat. "
        "Balas pesan dengan bahasa yang sama dengan pengirim (Indonesia/English). "
        "Maksimal 2 kalimat. Jangan berpura-pura menjadi manusia, tapi jawab dengan natural. "
    )
    if context:
        system += "Konteks tambahan: {}".format(context)

    user_prompt = "Pengirim: {}\nPesan: {}\n\nBuat balasan singkat.".format(sender, message)

    provider = (provider or "anthropic").lower()
    try:
        if provider == "anthropic":
            model = model or "claude-haiku-4-5-20251001"
            body = {
                "model": model, "max_tokens": 256,
                "system": system,
                "messages": [{"role": "user", "content": user_prompt}],
            }
            r = requests.post("https://api.anthropic.com/v1/messages",
                              headers={"x-api-key": api_key,
                                       "anthropic-version": "2023-06-01",
                                       "Content-Type": "application/json"},
                              json=body, timeout=20, verify=certifi.where())
            if r.ok:
                return (r.json().get("content", [{}])[0].get("text") or "").strip()

        elif provider == "openai":
            model = model or "gpt-4o-mini"
            body = {
                "model": model, "max_tokens": 256,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
            }
            r = requests.post("https://api.openai.com/v1/chat/completions",
                              headers={"Authorization": "Bearer {}".format(api_key),
                                       "Content-Type": "application/json"},
                              json=body, timeout=20, verify=certifi.where())
            if r.ok:
                return (r.json().get("choices", [{}])[0]
                        .get("message", {}).get("content") or "").strip()

        elif provider == "gemini":
            model = model or "gemini-2.0-flash"
            url = ("https://generativelanguage.googleapis.com/v1beta/models/"
                   "{}:generateContent?key={}".format(model, api_key))
            body = {"contents": [{"parts": [{"text": system + "\n\n" + user_prompt}]}]}
            r = requests.post(url, json=body, timeout=20, verify=certifi.where())
            if r.ok:
                return (r.json().get("candidates", [{}])[0]
                        .get("content", {}).get("parts", [{}])[0]
                        .get("text") or "").strip()
    except Exception as e:
        logger.error("AI reply error: %s", e)

    return ""


class WABot:
    """
    Monitor WhatsApp notifications via ADB dumpsys, generate AI replies,
    and send via ADB input text + keyevent.
    """

    POLL_INTERVAL = 4  # seconds between notification polls

    def __init__(self, adb_manager):
        self.adb      = adb_manager
        self._running = False
        self._thread  = None
        self._seen    = set()   # (pkg, key) already replied
        self.config   = {
            "enabled":  False,
            "context":  "",
            "api_key":  "",
            "provider": "anthropic",
            "model":    "claude-haiku-4-5-20251001",
            "whitelist": [],  # empty = reply to everyone
        }
        self.on_reply = None  # callback(sender, msg, reply)
        self.on_error = None  # callback(str)

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self, serial: str):
        if self._running:
            return
        cfg = _load_ai_cfg()
        self.config["api_key"]  = self.config["api_key"]  or cfg.get("api_key", "")
        self.config["provider"] = self.config["provider"] or cfg.get("provider", "anthropic")
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, args=(serial,), daemon=True)
        self._thread.start()
        logger.info("WABot started for %s", serial)

    def stop(self):
        self._running = False
        logger.info("WABot stopped")

    @property
    def running(self) -> bool:
        return self._running

    # ── Notification polling ──────────────────────────────────────────────────

    def _dump_notifications(self, serial: str) -> list:
        """Parse WA notifications from dumpsys. Returns list of dicts."""
        rc, out, _ = self.adb._run(
            "-s", serial, "shell",
            "dumpsys", "notification", "--noredact",
            timeout=10)
        if rc != 0:
            return []

        results = []
        cur = {}
        for line in out.splitlines():
            line = line.strip()
            if "pkg=com.whatsapp" in line or "pkg=com.whatsapp.w4b" in line:
                cur = {"pkg": "whatsapp"}
            if cur and "android.title=" in line:
                m = re.search(r'android\.title=([^\n]+)', line)
                if m:
                    cur["sender"] = m.group(1).strip().strip('"')
            if cur and "android.text=" in line:
                m = re.search(r'android\.text=([^\n]+)', line)
                if m:
                    cur["text"] = m.group(1).strip().strip('"')
            if cur and "key=" in line and "sender" in cur and "text" in cur:
                m = re.search(r'key=([^\s]+)', line)
                if m:
                    cur["key"] = m.group(1)
                    results.append(dict(cur))
                    cur = {}
        return results

    # ── Reply via ADB ─────────────────────────────────────────────────────────

    def _open_wa_reply(self, serial: str, sender: str):
        """Pull down notification shade and tap WA notification."""
        self.adb._run("-s", serial, "shell",
                      "cmd", "statusbar", "expand-notifications", timeout=5)
        time.sleep(0.8)
        rc, out, _ = self.adb._run(
            "-s", serial, "shell",
            "uiautomator", "dump", "/dev/stdin", timeout=10)
        # Try to find and click the WA notification by text
        m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^/]*/>', out)
        if not m:
            return False
        x = (int(m.group(1)) + int(m.group(3))) // 2
        y = (int(m.group(2)) + int(m.group(4))) // 2
        self.adb._run("-s", serial, "shell", "input", "tap",
                      str(x), str(y), timeout=5)
        time.sleep(1.2)
        return True

    def _send_text_adb(self, serial: str, text: str):
        """Type text via ADB input, then send."""
        escaped = text.replace(" ", "%s").replace("'", "\\'")
        self.adb._run("-s", serial, "shell",
                      "input", "text", escaped, timeout=10)
        time.sleep(0.3)
        self.adb._run("-s", serial, "shell",
                      "input", "keyevent", "KEYCODE_ENTER", timeout=5)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self, serial: str):
        while self._running:
            try:
                notifs = self._dump_notifications(serial)
                for n in notifs:
                    uid = (n.get("pkg"), n.get("key"))
                    if uid in self._seen:
                        continue
                    self._seen.add(uid)

                    sender = n.get("sender", "")
                    text   = n.get("text", "")
                    if not sender or not text:
                        continue

                    wl = self.config.get("whitelist", [])
                    if wl and sender not in wl:
                        continue

                    logger.info("WA dari %s: %s", sender, text[:60])

                    reply = _ai_reply(
                        sender, text,
                        self.config.get("context", ""),
                        self.config["api_key"],
                        self.config["provider"],
                        self.config["model"],
                    )
                    if not reply:
                        continue

                    self._send_text_adb(serial, reply)
                    logger.info("Auto-reply ke %s: %s", sender, reply[:80])
                    if self.on_reply:
                        self.on_reply(sender, text, reply)

            except Exception as e:
                logger.error("WABot loop error: %s", e)
                if self.on_error:
                    self.on_error(str(e))

            time.sleep(self.POLL_INTERVAL)

        self._running = False
