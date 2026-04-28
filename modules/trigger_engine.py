# -*- coding: utf-8 -*-
"""
modules/trigger_engine.py
Rule engine for Android → PC automation via Tasker webhooks.

Rule schema:
    {
        "id": str,
        "name": str,
        "enabled": bool,
        "event_type": str | "*",          # "notification", "sms", "app_opened", "*"
        "conditions": [                    # ALL must match (AND)
            {"field": str, "op": str, "value": str}
        ],
        "actions": [
            {"type": "notify_desktop", "title": str, "body_field": str},
            {"type": "log_sheet",      "spreadsheet_id": str, "fields": [str]},
            {"type": "adb_tap",        "x": int, "y": int},
            {"type": "adb_swipe",      "x1": int, "y1": int, "x2": int, "y2": int, "ms": int},
            {"type": "adb_key",        "keycode": int | str},
            {"type": "adb_shell",      "cmd": str},
        ]
    }

Supported condition ops: eq, ne, contains, not_contains, starts_with, ends_with, regex
"""
import re
import subprocess
import threading
import time
from typing import Callable

from core.logger import get_logger

logger = get_logger("trigger_engine")


# ── Condition matching ────────────────────────────────────────────────────────

def _get_field(event: dict, field: str):
    """Support dot-notation like 'data.package'."""
    parts = field.split(".")
    val = event
    for p in parts:
        if not isinstance(val, dict):
            return None
        val = val.get(p)
    return val


def _match_condition(event: dict, cond: dict) -> bool:
    raw = _get_field(event, cond["field"])
    val = str(raw) if raw is not None else ""
    op  = cond.get("op", "eq")
    cv  = str(cond.get("value", ""))

    if op == "eq":           return val == cv
    if op == "ne":           return val != cv
    if op == "contains":     return cv.lower() in val.lower()
    if op == "not_contains": return cv.lower() not in val.lower()
    if op == "starts_with":  return val.lower().startswith(cv.lower())
    if op == "ends_with":    return val.lower().endswith(cv.lower())
    if op == "regex":
        try:                 return bool(re.search(cv, val, re.IGNORECASE))
        except Exception:    return False
    return False


def _matches_rule(event: dict, rule: dict) -> bool:
    et = rule.get("event_type", "*")
    if et != "*" and et != event.get("event_type", ""):
        return False
    return all(_match_condition(event, c) for c in rule.get("conditions", []))


# ── Action executors ──────────────────────────────────────────────────────────

def _resolve(template: str, event: dict) -> str:
    """Replace {field} placeholders with event values."""
    def repl(m):
        return str(_get_field(event, m.group(1)) or "")
    return re.sub(r"\{([\w.]+)\}", repl, template)


def _run_adb(adb_path: str, serial: str, args: list[str]) -> tuple[bool, str]:
    cmd = [adb_path]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            return True, r.stdout.strip()
        return False, r.stderr.strip()
    except Exception as exc:
        return False, str(exc)


