# -*- coding: utf-8 -*-
"""
modules/web_change_monitor.py
Monitor perubahan konten sebuah URL secara berkala.
Gunakan web_scraper.scrape_url() — tidak butuh Playwright/Chrome.

Fitur:
  - Pantau apakah konten halaman berubah
  - Pantau keberadaan keyword tertentu (muncul/hilang)
  - Optional: analisis perubahan via AI
  - Callback on_change(old, new, diff_summary)
"""

import hashlib
import threading
import time
from datetime import datetime
from core.logger import get_logger

logger = get_logger("web_change_monitor")


def _short_diff(old: str, new: str, max_chars: int = 300) -> str:
    """Return a short human-readable summary of what changed."""
    old_lines = set(old.splitlines())
    new_lines = set(new.splitlines())
    added   = [l for l in new.splitlines() if l not in old_lines and l.strip()]
    removed = [l for l in old.splitlines() if l not in new_lines and l.strip()]
    parts = []
    if added:
        parts.append("+ " + " | ".join(added[:5]))
    if removed:
        parts.append("- " + " | ".join(removed[:5]))
    summary = "\n".join(parts)
    if len(summary) > max_chars:
        summary = summary[:max_chars] + "…"
    return summary or "(konten berubah)"


class WebChangeMonitor:
    """
    Background monitor for web page content changes.

    Usage:
        mon = WebChangeMonitor(on_status=..., on_change=...)
        mon.configure(url="https://...", interval_sec=300,
                      keyword="Stok habis", ai_analysis=True)
        mon.start()
        mon.stop()
    """

    def __init__(self, on_status=None, on_change=None):
        self._on_status  = on_status   # callback(str)
        self._on_change  = on_change   # callback(old_text, new_text, summary)
        self._stop_ev    = threading.Event()
        self._thread: threading.Thread | None = None

        self._cfg = {
            "url":          "",
            "interval_sec": 300,
            "keyword":      "",       # if set, watch for this keyword appearing/disappearing
            "ai_analysis":  False,    # call AI to explain the change
            "ai_key":       "",
            "ai_provider":  "openai",
            "ai_model":     "",
        }

        # State
        self._last_content: str  = ""
        self._last_hash:    str  = ""
        self._last_kw_found: bool | None = None
        self.last_change:   datetime | None = None
        self.last_check:    datetime | None = None
        self.check_count:   int  = 0
        self.change_count:  int  = 0
        self.running:       bool = False

    # ── Public API ─────────────────────────────────────────────────────────

    def configure(self, **kwargs):
        for k, v in kwargs.items():
            if k in self._cfg:
                self._cfg[k] = v

    def start(self):
        if self.running:
            return
        if not self._cfg["url"].strip():
            self._notify("URL belum diisi")
            return
        self.running = True
        self._stop_ev.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="WebChangeMonitor")
        self._thread.start()
        self._notify("Monitor dimulai — {}".format(self._cfg["url"][:60]))

    def stop(self):
        self.running = False
        self._stop_ev.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._notify("Monitor dihentikan.")

    def check_now(self):
        """Run one cycle immediately (blocking)."""
        self._run_cycle(first_run=(self._last_hash == ""))

    # ── Internal ───────────────────────────────────────────────────────────

    def _loop(self):
        self._run_cycle(first_run=True)
        while not self._stop_ev.wait(self._cfg["interval_sec"]):
            if not self.running:
                break
            self._run_cycle(first_run=False)

    def _run_cycle(self, first_run: bool = False):
        url = self._cfg["url"].strip()
        try:
            from modules.web_scraper import scrape_url
            self._notify("Mengecek {}…".format(url[:60]))
            new_text = scrape_url(url)
            new_hash = hashlib.md5(new_text.encode()).hexdigest()
            self.last_check  = datetime.now()
            self.check_count += 1

            keyword = self._cfg["keyword"].strip()

            if first_run:
                self._last_content  = new_text
                self._last_hash     = new_hash
                self._last_kw_found = (keyword.lower() in new_text.lower()) if keyword else None
                if keyword:
                    status = "keyword ditemukan" if self._last_kw_found else "keyword TIDAK ditemukan"
                    self._notify("Baseline OK — {} — {}".format(status, keyword))
                else:
                    self._notify("Baseline OK — {} karakter direkam".format(len(new_text)))
                return

            changed = False
            summary = ""

            if keyword:
                kw_found = keyword.lower() in new_text.lower()
                if kw_found != self._last_kw_found:
                    changed = True
                    if kw_found:
                        summary = "Keyword MUNCUL: '{}'".format(keyword)
                    else:
                        summary = "Keyword HILANG: '{}'".format(keyword)
                    self._last_kw_found = kw_found
            else:
                if new_hash != self._last_hash:
                    changed = True
                    summary = _short_diff(self._last_content, new_text)

            if changed:
                self.change_count += 1
                self.last_change   = datetime.now()
                self._notify("PERUBAHAN #{}: {}".format(self.change_count, summary[:80]))

                old_text = self._last_content
                self._last_content = new_text
                self._last_hash    = new_hash

                if self._cfg["ai_analysis"] and self._cfg["ai_key"]:
                    ai_summary = self._analyze_with_ai(old_text, new_text, summary)
                    full_summary = "{}\n\nAI: {}".format(summary, ai_summary)
                else:
                    full_summary = summary

                if self._on_change:
                    try:
                        self._on_change(old_text, new_text, full_summary)
                    except Exception:
                        pass
            else:
                self._notify("Tidak ada perubahan (cek #{})".format(self.check_count))

        except Exception as e:
            self._notify("ERROR: {}".format(str(e)[:100]))
            logger.exception("WebChangeMonitor cycle error")

    def _analyze_with_ai(self, old: str, new: str, diff: str) -> str:
        try:
            from modules.ai_client import call_ai
            prompt = (
                "Ini adalah perubahan konten halaman web:\n\n"
                "PERUBAHAN TERDETEKSI: {}\n\n"
                "KONTEN LAMA (awal):\n{}\n\n"
                "KONTEN BARU:\n{}\n\n"
                "Jelaskan dalam 2–3 kalimat apa yang berubah dan apakah ini penting."
            ).format(diff[:200], old[:800], new[:800])
            return call_ai(
                prompt=prompt,
                provider=self._cfg["ai_provider"],
                api_key=self._cfg["ai_key"],
                model=self._cfg["ai_model"] or None,
                max_tokens=300,
                system_prompt="Kamu adalah asisten analisis perubahan web. Jawab singkat dan jelas.",
            )
        except Exception as e:
            return "(AI gagal: {})".format(str(e)[:60])

    def _notify(self, msg: str):
        logger.info("[WebChangeMonitor] %s", msg)
        if self._on_status:
            try:
                self._on_status(msg)
            except Exception:
                pass
