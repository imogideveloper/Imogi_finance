from __future__ import annotations

from importlib import util as importlib_util
from typing import Callable, Iterable, Sequence

from imogi_finance.reporting.models import ScheduledJob


class _InMemoryScheduler:
    def __init__(self):
        self.jobs: list[ScheduledJob] = []

    def add_job(self, func: Callable, trigger: str, **kwargs):
        job = ScheduledJob(
            name=kwargs.get("id") or func.__name__,
            trigger=trigger,
            schedule=kwargs.get("schedule") or kwargs.get("cron") or "",
            target=f"{func.__module__}.{func.__name__}",
            kwargs=kwargs,
            backend="in-memory",
        )
        self.jobs.append(job)
        return job

    def start(self):
        return None

    def shutdown(self, wait: bool = True):
        return None


def _load_apscheduler_backend():
    if not importlib_util.find_spec("apscheduler"):
        return None

    if importlib_util.find_spec("apscheduler.schedulers.background"):
        from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore

        return BackgroundScheduler
    return None


class ReportScheduler:
    """Unified scheduler that prefers APScheduler but falls back to an in-memory collector."""

    def __init__(self, *, activate: bool = False):
        backend = _load_apscheduler_backend()
        self.backend = backend.__name__ if backend else "in-memory"
        self.scheduler = backend() if backend else _InMemoryScheduler()
        self.jobs: list[ScheduledJob] = []
        self.activate = activate

    def _register(self, func: Callable, trigger: str, **kwargs) -> ScheduledJob:
        job = ScheduledJob(
            name=kwargs.get("id") or func.__name__,
            trigger=trigger,
            schedule=kwargs.get("schedule") or kwargs.get("cron") or "",
            target=f"{func.__module__}.{func.__name__}",
            kwargs=kwargs,
            backend=self.backend,
        )
        self.jobs.append(job)
        if self.activate:
            self.scheduler.add_job(func, trigger, **kwargs)
        return job

    def start(self):
        if self.activate:
            self.scheduler.start()
        return self.jobs

    def shutdown(self):
        if self.activate:
            self.scheduler.shutdown()
        return None

    def schedule_daily_report(
        self,
        func: Callable,
        *,
        hour: int = 23,
        minute: int = 55,
        timezone: str = "Asia/Jakarta",
        branches: Sequence[str] | None = None,
    ) -> ScheduledJob:
        return self._register(
            func,
            "cron",
            hour=hour,
            minute=minute,
            timezone=timezone,
            kwargs={"branches": list(branches) if branches else None},
            id="daily-report",
        )

    def schedule_monthly_reconciliation(
        self,
        func: Callable,
        *,
        day: int = 1,
        hour: int = 6,
        minute: int = 0,
        timezone: str = "Asia/Jakarta",
    ) -> ScheduledJob:
        return self._register(
            func,
            "cron",
            day=day,
            hour=hour,
            minute=minute,
            timezone=timezone,
            id="monthly-reconciliation",
        )

    def schedule_custom_jobs(self, jobs: Iterable[dict]):
        for job in jobs:
            target = job.get("callable")
            if not callable(target):
                continue
            trigger = job.get("trigger") or "cron"
            kwargs = job.get("kwargs") or {}
            self._register(target, trigger, **kwargs)
        return self.jobs
