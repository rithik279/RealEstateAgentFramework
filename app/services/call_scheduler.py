from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger

from app.config import Settings

logger = logging.getLogger(__name__)


class CallScheduler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tz = ZoneInfo(settings.app_timezone)
        self.start_hour = settings.call_window_start_hour
        self.end_hour = settings.call_window_end_hour
        self._scheduler: BackgroundScheduler | None = None

    def _is_within_window(self, dt: datetime) -> bool:
        local = dt.astimezone(self.tz)
        start = local.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
        end = local.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)
        return start <= local < end

    def next_allowed_utc(self, from_dt: datetime | None = None) -> datetime:
        now = (from_dt or datetime.now(timezone.utc)).astimezone(self.tz)
        start = now.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
        end = now.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)

        if self.start_hour <= now.hour < self.end_hour:
            return now.astimezone(timezone.utc)
        if now.hour < self.start_hour:
            return start.astimezone(timezone.utc)
        next_day = now.date() + timedelta(days=1)
        return datetime.combine(
            next_day, time(self.start_hour, 0), tzinfo=self.tz
        ).astimezone(timezone.utc)

    def clamp_to_window(self, target_utc: datetime) -> datetime:
        local = target_utc.astimezone(self.tz)
        end = local.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)
        start = local.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)

        if self.start_hour <= local.hour < self.end_hour:
            return target_utc
        if local.hour < self.start_hour:
            return start.astimezone(timezone.utc)
        next_day = local.date() + timedelta(days=1)
        return datetime.combine(
            next_day, time(self.start_hour, 0), tzinfo=self.tz
        ).astimezone(timezone.utc)

    def schedule_job(
        self,
        func,
        trigger: str = "date",
        *,
        run_at: datetime | None = None,
        cron_hour: int | None = None,
        cron_minute: int = 0,
        id: str | None = None,
        replace_existing: bool = True,
        **kwargs,
    ) -> str | None:
        if self._scheduler is None:
            logger.warning("Scheduler not started — cannot schedule job.")
            return None

        trigger_obj: BaseTrigger
        if trigger == "date" and run_at:
            from apscheduler.triggers.date import DateTrigger
            trigger_obj = DateTrigger(run_date=run_at)
        elif trigger == "cron" and cron_hour is not None:
            trigger_obj = CronTrigger(hour=cron_hour, minute=cron_minute, tz=self.tz)
        else:
            logger.error("Invalid trigger configuration: trigger=%s", trigger)
            return None

        job_id = self._scheduler.add_job(
            func,
            trigger_obj,
            id=id,
            replace_existing=replace_existing,
            **kwargs,
        )
        logger.info(
            "Scheduled job id=%s trigger=%s run_at=%s cron=%s:%s",
            job_id,
            trigger,
            run_at,
            cron_hour,
            cron_minute,
        )
        return job_id

    def start(self) -> None:
        self._scheduler = BackgroundScheduler(timezone=str(self.tz))
        self._scheduler.start()
        logger.info(
            "CallScheduler started (window: %s %02d:00–%02d:00 %s)",
            self.settings.app_timezone,
            self.start_hour,
            self.end_hour,
            self.tz,
        )

    def stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            logger.info("CallScheduler stopped.")

    def get_jobs(self) -> list:
        if self._scheduler is None:
            return []
        return self._scheduler.get_jobs()
