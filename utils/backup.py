# -*- coding: utf-8 -*-
"""
utils/backup.py - Auto-backup system for Synthex.

Creates daily ZIP backups of critical data files and rotates to keep
only the most recent N backups.
"""

import os
import zipfile
from datetime import datetime

from core.logger import get_logger

_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKUP_DIR = os.path.join(_ROOT, "backups")

# Files to include in each backup (relative to _ROOT); missing files are skipped.
_BACKUP_FILES = [
    os.path.join("data", "user_data.json"),
    os.path.join("data", "jobs.db"),
    "credentials.json",
]

logger = get_logger("backup")


class AutoBackup:
    def __init__(self):
        os.makedirs(_BACKUP_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------

    def create_backup(self) -> str:
        """Create a backup ZIP for today.

        Returns the path to the created (or already-existing) backup file.
        If a backup for today already exists it is returned without
        overwriting.
        """
        date_str  = datetime.now().strftime("%Y-%m-%d")
        filename  = f"synthex_backup_{date_str}.zip"
        dest_path = os.path.join(_BACKUP_DIR, filename)

        if os.path.exists(dest_path):
            logger.info("[Backup] Today's backup already exists: %s", filename)
            return dest_path

        added = []
        try:
            with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for rel_path in _BACKUP_FILES:
                    abs_path = os.path.join(_ROOT, rel_path)
                    if os.path.exists(abs_path):
                        zf.write(abs_path, rel_path)
                        added.append(rel_path)
                    else:
                        logger.debug("[Backup] Skipping missing file: %s", rel_path)
        except Exception as exc:
            logger.error("[Backup] Failed to create backup: %s", exc)
            if os.path.exists(dest_path):
                os.remove(dest_path)
            return ""

        logger.info("[Backup] Created backup %s (%d file(s))", filename, len(added))
        self.cleanup_old_backups()
        return dest_path

    def restore_backup(self, backup_path: str) -> bool:
        """Extract *backup_path* into the project root, overwriting existing files.

        Returns True on success, False on failure.
        """
        if not os.path.exists(backup_path):
            logger.error("[Backup] Restore failed – file not found: %s", backup_path)
            return False
        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                zf.extractall(_ROOT)
            logger.info("[Backup] Restored from %s", os.path.basename(backup_path))
            return True
        except Exception as exc:
            logger.error("[Backup] Restore error: %s", exc)
            return False

    def list_backups(self) -> list:
        """Return a list of dicts describing available backups, newest first.

        Each dict has:
          - path  : absolute path to the ZIP
          - name  : filename
          - date  : datetime object parsed from the filename
          - size  : file size in bytes
        """
        results = []
        for fname in sorted(os.listdir(_BACKUP_DIR), reverse=True):
            if not fname.startswith("synthex_backup_") or not fname.endswith(".zip"):
                continue
            fpath = os.path.join(_BACKUP_DIR, fname)
            try:
                date_part = fname[len("synthex_backup_"):-len(".zip")]
                date_obj  = datetime.strptime(date_part, "%Y-%m-%d")
            except ValueError:
                date_obj = None
            results.append({
                "path": fpath,
                "name": fname,
                "date": date_obj,
                "size": os.path.getsize(fpath),
            })
        return results

    def cleanup_old_backups(self, keep: int = 7):
        """Delete backups beyond the *keep* most recent ones."""
        backups = self.list_backups()   # already newest-first
        for old in backups[keep:]:
            try:
                os.remove(old["path"])
                logger.info("[Backup] Removed old backup: %s", old["name"])
            except Exception as exc:
                logger.warning("[Backup] Could not remove %s: %s", old["name"], exc)

    # ------------------------------------------------------------------
    #  Convenience
    # ------------------------------------------------------------------

    def last_backup_label(self) -> str:
        """Return a human-readable string for when the last backup was made."""
        backups = self.list_backups()
        if not backups:
            return "Never"
        latest = backups[0]
        if latest["date"]:
            today = datetime.now().date()
            if latest["date"].date() == today:
                mtime = os.path.getmtime(latest["path"])
                t     = datetime.fromtimestamp(mtime)
                return f"Today {t.strftime('%H:%M')}"
            return latest["date"].strftime("%Y-%m-%d")
        return latest["name"]
