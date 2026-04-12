# -*- coding: utf-8 -*-
"""
core/engine.py - Central orchestration engine for Synthex.
Modules are initialized lazily after login via init_modules().
"""

import threading
import time
from datetime import datetime

from core.config import Config
from core.logger import get_logger
from ui.app import SynthexApp

# Module-level engine reference used by APScheduler callbacks (must be picklable).
_engine_ref = None


def _run_scheduled_job(task_id: str):
    """Called by APScheduler when a scheduled task fires.

    Must be a module-level function so APScheduler can pickle/unpickle it.
    """
    if _engine_ref is None:
        return
    tasks = _engine_ref.app._ud.tasks
    task = next((t for t in tasks if str(t.get("id")) == str(task_id)), None)
    if task is None or not task.get("enabled", True):
        return
    _engine_ref.logger.info(
        "[Scheduler] Auto-running task '%s'", task.get("name", task_id))
    _engine_ref.run_smart_task(task, enable_retry=True)


class Engine:
    def __init__(self, config: Config):
        global _engine_ref
        self.config = config
        self.logger = get_logger("engine", config.get("app.log_level", "INFO"))

        # Modules are None until init_modules() is called
        self.browser     = None
        self.sheets      = None
        self.macro       = None
        self.scheduler   = None
        self.smart_macro = None

        self.app = SynthexApp(config, self)
        self._running = False
        _engine_ref = self

    # -- Module initialization (called during loading screen) --
    def init_modules(self, progress_cb=None):
        """Initialize all automation modules.

        progress_cb(step, total, name) is called before each module so the UI
        can update a progress bar.  All heavy imports live inside factory lambdas
        so nothing loads until the module is actually instantiated.
        """
        def _make_browser():
            from modules.browser.actions import BrowserActions
            return BrowserActions(self.config)

        def _make_macro():
            from modules.macro.recorder import MacroRecorder
            return MacroRecorder(self.config)

        def _make_scheduler():
            from modules.scheduler.jobs import JobScheduler
            return JobScheduler(self.config)

        def _make_smart_macro():
            from modules.macro.smart_macro import SmartMacro
            def _notify(msg):
                if self.app and self.app._root:
                    self.app._root.after(0, lambda m=msg: self.app._show_toast(m))
            return SmartMacro(engine=self, notify_callback=_notify)

        def _make_sheets():
            from modules.cloud.sheets import SheetsSync
            return SheetsSync(self.config)

        modules = [
            ("Phantom Web Engine",       "browser",     _make_browser),
            ("Ghost Input Protocol",     "macro",       _make_macro),
            ("Precision Strike Trigger", "scheduler",   _make_scheduler),
            ("Smart Task Engine",        "smart_macro", _make_smart_macro),
            ("Cloud Sync Pipeline",      "sheets",      _make_sheets),
        ]
        total = len(modules)

        for i, (name, attr, factory) in enumerate(modules):
            if progress_cb:
                progress_cb(i, total, name)
            try:
                setattr(self, attr, factory())
                self.logger.info(f"[Engine] Ready: {name}")
            except Exception as e:
                self.logger.error(f"[Engine] Failed to init {name}: {e}")

        # Start the scheduler background thread
        if self.scheduler:
            try:
                self._log_and_recover_missed_jobs()
                self.scheduler.start()
                self._register_all_tasks()
                self._schedule_daily_backup()
            except Exception as e:
                self.logger.error(f"[Engine] Scheduler start error: {e}")

        # Run today's backup in the background (skips if already done today)
        threading.Thread(target=self._run_startup_backup, daemon=True).start()

    # -- Backup helpers --
    def _run_startup_backup(self):
        """Create today's backup on startup (no-op if it already exists)."""
        try:
            from utils.backup import AutoBackup
            AutoBackup().create_backup()
        except Exception as e:
            self.logger.error("[Engine] Startup backup error: %s", e)

    def _schedule_daily_backup(self):
        """Register a daily midnight backup job with APScheduler."""
        try:
            from apscheduler.triggers.cron import CronTrigger
            from utils.backup import AutoBackup

            def _midnight_backup():
                try:
                    AutoBackup().create_backup()
                except Exception as exc:
                    self.logger.error("[Engine] Midnight backup error: %s", exc)

            sched = self.scheduler._scheduler  # underlying BackgroundScheduler
            sched.add_job(
                _midnight_backup,
                trigger=CronTrigger(hour=0, minute=0, second=0),
                id="__synthex_daily_backup__",
                replace_existing=True,
                misfire_grace_time=3600,
            )
            self.logger.info("[Engine] Daily backup scheduled at midnight.")
        except Exception as e:
            self.logger.error("[Engine] Failed to schedule daily backup: %s", e)

    # -- Scheduler helpers --
    def _log_and_recover_missed_jobs(self):
        """Log tasks that were missed while the app was closed.

        Called before scheduler.start() so next_run_times haven't updated.
        APScheduler will auto-run jobs within misfire_grace_time (3600s).
        Jobs outside the grace window fire EVENT_JOB_MISSED via the listener.
        """
        try:
            missed = self.scheduler.get_missed_jobs_before_start()
        except Exception:
            return
        if not missed:
            return
        self.logger.info("[Engine] Found %d missed job(s) — running on startup.", len(missed))
        for job_id, name, missed_at in missed:
            self.logger.warning(
                "Task '%s' was missed at %s. Running now...", name, missed_at)

    def _register_all_tasks(self):
        """Register every enabled scheduled task in UserData with APScheduler."""
        if not self.scheduler or not self.app:
            return
        count = 0
        for task in self.app._ud.tasks:
            stype = task.get("schedule_type", "manual")
            if task.get("enabled", True) and stype != "manual":
                try:
                    self.scheduler.register_task(task, _run_scheduled_job)
                    count += 1
                except Exception as e:
                    self.logger.error(
                        "[Engine] Failed to register task '%s': %s",
                        task.get("name", "?"), e)
        if count:
            self.logger.info("[Engine] Registered %d scheduled task(s).", count)

    def register_task(self, task: dict):
        """Register or update a single task in the scheduler (called on save/toggle)."""
        if not self.scheduler:
            return
        try:
            self.scheduler.register_task(task, _run_scheduled_job)
        except Exception as e:
            self.logger.error("[Engine] register_task error: %s", e)

    # -- Lifecycle --
    def start(self):
        self.logger.info("Engine starting...")
        self._running = True
        self.app.run()          # blocks on Tk mainloop

    def stop(self):
        self.logger.info("Engine stopping...")
        self._running = False
        if self.scheduler:
            try:
                self.scheduler.stop()
            except Exception:
                pass
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        self.logger.info("Engine stopped cleanly.")

    # -- Convenience wrappers called by ui/app.py --
    def open_url(self, url: str) -> str:
        """Navigate the browser to the given URL and return the page title."""
        if not self.browser:
            self.logger.warning("open_url called but browser module is not ready.")
            return ""
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            title = self.browser.navigate(url)
            self.app._ud.log("open_url", f"Opened: {url}", ok=True)
            return title or ""
        except Exception as e:
            self.logger.error(f"open_url error: {e}")
            self.app._ud.log("open_url", str(e), ok=False)
            return ""

    def start_recording(self):
        """Start macro recording (mouse + keyboard)."""
        if self.macro:
            try:
                self.macro.start_recording()
                self.logger.info("Macro recording started via engine.")
            except Exception as e:
                self.logger.error(f"start_recording error: {e}")
        else:
            self.logger.warning("start_recording called but macro module is not ready.")

    def stop_recording(self):
        """Stop macro recording."""
        if self.macro:
            try:
                self.macro.stop_recording()
                self.logger.info("Macro recording stopped via engine.")
            except Exception as e:
                self.logger.error(f"stop_recording error: {e}")
        else:
            self.logger.warning("stop_recording called but macro module is not ready.")

    def run_smart_task(self, task: dict, progress_cb=None,
                       step_callback=None, dry_run=False,
                       stop_flag=None, enable_retry: bool = False) -> list:
        """Execute a SmartMacro task and return per-step results."""
        if not self.smart_macro:
            self.logger.error("Smart macro module not ready.")
            return []
        try:
            return self.smart_macro.run_task(
                task,
                progress_cb=progress_cb,
                step_callback=step_callback,
                dry_run=dry_run,
                stop_flag=stop_flag,
                enable_retry=enable_retry,
            )
        except Exception as e:
            self.logger.error(f"run_smart_task error: {e}")
            return [{"step": -1, "ok": False, "result": str(e)}]

    def run_continuous_task(self, task: dict, loop_cb=None, stop_flag=None) -> None:
        """Run a SmartMacro task in continuous loop mode."""
        if not self.smart_macro:
            self.logger.error("Smart macro module not ready.")
            return
        try:
            self.smart_macro.run_continuous(
                task, loop_cb=loop_cb, stop_flag=stop_flag)
        except Exception as e:
            self.logger.error(f"run_continuous_task error: {e}")

    @property
    def is_running(self) -> bool:
        return self._running
