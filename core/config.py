"""
core/config.py - Configuration loader and accessor for Synthex.
"""

import json
import os
import tempfile
import threading
from typing import Any
from core.paths import synthex_dir as _get_synthex_dir


class Config:
    def __init__(self, path: str = "config.json"):
        # Resolve relative paths to the Synthex data dir (next to exe when frozen)
        if not os.path.isabs(path):
            synthex_dir = _get_synthex_dir()
            os.makedirs(synthex_dir, exist_ok=True)
            appdata_path = os.path.join(synthex_dir, os.path.basename(path))
            # Always sync app.version from bundled config so the exe version
            # is always authoritative (prevents stale AppData triggering updates).
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            bundled = os.path.join(project_root, path)
            if not os.path.exists(appdata_path):
                if os.path.exists(bundled):
                    import shutil
                    shutil.copy2(bundled, appdata_path)
            elif os.path.exists(bundled):
                try:
                    with open(bundled, "r", encoding="utf-8") as _bf:
                        _bdata = json.load(_bf)
                    _bundled_ver = _bdata.get("app", {}).get("version")
                    if _bundled_ver:
                        with open(appdata_path, "r", encoding="utf-8") as _af:
                            _adata = json.load(_af)
                        if _adata.get("app", {}).get("version") != _bundled_ver:
                            _adata.setdefault("app", {})["version"] = _bundled_ver
                            with open(appdata_path, "w", encoding="utf-8") as _af:
                                json.dump(_adata, _af, indent=2)
                except Exception:
                    pass
            path = appdata_path
        self._path = path
        self._data: dict = {}
        self._lock = threading.Lock()
        self.load()

    def load(self):
        if not os.path.exists(self._path):
            raise FileNotFoundError(f"Config file not found: {self._path}")
        with open(self._path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def save(self):
        dir_ = os.path.dirname(self._path)
        with self._lock:
            fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2)
                os.replace(tmp, self._path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

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
