from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class CallWindow:
    tz: str = "America/Toronto"
    start_hour: int = 9
    end_hour: int = 20

    def next_allowed(self, now_utc: datetime) -> datetime:
        tz = ZoneInfo(self.tz)
        local = now_utc.astimezone(tz)

        start_local = datetime.combine(local.date(), time(self.start_hour, 0), tzinfo=tz)
        end_local = datetime.combine(local.date(), time(self.end_hour, 0), tzinfo=tz)

        if local < start_local:
            return start_local.astimezone(ZoneInfo("UTC"))
        if local >= end_local:
            next_day = local.date() + timedelta(days=1)
            next_start = datetime.combine(next_day, time(self.start_hour, 0), tzinfo=tz)
            return next_start.astimezone(ZoneInfo("UTC"))

        return now_utc

    def clamp_delay(self, target_utc: datetime) -> datetime:
        # If a retry delay pushes outside hours, clamp to next allowed window.
        tz = ZoneInfo(self.tz)
        local = target_utc.astimezone(tz)
        start_local = datetime.combine(local.date(), time(self.start_hour, 0), tzinfo=tz)
        end_local = datetime.combine(local.date(), time(self.end_hour, 0), tzinfo=tz)

        if local < start_local:
            return start_local.astimezone(ZoneInfo("UTC"))
        if local >= end_local:
            next_day = local.date() + timedelta(days=1)
            next_start = datetime.combine(next_day, time(self.start_hour, 0), tzinfo=tz)
            return next_start.astimezone(ZoneInfo("UTC"))
        return target_utc

