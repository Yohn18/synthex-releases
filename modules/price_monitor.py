# -*- coding: utf-8 -*-
"""
modules/price_monitor.py - Monitor harga otomatis.

Mengambil data tabel dari halaman web secara terjadwal, lalu menulis ke
Google Sheet. Berjalan di background thread — browser utama user bisa
diminimize atau ditutup sama sekali, karena Synthex menggunakan browser
tersembunyi (headless Chrome) sendiri.

Dua mode pengambilan data:
  requests  — langsung fetch HTML (cepat, tanpa browser, cocok untuk halaman
              statis atau yang tidak butuh JavaScript).
  headless  — jalankan Chrome tersembunyi via CDP (untuk halaman dinamis/JS).
              Chrome tidak muncul di taskbar sama sekali.
"""

import json
import os
import socket
import subprocess
import threading
import time
import datetime

import requests as _req
from core.logger import get_logger

# ── Chrome path candidates ────────────────────────────────────────────────────
_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
]

# Data dir untuk headless Chrome (terpisah dari profil user)
_HEADLESS_PROFILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "headless_profile")


def _find_chrome():
    for p in _CHROME_PATHS:
        if os.path.exists(p):
            return p
    return None


def _free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class PriceMonitor:
    """
    Background price monitor.

    Lifecycle:
        pm = PriceMonitor(on_status=my_cb, on_data=my_data_cb)
        pm.configure(url=..., table_selector="table", ...)
        pm.start()
        ...
        pm.stop()
    """

    def __init__(self, on_status=None, on_data=None):
        self.logger      = get_logger("price_monitor")
        self._on_status  = on_status   # callback(str)
        self._on_data    = on_data     # callback(list[list[str]])
        self._stop_ev    = threading.Event()
        self._thread     = None
        self._session    = _req.Session()
        self._session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/124 Safari/537.36")
        })

        # Config (set via configure())
        self._cfg = {
            "url":            "",
            "btn_selector":   "",      # CSS selector tombol refresh (kosong = skip)
            "table_selector": "table", # CSS selector tabel
            "mode":           "requests",   # "requests" | "headless"
            "interval_sec":   300,     # default 5 menit
            "sheet_id":       "",
            "worksheet":      "Sheet1",
            "start_cell":     "A1",
            "clear_before":   True,    # hapus isi sheet sebelum isi ulang
        }

        # State
        self.last_data:   list        = []
        self.last_update: datetime.datetime | None = None
        self.last_error:  str         = ""
        self.cycle_count: int         = 0
        self.running:     bool        = False

    # ── Public API ────────────────────────────────────────────────────────────

    def configure(self, **kwargs):
        """Update any subset of config keys."""
        for k, v in kwargs.items():
            if k in self._cfg:
                self._cfg[k] = v

    def start(self):
        if self.running:
            return
        self.running = True
        self._stop_ev.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="PriceMonitor")
        self._thread.start()
        self._notify("Monitor dimulai (interval: {}s)".format(
            self._cfg["interval_sec"]))

    def stop(self):
        self.running = False
        self._stop_ev.set()
        self._notify("Monitor dihentikan.")

    def run_once(self):
        """Run one cycle immediately (blocking, for manual trigger)."""
        self._run_cycle()

    # ── Internal loop ────────────────────────────────────────────────────────

    def _loop(self):
        """Run cycle immediately, then repeat every interval_sec."""
        self._run_cycle()
        while not self._stop_ev.wait(timeout=self._cfg["interval_sec"]):
            if not self.running:
                break
            self._run_cycle()

    def _run_cycle(self):
        url = self._cfg.get("url", "").strip()
        if not url:
            self._notify("ERROR: URL belum diisi.")
            return

        self._notify("Mengambil data dari {}...".format(url[:60]))
        try:
            if self._cfg["mode"] == "headless":
                rows = self._fetch_headless(url)
            else:
                rows = self._fetch_requests(url)

            if not rows:
                self._notify("Tidak ada data tabel ditemukan di halaman.")
                return

            self.last_data   = rows
            self.last_update = datetime.datetime.now()
            self.cycle_count += 1
            self.last_error  = ""
            self._notify("Data diambil: {} baris x {} kolom".format(
                len(rows), max(len(r) for r in rows) if rows else 0))

            if self._on_data:
                self._on_data(rows)

            # Write to Google Sheets
            sheet_id = self._cfg.get("sheet_id", "").strip()
            if sheet_id:
                self._write_sheet(rows)

        except Exception as e:
            self.last_error = str(e)
            self._notify("ERROR: {}".format(str(e)[:120]))
            self.logger.exception("PriceMonitor cycle error")

    # ── Fetch: requests mode ──────────────────────────────────────────────────

    def _fetch_requests(self, url):
        """Fetch page with requests, parse table with BeautifulSoup."""
        from bs4 import BeautifulSoup

        resp = self._session.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        sel = self._cfg.get("table_selector", "table") or "table"
        table = soup.select_one(sel)
        if table is None:
            table = soup.find("table")
        if table is None:
            raise ValueError("Tabel tidak ditemukan. Coba mode Headless untuk halaman JS.")

        return self._parse_html_table(table)

    @staticmethod
    def _parse_html_table(table_el):
        rows = []
        for tr in table_el.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(cells)
        return rows

    # ── Fetch: headless Chrome mode ───────────────────────────────────────────

    def _fetch_headless(self, url):
        """
        Launch hidden Chrome, navigate to URL, optionally click a button,
        then extract table data via CDP/JavaScript.
        Chrome window never appears — runs completely in background.
        """
        chrome = _find_chrome()
        if chrome is None:
            raise RuntimeError(
                "Google Chrome tidak ditemukan. Install Chrome atau gunakan mode Requests.")

        port = _free_port()
        os.makedirs(_HEADLESS_PROFILE, exist_ok=True)

        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--remote-debugging-port={}".format(port),
            "--user-data-dir={}".format(_HEADLESS_PROFILE),
            "--window-size=1280,800",
            url,
        ]

        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        try:
            # Wait for Chrome to start CDP server
            self._wait_cdp(port, timeout=10)

            # Get WebSocket URL for the page tab
            targets = _req.get(
                "http://localhost:{}/json".format(port), timeout=5).json()
            ws_url = next(
                (t["webSocketDebuggerUrl"] for t in targets
                 if t.get("type") == "page"), None)
            if ws_url is None:
                raise RuntimeError("CDP: tidak ada page target")

            import websocket
            ws = websocket.create_connection(ws_url, timeout=15)

            def cdp(method, params=None):
                """Send CDP command, wait for response."""
                import json as _json
                mid = int(time.time() * 1000) % 999999
                ws.send(_json.dumps({"id": mid, "method": method,
                                     "params": params or {}}))
                for _ in range(30):
                    raw = ws.recv()
                    msg = _json.loads(raw)
                    if msg.get("id") == mid:
                        if "error" in msg:
                            raise RuntimeError("CDP {}: {}".format(
                                method, msg["error"].get("message", "")))
                        return msg.get("result", {})
                return {}

            # Wait for page to finish loading
            self._notify("Menunggu halaman selesai load...")
            time.sleep(2)

            # Enable Runtime
            cdp("Runtime.enable")

            # Click button if configured
            btn_sel = self._cfg.get("btn_selector", "").strip()
            if btn_sel:
                self._notify("Klik tombol: {}".format(btn_sel[:40]))
                safe_sel = btn_sel.replace("\\", "\\\\").replace("'", "\\'")
                result = cdp("Runtime.evaluate", {
                    "expression": (
                        "var _b = document.querySelector('{sel}');"
                        "_b ? (_b.click(), 'clicked') : 'not found'"
                    ).format(sel=safe_sel),
                    "returnByValue": True,
                })
                click_val = (result.get("result") or {}).get("value", "")
                self._notify("Tombol: {}".format(click_val))
                if click_val == "clicked":
                    time.sleep(2)   # Tunggu tabel refresh

            # Extract table via JavaScript
            tbl_sel = (self._cfg.get("table_selector", "table") or "table")
            safe_tbl = tbl_sel.replace("\\", "\\\\").replace("'", "\\'")

            js = r"""
(function() {
    var tbl = document.querySelector('""" + safe_tbl + r"""');
    if (!tbl) { return null; }
    var rows = [];
    tbl.querySelectorAll('tr').forEach(function(tr) {
        var cells = [];
        tr.querySelectorAll('td, th').forEach(function(td) {
            cells.push((td.innerText || td.textContent || '').trim());
        });
        if (cells.some(function(c){ return c.length > 0; })) {
            rows.push(cells);
        }
    });
    return JSON.stringify(rows);
})()
"""
            result = cdp("Runtime.evaluate", {
                "expression":    js.strip(),
                "returnByValue": True,
            })
            raw = (result.get("result") or {}).get("value")
            ws.close()

            if not raw:
                raise ValueError(
                    "Tabel '{}' tidak ditemukan di halaman. "
                    "Cek CSS selector.".format(tbl_sel))
            return json.loads(raw)

        finally:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try: proc.kill()
                except Exception: pass

    @staticmethod
    def _wait_cdp(port, timeout=10):
        """Block until Chrome's CDP HTTP server responds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                _req.get("http://localhost:{}/json/version".format(port), timeout=1)
                return
            except Exception:
                time.sleep(0.4)
        raise RuntimeError("Chrome CDP tidak merespons dalam {}s".format(timeout))

    # ── Google Sheets write ───────────────────────────────────────────────────

    def _write_sheet(self, rows):
        """Write rows to Google Sheet using existing sheets connector."""
        try:
            from modules.sheets.connector import connect_sheet, extract_sheet_id

            sheet_id  = extract_sheet_id(self._cfg.get("sheet_id", ""))
            worksheet = self._cfg.get("worksheet", "Sheet1")
            start     = self._cfg.get("start_cell", "A1").upper().strip() or "A1"

            if not sheet_id:
                self._notify("Sheet ID tidak valid.")
                return

            self._notify("Menulis ke Google Sheet...")
            ws, err = connect_sheet(sheet_id, worksheet)
            if err:
                self._notify("Sheet error: {}".format(err))
                return

            if self._cfg.get("clear_before", True):
                ws.clear()

            # Pad all rows to same length
            max_cols = max(len(r) for r in rows) if rows else 1
            padded   = [r + [""] * (max_cols - len(r)) for r in rows]

            ws.update(padded, start)
            self._notify("Sheet diperbarui: {} baris ditulis ke {}!{}".format(
                len(rows), worksheet, start))

        except ImportError as e:
            self._notify("Import error: {}".format(e))
        except Exception as e:
            self._notify("Gagal tulis sheet: {}".format(str(e)[:100]))

    # ── Utility ──────────────────────────────────────────────────────────────

    def _notify(self, msg):
        self.logger.info("[PriceMonitor] %s", msg)
        if self._on_status:
            try:
                self._on_status(msg)
            except Exception:
                pass
