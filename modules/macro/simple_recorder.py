"""
modules/macro/simple_recorder.py - Simple click/keystroke recorder like OP Auto Clicker.

Records mouse clicks, keyboard input, and scroll events with timing delays.
Playback uses pyautogui to replay at the same screen coordinates.

Hybrid UIA mode: each click also captures Windows UIA element info (name,
automationId, className).  During playback the element is searched first via
UIA so the click lands on the correct button even when the window has moved or
the screen resolution changed.  Falls back to raw coordinates if UIA lookup
fails.
"""

import os
import threading
import time

from core.logger import get_logger


# ── UIA helpers (shared, lazy-init) ──────────────────────────────────────────

_uia_obj      = None
_uia_obj_lock = threading.Lock()
_UIA_DLL      = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"),
    "System32", "UIAutomationCore.dll"
)
_UIA_CLSID    = "{ff48dba4-60ef-4201-aa87-54103eef594e}"


def _init_uia():
    """Lazy-init IUIAutomation singleton (thread-safe)."""
    global _uia_obj
    if _uia_obj is not None:
        return _uia_obj
    try:
        with _uia_obj_lock:
            if _uia_obj is not None:
                return _uia_obj
            import comtypes, comtypes.client
            comtypes.client.GetModule(_UIA_DLL)
            from comtypes.gen import UIAutomationClient as _UIA
            _uia_obj = comtypes.client.CreateObject(
                _UIA_CLSID,
                clsctx=comtypes.CLSCTX_INPROC_SERVER,
                interface=_UIA.IUIAutomation,
            )
    except Exception:
        pass
    return _uia_obj


def _capture_uia(x, y):
    """
    Return UIA fingerprint dict for the element at screen position (x, y).
    Returns {} on any error so the caller can fall back to coordinates.

    Fingerprint keys:
        name        – CurrentName (button label, field placeholder, …)
        aid         – CurrentAutomationId
        cls         – CurrentClassName
        ctrl        – CurrentControlType (integer)
        loc_type    – CurrentLocalizedControlType (e.g. "button")
        proc        – CurrentProcessId (to disambiguate same name across apps)
    """
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass
    try:
        from comtypes.gen import UIAutomationClient as _UIA
        uia = _init_uia()
        if uia is None:
            return {}
        pt = _UIA.tagPOINT()
        pt.x, pt.y = int(x), int(y)
        el = uia.ElementFromPoint(pt)
        if el is None:
            return {}
        return {
            "name":     (el.CurrentName or "").strip()[:80],
            "aid":      (el.CurrentAutomationId or "").strip()[:80],
            "cls":      (el.CurrentClassName or "").strip()[:80],
            "ctrl":     el.CurrentControlType,
            "loc_type": (el.CurrentLocalizedControlType or "").strip(),
            "proc":     el.CurrentProcessId,
        }
    except Exception:
        return {}
    finally:
        try:
            import comtypes
            comtypes.CoUninitialize()
        except Exception:
            pass


def _uia_find_center(fingerprint):
    """
    Try to locate the element matching *fingerprint* on the current screen.
    Returns (cx, cy) center coords, or None if not found / ambiguous.

    Strategy:
      1. Build a condition from the best available identifier (aid > name+cls > name).
      2. Search from the desktop root.
      3. If multiple matches, pick the one whose bounding-rect centre is closest
         to the original recorded position (stored separately as fallback).
    """
    if not fingerprint:
        return None
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass
    try:
        from comtypes.gen import UIAutomationClient as _UIA

        UIA_AutomationIdPropertyId  = 30011
        UIA_NamePropertyId          = 30005
        UIA_ClassNamePropertyId     = 30012
        UIA_ControlTypePropertyId   = 30003
        TreeScope_Descendants       = 4

        uia  = _init_uia()
        if uia is None:
            return None
        root = uia.GetRootElement()

        aid      = fingerprint.get("aid", "")
        name     = fingerprint.get("name", "")
        cls      = fingerprint.get("cls", "")
        ctrl     = fingerprint.get("ctrl", 0)

        # Build the most specific condition we can
        cond = None
        if aid:
            cond = uia.CreatePropertyCondition(UIA_AutomationIdPropertyId, aid)
        elif name and cls:
            c_name = uia.CreatePropertyCondition(UIA_NamePropertyId, name)
            c_cls  = uia.CreatePropertyCondition(UIA_ClassNamePropertyId, cls)
            cond   = uia.CreateAndCondition(c_name, c_cls)
        elif name:
            cond = uia.CreatePropertyCondition(UIA_NamePropertyId, name)

        if cond is None:
            return None

        # Also restrict by ControlType when available
        if ctrl:
            c_ctrl = uia.CreatePropertyCondition(UIA_ControlTypePropertyId, ctrl)
            cond   = uia.CreateAndCondition(cond, c_ctrl)

        elements = root.FindAll(TreeScope_Descendants, cond)
        if elements is None or elements.Length == 0:
            return None

        proc_id = fingerprint.get("proc", 0)
        best = None
        best_area = None
        best_same_proc = False

        for i in range(elements.Length):
            el = elements.GetElement(i)
            if el is None:
                continue
            try:
                rect = el.CurrentBoundingRectangle
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if w <= 0 or h <= 0:
                    continue
                area = w * h
                same_proc = proc_id > 0 and (el.CurrentProcessId == proc_id)

                if best is None:
                    best = el; best_area = area; best_same_proc = same_proc
                elif same_proc and not best_same_proc:
                    best = el; best_area = area; best_same_proc = True
                elif same_proc == best_same_proc and area < best_area:
                    best = el; best_area = area
            except Exception:
                continue

        if best is None or (not best_same_proc and proc_id > 0):
            return None

        rect = best.CurrentBoundingRectangle
        cx = (rect.left + rect.right)  // 2
        cy = (rect.top  + rect.bottom) // 2
        return (cx, cy)

    except Exception:
        return None
    finally:
        try:
            import comtypes
            comtypes.CoUninitialize()
        except Exception:
            pass


