"""
core/config.py - Configuration loader and accessor for Synthex.
"""

import json
import os
from typing import Any


class Config:
    def __init__(self, path: str = "config.json"):
        # Resolve relative paths to AppData\Synthex so the EXE can write there
        if not os.path.isabs(path):
            appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
            synthex_dir = os.path.join(appdata, "Synthex")
            os.makedirs(synthex_dir, exist_ok=True)
            # Seed from bundled config if AppData copy doesn't exist yet
            appdata_path = os.path.join(synthex_dir, os.path.basename(path))
            if not os.path.exists(appdata_path):
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                bundled = os.path.join(project_root, path)
                if os.path.exists(bundled):
                    import shutil
                    shutil.copy2(bundled, appdata_path)
            path = appdata_path
        self._path = path
        self._data: dict = {}
        self.load()

    def load(self):
        if not os.path.exists(self._path):
            raise FileNotFoundError(f"Config file not found: {self._path}")
        with open(self._path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-notation access: config.get('browser.headless')"""
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any):
        """Dot-notation setter: config.set('browser.headless', True)"""
        keys = key.split(".")
        data = self._data
        for k in keys[:-1]:
            data = data.setdefault(k, {})
        data[keys[-1]] = value

    def section(self, name: str) -> dict:
        return self._data.get(name, {})

    def __repr__(self):
        return f"<Config path={self._path}>"
