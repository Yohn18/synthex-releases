# -*- coding: utf-8 -*-
"""
modules/phone_files.py
ADB-based file manager + auto photo backup for Android devices.
"""
import os
import re
import threading
from datetime import datetime
from core.logger import get_logger

logger = get_logger("phone_files")

_PICTURES_DIR = os.path.join(os.path.expanduser("~"), "Pictures", "Synthex Backup")


# ─────────────────────────────────────────────────────────────────────────────
# File Manager
# ─────────────────────────────────────────────────────────────────────────────

class PhoneFileManager:
    """Browse, pull, push files on Android via ADB."""

    def __init__(self, adb_manager):
        self.adb  = adb_manager
        self._cur = "/sdcard"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self, serial: str, *args, timeout: int = 15):
        return self.adb._run("-s", serial, *args, timeout=timeout)

    # ── Directory listing ─────────────────────────────────────────────────────

    def ls(self, serial: str, path: str = None) -> list:
        """
        Return list of dicts: {name, is_dir, size, modified, path}
        """
        path = path or self._cur
        rc, out, err = self._run(serial, "shell",
                                 "ls", "-la", "--color=never", path)
        if rc != 0:
            raise RuntimeError("ls gagal: {}".format(err or out))

        entries = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("total"):
                continue
            parts = line.split()
            if len(parts) < 8:
                continue
            perms = parts[0]
            is_dir = perms.startswith("d")
            is_link = perms.startswith("l")
            try:
                size = int(parts[4]) if not is_dir else 0
            except (ValueError, IndexError):
                size = 0
            date_str = " ".join(parts[5:7])
            name_raw = " ".join(parts[7:])
            name = name_raw.split(" -> ")[0] if is_link else name_raw
            if name in (".", ".."):
                continue
            entries.append({
                "name":     name,
                "is_dir":   is_dir or is_link,
                "size":     size,
                "modified": date_str,
                "path":     "{}/{}".format(path.rstrip("/"), name),
                "perms":    perms,
            })

        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return entries

    def cd(self, path: str):
        self._cur = path

    @property
    def cwd(self) -> str:
        return self._cur

    # ── Transfer ──────────────────────────────────────────────────────────────

    def pull(self, serial: str, remote_path: str, local_dir: str,
             progress_cb=None) -> str:
        """Pull file from phone to local_dir. Returns local path."""
        os.makedirs(local_dir, exist_ok=True)
        fname = os.path.basename(remote_path.rstrip("/"))
        local = os.path.join(local_dir, fname)
        if progress_cb:
            progress_cb("Mengunduh {}...".format(fname))
        rc, out, err = self._run(serial, "pull", remote_path, local, timeout=120)
        if rc != 0:
            raise RuntimeError("pull gagal: {}".format(err or out))
        if progress_cb:
            progress_cb("Selesai: {}".format(local))
        logger.info("pull %s -> %s", remote_path, local)
        return local

    def push(self, serial: str, local_path: str, remote_dir: str,
             progress_cb=None) -> str:
        """Push local file to phone. Returns remote path."""
        fname  = os.path.basename(local_path)
        remote = "{}/{}".format(remote_dir.rstrip("/"), fname)
        if progress_cb:
            progress_cb("Mengunggah {}...".format(fname))
        rc, out, err = self._run(serial, "push", local_path, remote, timeout=120)
        if rc != 0:
            raise RuntimeError("push gagal: {}".format(err or out))
        if progress_cb:
            progress_cb("Selesai: {}".format(remote))
        logger.info("push %s -> %s", local_path, remote)
        return remote

    def delete(self, serial: str, remote_path: str) -> bool:
        rc, _, err = self._run(serial, "shell", "rm", "-f", remote_path)
        if rc != 0:
            raise RuntimeError("delete gagal: {}".format(err))
        return True

    def mkdir(self, serial: str, remote_path: str) -> bool:
        rc, _, err = self._run(serial, "shell", "mkdir", "-p", remote_path)
        return rc == 0

    def get_storage_info(self, serial: str) -> dict:
        """Return {total_gb, used_gb, free_gb}."""
        rc, out, _ = self._run(serial, "shell", "df", "/sdcard")
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] not in ("Filesystem",):
                try:
                    total = int(parts[1]) / 1024 / 1024
                    used  = int(parts[2]) / 1024 / 1024
                    free  = int(parts[3]) / 1024 / 1024
                    return {"total_gb": round(total, 1),
                            "used_gb":  round(used,  1),
                            "free_gb":  round(free,  1)}
                except (ValueError, IndexError):
                    continue
        return {"total_gb": 0, "used_gb": 0, "free_gb": 0}


# ─────────────────────────────────────────────────────────────────────────────
# Auto Photo Backup
# ─────────────────────────────────────────────────────────────────────────────

class PhotoBackup:
    """
    Incrementally backup DCIM photos from Android to PC.
    Only copies files not already present locally.
    """

    DCIM_PATH = "/sdcard/DCIM"

    def __init__(self, adb_manager, save_dir: str = None):
        self.adb      = adb_manager
        self.save_dir = save_dir or _PICTURES_DIR
        self._running = False
        self._thread  = None

    # ── Public ────────────────────────────────────────────────────────────────

    def backup(self, serial: str, progress_cb=None, done_cb=None,
               subfolders: bool = True) -> dict:
        """
        Sync photos in background. Returns immediately.
        progress_cb(message: str) called during transfer.
        done_cb(result: dict) called when finished.
        """
        self._running = True
        self._thread  = threading.Thread(
            target=self._run_backup,
            args=(serial, progress_cb, done_cb, subfolders),
            daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _list_phone_files(self, serial: str, path: str) -> list:
        """Recursively list files under path on phone."""
        rc, out, _ = self.adb._run(
            "-s", serial, "shell",
            "find", path, "-type", "f",
            "-name", "*.jpg", "-o",
            "-name", "*.jpeg", "-o",
            "-name", "*.png", "-o",
            "-name", "*.mp4", "-o",
            "-name", "*.mov",
            timeout=30)
        if rc != 0:
            return []
        return [l.strip() for l in out.splitlines() if l.strip()]

    def _run_backup(self, serial: str, progress_cb, done_cb, subfolders: bool):
        result = {"copied": 0, "skipped": 0, "failed": 0, "save_dir": self.save_dir}
        try:
            if progress_cb:
                progress_cb("Membaca daftar foto di HP...")

            files = self._list_phone_files(serial, self.DCIM_PATH)
            total = len(files)

            if progress_cb:
                progress_cb("Ditemukan {} file media".format(total))

            for i, remote in enumerate(files):
                if not self._running:
                    break
                rel   = remote.replace(self.DCIM_PATH + "/", "")
                parts = rel.split("/")
                sub   = os.path.join(self.save_dir, *parts[:-1]) if subfolders else self.save_dir
                local = os.path.join(sub, parts[-1])

                if os.path.exists(local):
                    result["skipped"] += 1
                    continue

                os.makedirs(sub, exist_ok=True)
                if progress_cb:
                    progress_cb("[{}/{}] Backup: {}".format(i + 1, total, parts[-1]))

                rc, _, err = self.adb._run(
                    "-s", serial, "pull", remote, local, timeout=60)
                if rc == 0:
                    result["copied"] += 1
                else:
                    result["failed"] += 1
                    logger.warning("backup pull gagal: %s — %s", remote, err)

        except Exception as e:
            logger.error("backup error: %s", e)
            result["error"] = str(e)
        finally:
            self._running = False
            if done_cb:
                done_cb(result)
