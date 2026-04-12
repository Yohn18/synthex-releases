"""
modules/macro/recorder.py - Mouse and keyboard macro recorder/player for Synthex.
"""

import json
import os
import time
import threading
from core.config import Config
from core.logger import get_logger


class MacroRecorder:
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger("macro")
        _project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.save_path = config.get("macro.save_path", os.path.join(_project_root, "macros"))
        self.playback_speed = config.get("macro.playback_speed", 1.0)
        self._events: list = []
        self._recording = False
        self._start_time: float = 0.0
        self._mouse_listener = None
        self._keyboard_listener = None

        os.makedirs(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "macros"), exist_ok=True)

    def start_recording(self):
        from pynput import mouse, keyboard
        self._events = []
        self._recording = True
        self._start_time = time.time()
        self.logger.info("Macro recording started.")

        if self.config.get("macro.record_mouse", True):
            self._mouse_listener = mouse.Listener(
                on_move=self._on_move,
                on_click=self._on_click,
                on_scroll=self._on_scroll,
            )
            self._mouse_listener.start()

        if self.config.get("macro.record_keyboard", True):
            self._keyboard_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._keyboard_listener.start()

    def stop_recording(self):
        self._recording = False
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()
        self.logger.info(f"Macro recording stopped. {len(self._events)} events captured.")

    def save(self, name: str):
        path = os.path.join(self.save_path, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._events, f, indent=2)
        self.logger.info(f"Macro saved: {path}")

    def load(self, name: str) -> list:
        path = os.path.join(self.save_path, f"{name}.json")
        with open(path, "r", encoding="utf-8") as f:
            self._events = json.load(f)
        self.logger.info(f"Macro loaded: {path} ({len(self._events)} events)")
        return self._events

    def play(self, name: str = None):
        if name:
            self.load(name)
        self.logger.info("Macro playback started.")
        prev_time = 0.0
        for event in self._events:
            delay = (event["time"] - prev_time) / self.playback_speed
            time.sleep(max(0, delay))
            prev_time = event["time"]
            self._replay_event(event)
        self.logger.info("Macro playback complete.")

    def _replay_event(self, event: dict):
        import pyautogui
        etype = event.get("type")
        if etype == "move":
            pyautogui.moveTo(event["x"], event["y"])
        elif etype == "click":
            btn = event.get("button", "left")
            if event.get("pressed"):
                pyautogui.mouseDown(event["x"], event["y"], button=btn)
            else:
                pyautogui.mouseUp(event["x"], event["y"], button=btn)
        elif etype == "key_press":
            pyautogui.keyDown(event.get("key", ""))
        elif etype == "key_release":
            pyautogui.keyUp(event.get("key", ""))

    def _record(self, event: dict):
        event["time"] = time.time() - self._start_time
        self._events.append(event)

    def _on_move(self, x, y):
        self._record({"type": "move", "x": x, "y": y})

    def _on_click(self, x, y, button, pressed):
        self._record({"type": "click", "x": x, "y": y, "button": button.name, "pressed": pressed})

    def _on_scroll(self, x, y, dx, dy):
        self._record({"type": "scroll", "x": x, "y": y, "dx": dx, "dy": dy})

    def _on_key_press(self, key):
        self._record({"type": "key_press", "key": str(key)})

    def _on_key_release(self, key):
        self._record({"type": "key_release", "key": str(key)})
