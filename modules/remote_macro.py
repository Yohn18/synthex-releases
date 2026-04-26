# -*- coding: utf-8 -*-
"""
modules/remote_macro.py
Macro engine for Synthex Remote — inactivity detection + auto-actions via ADB.

Usage:
    engine = MacroEngine(adb_manager)
    engine.set_serial("device_serial")
    engine.set_rules([
        {"delay_sec": 180, "action": "swipe_down"},
        {"delay_sec": 300, "action": "tap", "x": 540, "y": 960},
    ])
    engine.start()
    engine.ping()   # call this on any user interaction
    engine.stop()
"""
import threading
import time
from core.logger import get_logger

logger = get_logger("remote_macro")

ACTION_LABELS = {
    "tap":          "Tap koordinat",
    "swipe_down":   "Swipe ke bawah",
    "swipe_up":     "Swipe ke atas",
    "swipe_left":   "Swipe ke kiri",
    "swipe_right":  "Swipe ke kanan",
    "swipe_custom": "Swipe custom",
    "key_home":     "Tombol Home",
    "key_back":     "Tombol Back",
    "key_menu":     "Tombol Recent",
    "key_power":    "Tombol Power",
    "key_wakeup":   "Wake Up Layar",
}

_KEY_CODES = {
    "key_home":   3,
    "key_back":   4,
    "key_menu":   187,
    "key_power":  26,
    "key_wakeup": 224,
}

_SWIPE_PRESETS = {
    "swipe_down":  (540, 300, 540, 1200, 350),
    "swipe_up":    (540, 1200, 540, 300, 350),
    "swipe_left":  (900, 960, 100, 960, 300),
    "swipe_right": (100, 960, 900, 960, 300),
}


class MacroEngine:
    """
    Watches for inactivity and fires configured actions via ADB shell input.

    Each rule:
        delay_sec   int    — inactivity seconds before firing (default 180)
        action      str    — one of ACTION_LABELS keys
        x, y        int    — coordinates for "tap"
        x1,y1,x2,y2 int   — for "swipe_custom"
        ms          int    — swipe duration ms (default 350)
        label       str    — human-readable name (optional)
        enabled     bool   — False = skip this rule
    """

    def __init__(self, adb_manager):
        self._adb       = adb_manager
        self._serial    = ""
        self._serial_fn: callable | None = None  # optional; called at execute time
        self._rules: list[dict] = []
        self._stop   = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_activity = time.monotonic()
        self._fired: dict[int, float] = {}
        self._lock   = threading.Lock()
        self.on_fire: callable | None = None   # callback(rule) on each fire

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_serial(self, serial: str):
        self._serial = serial

    def set_rules(self, rules: list[dict]):
        with self._lock:
            self._rules = list(rules)
            self._fired.clear()

    def ping(self):
        """Reset inactivity timer — call on any user interaction."""
        self._last_activity = time.monotonic()
        with self._lock:
            self._fired.clear()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._last_activity = time.monotonic()
        with self._lock:
            self._fired.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="SynthexMacro")
        self._thread.start()
        logger.info("MacroEngine started — serial=%s rules=%d",
                    self._serial, len(self._rules))

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        logger.info("MacroEngine stopped.")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_activity

    def fire_now(self, rule: dict):
        """Manually trigger a rule immediately (from UI)."""
        threading.Thread(target=self._execute, args=(rule,),
                         daemon=True).start()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop.wait(1.0):
            idle = time.monotonic() - self._last_activity
            with self._lock:
                rules = list(self._rules)
                fired = dict(self._fired)

            for i, rule in enumerate(rules):
                if not rule.get("enabled", True):
                    continue
                delay = rule.get("delay_sec", 180)
                if idle < delay:
                    continue
                last_fire = fired.get(i, 0)
                # Re-fire no sooner than delay seconds after last fire
                if time.monotonic() - last_fire < delay:
                    continue
                with self._lock:
                    self._fired[i] = time.monotonic()
                self._execute(rule)

    def _execute(self, rule: dict):
        action = rule.get("action", "tap")
        serial = self._serial_fn() if self._serial_fn else self._serial
        s_args = ["-s", serial] if serial else []
        logger.info("MacroEngine firing: %s serial=%s", action, serial)

        try:
            if action == "tap":
                x = int(rule.get("x", 540))
                y = int(rule.get("y", 960))
                self._adb._run(*s_args, "shell", "input", "tap", str(x), str(y))

            elif action in _SWIPE_PRESETS:
                x1, y1, x2, y2, ms = _SWIPE_PRESETS[action]
                self._adb._run(*s_args, "shell", "input", "swipe",
                               str(x1), str(y1), str(x2), str(y2), str(ms))

            elif action == "swipe_custom":
                x1 = int(rule.get("x1", 540)); y1 = int(rule.get("y1", 300))
                x2 = int(rule.get("x2", 540)); y2 = int(rule.get("y2", 1200))
                ms = int(rule.get("ms", 350))
                self._adb._run(*s_args, "shell", "input", "swipe",
                               str(x1), str(y1), str(x2), str(y2), str(ms))

            elif action in _KEY_CODES:
                kc = _KEY_CODES[action]
                self._adb._run(*s_args, "shell", "input", "keyevent", str(kc))

            if self.on_fire:
                try:
                    self.on_fire(rule)
                except Exception:
                    pass

        except Exception as e:
            logger.warning("MacroEngine execute error: %s", e)
