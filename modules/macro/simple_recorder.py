"""
modules/macro/simple_recorder.py - Simple click/keystroke recorder like OP Auto Clicker.

Records mouse clicks, keyboard input, and scroll events with timing delays.
Playback uses pyautogui to replay at the same screen coordinates.
"""

import threading
import time

from core.logger import get_logger


class SimpleRecorder:
    """
    Records mouse clicks, key presses, and scroll events with delays.

    Actions format:
        {"type": "click",  "x": 450, "y": 320, "button": "left", "delay": 0.5}
        {"type": "type",   "text": "hello", "delay": 0.2}
        {"type": "scroll", "x": 450, "y": 320, "amount": -3,    "delay": 0.1}
    """

    def __init__(self):
        self.logger = get_logger("simple_recorder")
        self._events     = []   # raw pynput events with timestamps
        self._actions    = []   # cleaned action list (returned by stop_recording)
        self._recording  = False
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
        """Start listening for mouse and keyboard events."""
        from pynput import mouse, keyboard

        self._events     = []
        self._actions    = []
        self._recording  = True
        self._start_time = time.time()
        self.logger.info("Simple recording started.")

        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
        )
        self._mouse_listener.start()
        self._keyboard_listener.start()

    def stop_recording(self):
        """Stop recording. Returns cleaned action list."""
        self._recording = False
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        if self._keyboard_listener:
            try:
                self._keyboard_listener.stop()
            except Exception:
                pass
        self._flush_pending_text()
        self.logger.info(
            "Simple recording stopped. {} actions.".format(len(self._events)))
        return list(self._actions)

    def get_actions(self):
        """Return the last recorded action list."""
        return list(self._actions)

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    def _elapsed(self):
        return time.time() - self._start_time

    def _on_click(self, x, y, button, pressed):
        if not self._recording or not pressed:
            return
        t = self._elapsed()
        self._flush_pending_text(t)
        delay = self._calc_delay(t)
        btn_name = getattr(button, "name", "left")
        action = {"type": "click", "x": x, "y": y,
                  "button": btn_name, "delay": round(delay, 3)}
        with self._lock:
            self._events.append({"t": t, "action": action})
            self._actions.append(action)

    def _on_scroll(self, x, y, dx, dy):
        if not self._recording:
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
        if not self._recording:
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
            # Control-key combos (Ctrl+1, Ctrl+3, etc.) produce non-printable
            # chars; skip them so hotkeys are not recorded as steps.
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
        Replay recorded actions using pyautogui (or Playwright CDP in silent mode).

        Args:
            actions:          List of action dicts from stop_recording().
            speed:            1.0 = normal, 0.5 = 2x faster, 2.0 = half speed.
            repeat:           How many times to repeat.
            on_step:          Callback(step_index, total, description) for UI updates.
            stop_event:       threading.Event - set to abort playback.
            pause_event:      threading.Event - set to pause playback.
            silent_mode:      If True, use silent_click_fn for click actions.
            silent_click_fn:  Callable(x, y, button) used when silent_mode is True.
                              Clicks via CDP so cursor does not move.
        """
        import pyautogui
        pyautogui.FAILSAFE = False

        total = len(actions) * repeat
        step  = 0

        for _rep in range(repeat):
            if _rep > 0:
                # Pause between repeat cycles
                time.sleep(0.5)
            for i, action in enumerate(actions):
                if stop_event and stop_event.is_set():
                    return
                while pause_event and pause_event.is_set():
                    if stop_event and stop_event.is_set():
                        return
                    time.sleep(0.05)

                # Wait the recorded delay (adjusted for speed)
                delay = action.get("delay", 0) * speed
                if delay > 0:
                    time.sleep(delay)

                atype = action.get("type")
                desc  = self._action_desc(action)

                if on_step:
                    on_step(step, total, desc)

                if atype == "click":
                    btn = action.get("button", "left")
                    if silent_mode and silent_click_fn:
                        # CDP dispatch - cursor stays in place
                        silent_click_fn(action["x"], action["y"], btn)
                    else:
                        pyautogui.click(action["x"], action["y"], button=btn)

                elif atype == "type":
                    pyautogui.typewrite(action.get("text", ""),
                                       interval=0.03)

                elif atype == "scroll":
                    pyautogui.scroll(action.get("amount", 0),
                                     x=action["x"], y=action["y"])

                elif atype == "key":
                    key = action.get("key", "")
                    if key:
                        pyautogui.press(key)

                step += 1

    @staticmethod
    def _action_desc(action):
        atype = action.get("type", "")
        if atype == "click":
            return "Click {} at ({}, {})".format(
                action.get("button", "left"), action.get("x", 0), action.get("y", 0))
        if atype == "type":
            return 'Type "{}"'.format(action.get("text", "")[:30])
        if atype == "scroll":
            return "Scroll {} at ({}, {})".format(
                action.get("amount", 0), action.get("x", 0), action.get("y", 0))
        if atype == "key":
            return "Key: {}".format(action.get("key", ""))
        return str(action)