def _exec_action(action: dict, event: dict, cfg: "TriggerConfig"):
    atype = action.get("type")

    if atype == "notify_desktop":
        try:
            from plyer import notification as _n
            title = _resolve(action.get("title", "Synthex"), event)
            body_field = action.get("body_field", "body")
            body = str(_get_field(event, body_field) or "")
            body = _resolve(action.get("body", body), event) if "body" in action else body
            _n.notify(
                title=title,
                message=body[:256],
                app_name="Synthex",
                timeout=8,
            )
        except Exception as exc:
            logger.warning("notify_desktop failed: %s", exc)

    elif atype == "log_sheet":
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            fields = action.get("fields", ["event_type", "body", "_ts"])
            row = [str(_get_field(event, f) or "") for f in fields]
            creds_file = action.get("credentials_file") or cfg.google_credentials_file
            sid = action.get("spreadsheet_id") or cfg.google_spreadsheet_id
            sheet_name = action.get("worksheet_name", "Sheet1")
            if not creds_file or not sid:
                logger.warning("log_sheet: no credentials_file or spreadsheet_id")
                return
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds  = Credentials.from_service_account_file(creds_file, scopes=scopes)
            gc     = gspread.authorize(creds)
            ws     = gc.open_by_key(sid).worksheet(sheet_name)
            ws.append_row(row)
        except Exception as exc:
            logger.warning("log_sheet failed: %s", exc)

    elif atype == "adb_tap":
        x = int(action.get("x", 0))
        y = int(action.get("y", 0))
        ok, err = _run_adb(cfg.adb_path, cfg.adb_serial, ["shell", "input", "tap", str(x), str(y)])
        if not ok:
            logger.warning("adb_tap failed: %s", err)

    elif atype == "adb_swipe":
        x1, y1 = int(action.get("x1", 0)), int(action.get("y1", 0))
        x2, y2 = int(action.get("x2", 0)), int(action.get("y2", 0))
        ms = int(action.get("ms", 300))
        ok, err = _run_adb(cfg.adb_path, cfg.adb_serial,
                           ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms)])
        if not ok:
            logger.warning("adb_swipe failed: %s", err)

    elif atype == "adb_key":
        kc = str(action.get("keycode", ""))
        ok, err = _run_adb(cfg.adb_path, cfg.adb_serial, ["shell", "input", "keyevent", kc])
        if not ok:
            logger.warning("adb_key failed: %s", err)

    elif atype == "adb_shell":
        cmd_str = _resolve(action.get("cmd", ""), event)
        if cmd_str:
            ok, err = _run_adb(cfg.adb_path, cfg.adb_serial, ["shell"] + cmd_str.split())
            if not ok:
                logger.warning("adb_shell failed: %s", err)

    else:
        logger.warning("unknown action type: %s", atype)


# ── Config ────────────────────────────────────────────────────────────────────

class TriggerConfig:
    def __init__(self, **kw):
        self.adb_path               = kw.get("adb_path", "adb")
        self.adb_serial             = kw.get("adb_serial", "")
        self.google_credentials_file = kw.get("google_credentials_file", "")
        self.google_spreadsheet_id  = kw.get("google_spreadsheet_id", "")


# ── Engine ────────────────────────────────────────────────────────────────────

class TriggerEngine:
    """
    Matches incoming events against rules and runs actions asynchronously.

    Usage:
        cfg = TriggerConfig(adb_path="adb")
        eng = TriggerEngine(cfg)
        eng.rules = [...]         # list of rule dicts
        eng.process(event_dict)
    """

    def __init__(self, cfg: TriggerConfig | None = None):
        self._cfg   = cfg or TriggerConfig()
        self._rules: list[dict] = []
        self._lock  = threading.Lock()
        self._history: list[dict] = []  # last 200 matched events
        self.on_match: Callable | None = None  # callback(rule, event, actions)

    @property
    def rules(self) -> list[dict]:
        with self._lock:
            return list(self._rules)

    @rules.setter
    def rules(self, val: list[dict]):
        with self._lock:
            self._rules = val

    @property
    def config(self) -> TriggerConfig:
        return self._cfg

    @config.setter
    def config(self, val: TriggerConfig):
        self._cfg = val

    def get_history(self) -> list[dict]:
        with self._lock:
            return list(self._history)

    def process(self, event: dict):
        """Called for each incoming webhook event. Runs in calling thread; actions dispatched async."""
        with self._lock:
            active = [r for r in self._rules if r.get("enabled", True)]

        for rule in active:
            if _matches_rule(event, rule):
                logger.info("Rule matched: %s → %s", rule.get("name"), event.get("event_type"))
                acts = rule.get("actions", [])
                self._record(rule, event)
                if self.on_match:
                    try:
                        self.on_match(rule, event, acts)
                    except Exception as exc:
                        logger.error("on_match error: %s", exc)
                t = threading.Thread(target=self._run_actions, args=(acts, event), daemon=True)
                t.start()

    def _run_actions(self, actions: list[dict], event: dict):
        for act in actions:
            try:
                _exec_action(act, event, self._cfg)
            except Exception as exc:
                logger.error("action error: %s", exc)

    def _record(self, rule: dict, event: dict):
        entry = {
            "_ts": time.time(),
            "rule_id": rule.get("id"),
            "rule_name": rule.get("name"),
            "event": event,
        }
        with self._lock:
            self._history.insert(0, entry)
            if len(self._history) > 200:
                self._history.pop()
