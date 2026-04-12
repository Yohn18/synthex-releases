"""
modules/scheduler/jobs.py - APScheduler-based job scheduler for Synthex.
Jobs are persisted to SQLite so they survive PC and app restarts.
"""

import os
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import (
    EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED,
)
from core.config import Config
from core.logger import get_logger

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "jobs.db",
)


class JobScheduler:
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger("scheduler")

        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        jobstore = SQLAlchemyJobStore(url="sqlite:///{}".format(_DB_PATH))

        self._scheduler = BackgroundScheduler(
            jobstores={"default": jobstore},
            job_defaults={"misfire_grace_time": 3600, "max_instances": 1},
            timezone=config.get("scheduler.timezone", "UTC"),
        )
        self._scheduler.add_listener(
            self._on_job_event,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
        )
        # Optional callback: set to a callable(message, kind) to show UI toasts.
        self.notify_callback = None

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def start(self):
        self._scheduler.start()
        self.logger.info("Scheduler started (SQLite job store: %s).", _DB_PATH)
        self._load_jobs_from_config()

    def stop(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            self.logger.info("Scheduler stopped.")

    # ------------------------------------------------------------------ #
    #  Job registration                                                    #
    # ------------------------------------------------------------------ #

    def add_cron_job(self, func, job_id: str, cron_expr: str, **kwargs):
        """Add a job using a cron expression (e.g. '0 9 * * 1-5')."""
        trigger = CronTrigger.from_crontab(cron_expr)
        self._scheduler.add_job(
            func, trigger, id=job_id, replace_existing=True, kwargs=kwargs)
        self.logger.info("Cron job added: %s @ %s", job_id, cron_expr)

    def add_interval_job(self, func, job_id: str, seconds: int = 60, **kwargs):
        """Add a job that runs every N seconds."""
        trigger = IntervalTrigger(seconds=seconds)
        self._scheduler.add_job(
            func, trigger, id=job_id, replace_existing=True, kwargs=kwargs)
        self.logger.info("Interval job added: %s every %ds", job_id, seconds)

    def register_task(self, task: dict, run_fn) -> None:
        """Register a user task dict (from UserData) with the scheduler.

        run_fn must be a module-level callable that accepts (task_id: str).
        replace_existing=True makes this idempotent.
        """
        task_id = str(task.get("id", ""))
        if not task_id:
            return

        stype = task.get("schedule_type", "manual")
        sval  = task.get("schedule_value", "")
        stime = task.get("schedule_time", "09:00")
        job_id = "task_{}".format(task_id)
        name   = task.get("name", job_id)

        if stype == "manual" or not task.get("enabled", True):
            # Remove from scheduler if present
            try:
                self._scheduler.remove_job(job_id)
                self.logger.info("Unscheduled task '%s'.", name)
            except Exception:
                pass
            return

        try:
            if stype == "interval" and sval:
                minutes = int(sval)
                trigger = IntervalTrigger(minutes=minutes)
                self._scheduler.add_job(
                    run_fn, trigger,
                    id=job_id, args=[task_id], name=name,
                    replace_existing=True,
                )
                self.logger.info("Task '%s' scheduled every %dm.", name, minutes)

            elif stype == "daily" and stime:
                h, m = stime.split(":")
                trigger = CronTrigger(hour=int(h), minute=int(m))
                self._scheduler.add_job(
                    run_fn, trigger,
                    id=job_id, args=[task_id], name=name,
                    replace_existing=True,
                )
                self.logger.info("Task '%s' scheduled daily at %s.", name, stime)

            elif stype == "hourly":
                trigger = CronTrigger(minute=0)
                self._scheduler.add_job(
                    run_fn, trigger,
                    id=job_id, args=[task_id], name=name,
                    replace_existing=True,
                )
                self.logger.info("Task '%s' scheduled hourly.", name)

        except Exception as e:
            self.logger.error("Failed to register task '%s': %s", name, e)

    # ------------------------------------------------------------------ #
    #  Query helpers                                                       #
    # ------------------------------------------------------------------ #

    def get_job_next_run(self, task_id: str):
        """Return next run datetime (timezone-aware) for a task, or None."""
        job = self._scheduler.get_job("task_{}".format(task_id))
        return job.next_run_time if job else None

    def get_missed_jobs_before_start(self) -> list:
        """Return list of (job_id, name, missed_at_str) for overdue jobs.

        Call this BEFORE start() while scheduler is still paused so the
        next_run_times haven't been updated yet.
        """
        now = datetime.now(timezone.utc)
        missed = []
        for job in self._scheduler.get_jobs():
            if job.next_run_time and job.next_run_time < now:
                missed.append((
                    job.id,
                    job.name or job.id,
                    job.next_run_time.strftime("%Y-%m-%d %H:%M:%S"),
                ))
        return missed

    def remove_job(self, job_id: str):
        try:
            self._scheduler.remove_job(job_id)
            self.logger.info("Job removed: %s", job_id)
        except Exception:
            pass

    def list_jobs(self) -> list:
        return [
            {"id": j.id, "next_run": str(j.next_run_time)}
            for j in self._scheduler.get_jobs()
        ]

    # ------------------------------------------------------------------ #
    #  Internal                                                            #
    # ------------------------------------------------------------------ #

    def _load_jobs_from_config(self):
        jobs = self.config.get("scheduler.jobs", [])
        for job in jobs:
            self.logger.info(
                "Config job found: %s (register manually via add_cron_job)", job)

    def _notify(self, message: str, kind: str = "info"):
        if callable(self.notify_callback):
            try:
                self.notify_callback(message, kind)
            except Exception:
                pass

    def _on_job_event(self, event):
        job_id = event.job_id
        try:
            job = self._scheduler.get_job(job_id)
            name = (job.name or job_id) if job else job_id
        except Exception:
            name = job_id

        if event.code == EVENT_JOB_MISSED:
            msg = "Task '{}' was missed while the PC was off. Running now...".format(name)
            self.logger.warning(msg)
            self._notify(msg, kind="warning")
            return

        if event.exception:
            from utils.error_handler import friendly_message
            friendly = friendly_message(event.exception)
            self.logger.error(
                "Task '%s' failed: %s | %s",
                name, type(event.exception).__name__, event.exception)
            self._notify(
                "Task '{}' did not complete. {}".format(name, friendly),
                kind="error",
            )
        else:
            self.logger.debug("Task '%s' completed successfully.", name)