class SimpleRecorder:
    """
    Records mouse clicks, key presses, and scroll events with delays.

    Actions format:
        {"type": "click",  "x": 450, "y": 320, "button": "left", "delay": 0.5,
         "uia": {"name": "Masuk", "aid": "btnLogin", "cls": "Button", ...}}
        {"type": "type",   "text": "hello", "delay": 0.2}
        {"type": "scroll", "x": 450, "y": 320, "amount": -3,    "delay": 0.1}

    The "uia" key is optional — absent on older recordings and on scroll events.
    """

    def __init__(self):
        self.logger = get_logger("simple_recorder")
        self._events     = []   # raw pynput events with timestamps
        self._actions    = []   # cleaned action list (returned by stop_recording)
        self._recording  = False
        self._paused     = False
        self._start_time = 0.0
        self._mouse_listener    = None
        self._keyboard_listener = None
        self._pending_text      = []   # accumulate consecutive key chars
        self._pending_text_time = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def start_recording(self):
        """Start listening for mouse events. Keyboard events are routed from
        the app-level keyboard listener to avoid two-listener crash on Windows."""
        from pynput import mouse

        self._events     = []
        self._actions    = []
        self._recording  = True
        self._paused     = False
        self._start_time = time.time()
        self.logger.info("Simple recording started.")

        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._keyboard_listener = None  # managed by app-level listener
        self._mouse_listener.start()

    def stop_recording(self):
        """Stop recording. Returns cleaned action list."""
        self._recording = False
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        # keyboard_listener is None (managed by app-level listener)
        self._flush_pending_text()
        self.logger.info(
            "Simple recording stopped. {} actions.".format(len(self._events)))
        return list(self._actions)

    def pause_recording(self):
        """Pause recording — events are ignored while paused."""
        self._paused = True
        self.logger.info("Recording paused.")

    def resume_recording(self):
        """Resume recording after a pause."""
        self._paused = False
        self._start_time = time.time() - (self._events[-1]["t"] if self._events else 0)
        self.logger.info("Recording resumed.")

    def get_actions(self):
        """Return the last recorded action list."""
        return list(self._actions)

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    def _elapsed(self):
        return time.time() - self._start_time

    def _on_click(self, x, y, button, pressed):
        if not self._recording or self._paused or not pressed:
            return
        t = self._elapsed()
        self._flush_pending_text(t)
        delay    = self._calc_delay(t)
        btn_name = getattr(button, "name", "left")

        # Capture UIA fingerprint asynchronously so pynput listener is not blocked
        action = {"type": "click", "x": x, "y": y,
                  "button": btn_name, "delay": round(delay, 3)}
        with self._lock:
            self._events.append({"t": t, "action": action})
            self._actions.append(action)

        def _async_uia(ax=x, ay=y, act=action):
            try:
                info = _capture_uia(ax, ay)
                if info:
                    with self._lock:
                        act["uia"] = info
            except Exception:
                pass
        threading.Thread(target=_async_uia, daemon=True).start()
        return  # action already appended above; skip append below

    def _on_scroll(self, x, y, dx, dy):
        if not self._recording or self._paused:
            return
        t = self._elapsed()
        self._flush_pending_text(t)
        delay = self._calc_delay(t)
        action = {"type": "scroll", "x": x, "y": y,
                  "amount": int(dy), "delay": round(delay, 3)}
        with self._lock:
            self._events.append({"t": t, "action": action})
            self._actions.append(action)

    def _on_key_press(self, key):
        if not self._recording or self._paused:
            return
        # Skip F5-F9 (global hotkeys) so they are not recorded as steps
        try:
            from pynput import keyboard as _kb
            if key in (_kb.Key.f5, _kb.Key.f6, _kb.Key.f7,
                       _kb.Key.f8, _kb.Key.f9):
                return
        except Exception:
            pass
        t = self._elapsed()
        # Try to get printable character
        try:
            char = key.char
            if char and char.isprintable():
                with self._lock:
                    if not self._pending_text:
                        self._pending_text_time = t
                    self._pending_text.append(char)
                return
            # Control-key combos produce non-printable chars — skip hotkeys
            if char is not None:
                return
        except AttributeError:
            pass
        # Special key (enter, backspace, etc.) - flush text first
        self._flush_pending_text(t)
        try:
            key_name = key.name  # e.g. "enter", "backspace"
        except AttributeError:
            key_name = str(key)
        delay = self._calc_delay(t)
        action = {"type": "key", "key": key_name, "delay": round(delay, 3)}
        with self._lock:
            self._events.append({"t": t, "action": action})
            self._actions.append(action)

    def _flush_pending_text(self, current_time=None):
        """Combine buffered chars into a single 'type' action."""
        with self._lock:
            if not self._pending_text:
                return
            text = "".join(self._pending_text)
            t    = self._pending_text_time
            self._pending_text = []
        if current_time is None:
            current_time = self._elapsed()
        delay = self._calc_delay(t)
        action = {"type": "type", "text": text, "delay": round(delay, 3)}
        with self._lock:
            self._events.append({"t": t, "action": action})
            self._actions.append(action)

    def _calc_delay(self, current_t):
        """Delay = time since last event, capped at 10s."""
        with self._lock:
            if not self._events:
                return round(current_t, 3)
            last_t = self._events[-1]["t"]
        return min(current_t - last_t, 10.0)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def play_recording(self, actions, speed=1.0, repeat=1,
                       on_step=None, stop_event=None, pause_event=None,
                       silent_mode=False, silent_click_fn=None):
        """
        Replay recorded actions using pyautogui.

        For click actions that have a "uia" fingerprint:
          1. Try to find the element on screen via Windows UIA.
          2. If found → click its current centre (works after window move/resize).
          3. If not found → fall back to recorded (x, y) coordinates.

        Args:
            actions:          List of action dicts from stop_recording().
            speed:            1.0 = normal, 0.5 = 2x faster, 2.0 = half speed.
            repeat:           How many times to repeat.
            on_step:          Callback(step_index, total, description) for UI updates.
            stop_event:       threading.Event - set to abort playback.
            pause_event:      threading.Event - set to pause playback.
            silent_mode:      If True, use silent_click_fn for click actions.
            silent_click_fn:  Callable(x, y, button) used when silent_mode is True.
        """
        import pyautogui

        total = len(actions) * repeat
        step  = 0

        for _rep in range(repeat):
            if _rep > 0:
                if stop_event and stop_event.is_set():
                    return
                time.sleep(0.5)
            for i, action in enumerate(actions):
                if stop_event and stop_event.is_set():
                    return
                while pause_event and pause_event.is_set():
                    if stop_event and stop_event.is_set():
                        return
                    time.sleep(0.05)

                delay = action.get("delay", 0) * speed
                if delay > 0:
                    time.sleep(delay)

                atype = action.get("type")
                desc  = self._action_desc(action)

                if on_step:
                    try:
                        on_step(step, total, desc)
                    except Exception:
                        pass

                try:
                    if atype == "click":
                        btn = action.get("button", "left")
                        cx, cy = action["x"], action["y"]
                        uia_fp = action.get("uia", {})
                        if uia_fp and uia_fp.get("proc"):
                            found = _uia_find_center(uia_fp)
                            if found:
                                cx, cy = found

                        if silent_mode and silent_click_fn:
                            silent_click_fn(cx, cy, btn)
                        else:
                            pyautogui.click(cx, cy, button=btn)

                    elif atype == "type":
                        text = action.get("text", "")
                        pasted = False
                        try:
                            import pyperclip
                            pyperclip.copy(text)
                            pyautogui.hotkey("ctrl", "v")
                            time.sleep(0.15)
                            pasted = True
                        except Exception:
                            pass
                        if not pasted:
                            # pyperclip unavailable or failed — fall back to typewrite
                            safe = text.encode("ascii", "ignore").decode("ascii")
                            if safe:
                                pyautogui.typewrite(safe, interval=0.05)

                    elif atype == "scroll":
                        pyautogui.scroll(action.get("amount", 0),
                                         x=action["x"], y=action["y"])

                    elif atype == "key":
                        key = action.get("key", "")
                        if key:
                            pyautogui.press(key)
                except Exception as exc:
                    self.logger.error("Playback step %d error: %s", step, exc, exc_info=True)
                    if stop_event and not stop_event.is_set():
                        pass  # continue to next step rather than crashing

                step += 1

    @staticmethod
    def _action_desc(action):
        atype = action.get("type", "")
        if atype == "click":
            uia = action.get("uia", {})
            label = uia.get("name") or uia.get("aid") or ""
            loc   = ' "{}"'.format(label[:20]) if label else ""
            return "Click{} {} at ({}, {})".format(
                loc, action.get("button", "left"),
                action.get("x", 0), action.get("y", 0))
        if atype == "type":
            return 'Type "{}"'.format(action.get("text", "")[:30])
        if atype == "scroll":
            return "Scroll {} at ({}, {})".format(
                action.get("amount", 0), action.get("x", 0), action.get("y", 0))
        if atype == "key":
            return "Key: {}".format(action.get("key", ""))
        return str(action)
