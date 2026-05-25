"""
Reactivation SMS drip system.

- Seeds 20 SMS jobs/day for legacy_reactivation leads not yet contacted
- Jobs fire at random times within 4-8 PM Toronto (configurable)
- Message personalized by area label
- Idempotent: dedupe_key prevents double-sends
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from zoneinfo import ZoneInfo

from app.db import Database
from app.orchestrator.area import messaging_area
from app.orchestrator.repository import OrchestratorRepo


# ---------------------------------------------------------------------------
# SMS copy — NO emojis, NO em dashes, NO automation feel
# ---------------------------------------------------------------------------

_SMS_TEMPLATES: dict[str, str] = {
    "gta_core": (
        "Hi {name}, it's Anu Kabli. You reached out to us a while back about buying a home in the GTA. "
        "Did you end up finding something, or is that still on your radar? Happy to catch up."
    ),
    "gta_suburbs": (
        "Hi {name}, it's Anu Kabli. You reached out to us a while back about buying a home in the GTA. "
        "Did you end up finding something, or is that still on your radar? Happy to catch up."
    ),
    "sw_ontario": (
        "Hi {name}, it's Anu Kabli. You reached out to us a while back about buying a home in the "
        "Kitchener, Waterloo, London, Woodstock or surrounding area. "
        "Did you end up finding something, or is that still on your radar? Happy to chat."
    ),
    "eastern_ont": (
        "Hi {name}, it's Anu Kabli. You reached out to us a while back about buying a home in Ontario. "
        "Did you end up finding something, or is that still on your radar? Happy to reconnect."
    ),
    "central_ont": (
        "Hi {name}, it's Anu Kabli. You reached out to us a while back about buying a home in Ontario. "
        "Did you end up finding something, or is that still on your radar? Happy to reconnect."
    ),
    "northern_ont": (
        "Hi {name}, it's Anu Kabli. You reached out to us a while back about buying a home in Ontario. "
        "Did you end up finding something, or is that still on your radar? Happy to reconnect."
    ),
    "out_of_province": (
        "Hi {name}, it's Anu Kabli. You reached out to us a while back about buying a home. "
        "Did you end up finding something, or is that still on your radar? Happy to reconnect."
    ),
    "unknown": (
        "Hi {name}, it's Anu Kabli. You reached out to us a while back about buying a home. "
        "Did you end up finding something, or is that still on your radar? Happy to reconnect."
    ),
}

_FALLBACK_TEMPLATE = _SMS_TEMPLATES["unknown"]


def build_sms_body(name: str | None, area: str | None) -> str:
    first_name = (name or "").split()[0] if name else ""
    display_name = first_name if first_name else "there"
    template = _SMS_TEMPLATES.get(area or "unknown", _FALLBACK_TEMPLATE)
    return template.format(name=display_name)


# ---------------------------------------------------------------------------
# Random send time within window
# ---------------------------------------------------------------------------

def _random_send_time(
    *,
    tz: str,
    window_start_hour: int,
    window_end_hour: int,
    base_date: datetime | None = None,
) -> datetime:
    """Return a random UTC datetime within today's SMS window in the given tz."""
    local_tz = ZoneInfo(tz)
    now_local = datetime.now(local_tz)
    date = (base_date or now_local).date()

    window_start = datetime(date.year, date.month, date.day, window_start_hour, 0, tzinfo=local_tz)
    window_end = datetime(date.year, date.month, date.day, window_end_hour, 0, tzinfo=local_tz)

    # If window already past for today, schedule for tomorrow
    if now_local >= window_end:
        tomorrow = date + timedelta(days=1)
        window_start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, window_start_hour, 0, tzinfo=local_tz)
        window_end = datetime(tomorrow.year, tomorrow.month, tomorrow.day, window_end_hour, 0, tzinfo=local_tz)

    # If we're inside the window, start from now
    if window_start < now_local < window_end:
        window_start = now_local

    total_seconds = int((window_end - window_start).total_seconds())
    offset = random.randint(0, max(0, total_seconds - 1))
    send_time_local = window_start + timedelta(seconds=offset)
    return send_time_local.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Seed daily drip jobs
# ---------------------------------------------------------------------------

def seed_reactivation_sms_jobs(
    *,
    db: Database,
    tz: str = "America/Toronto",
    window_start_hour: int = 16,
    window_end_hour: int = 20,
    daily_limit: int = 20,
) -> int:
    """
    Pull next `daily_limit` legacy_reactivation leads that haven't had
    a reactivation SMS sent yet, enqueue reactivation_sms jobs at
    random times within the SMS window.

    Returns number of jobs seeded.
    """
    repo = OrchestratorRepo(db=db)

    with db.connect() as conn:
        with conn.cursor() as cur:
            # Leads eligible: legacy_reactivation, not do_not_contact,
            # no reactivation_sms job already queued/done for them
            cur.execute(
                """
                select l.id, l.name, l.area
                from leads l
                where l.source = 'legacy_reactivation'
                  and l.do_not_contact = false
                  and l.phone_e164 is not null
                  and not exists (
                    select 1 from jobs j
                    where j.type = 'reactivation_sms'
                      and j.payload->>'lead_id' = l.id
                  )
                order by l.created_at asc
                limit %s
                """,
                (daily_limit,),
            )
            rows = cur.fetchall()

    seeded = 0
    for (lead_id, name, area) in rows:
        send_at = _random_send_time(
            tz=tz,
            window_start_hour=window_start_hour,
            window_end_hour=window_end_hour,
        )
        body = build_sms_body(name=name, area=area)
        repo.enqueue_job(
            job_type="reactivation_sms",
            dedupe_key=f"reactivation_sms:{lead_id}",
            payload={"lead_id": lead_id, "body": body},
            run_at=send_at,
            max_attempts=2,
        )
        seeded += 1

    return seeded


# ---------------------------------------------------------------------------
# Daily report
# ---------------------------------------------------------------------------

def daily_reactivation_report(*, db: Database, tz: str = "America/Toronto") -> dict[str, Any]:
    """Return stats dict for today's reactivation SMS activity."""
    local_tz = ZoneInfo(tz)
    now_local = datetime.now(local_tz)
    today_start = datetime(now_local.year, now_local.month, now_local.day, 0, 0, tzinfo=local_tz)
    today_end = today_start + timedelta(days=1)

    today_start_utc = today_start.astimezone(timezone.utc)
    today_end_utc = today_end.astimezone(timezone.utc)

    with db.connect() as conn:
        with conn.cursor() as cur:
            # SMS sent today
            cur.execute(
                """
                select count(*) from jobs
                where type = 'reactivation_sms'
                  and status = 'done'
                  and updated_at >= %s and updated_at < %s
                """,
                (today_start_utc, today_end_utc),
            )
            sent_today = cur.fetchone()[0]

            # Still queued for today
            cur.execute(
                """
                select count(*) from jobs
                where type = 'reactivation_sms'
                  and status = 'queued'
                  and run_at >= %s and run_at < %s
                """,
                (today_start_utc, today_end_utc),
            )
            queued_today = cur.fetchone()[0]

            # Total sent all time
            cur.execute(
                "select count(*) from jobs where type = 'reactivation_sms' and status = 'done'"
            )
            total_sent = cur.fetchone()[0]

            # Total eligible remaining
            cur.execute(
                """
                select count(*) from leads l
                where l.source = 'legacy_reactivation'
                  and l.do_not_contact = false
                  and l.phone_e164 is not null
                  and not exists (
                    select 1 from jobs j
                    where j.type = 'reactivation_sms'
                      and j.payload->>'lead_id' = l.id
                  )
                """
            )
            remaining_eligible = cur.fetchone()[0]

            # Replies received today (inbound SMS from reactivation leads)
            cur.execute(
                """
                select count(*) from messages m
                join leads l on l.id = m.lead_id
                where m.direction = 'in'
                  and m.channel = 'sms'
                  and l.source = 'legacy_reactivation'
                  and m.created_at >= %s and m.created_at < %s
                """,
                (today_start_utc, today_end_utc),
            )
            replies_today = cur.fetchone()[0]

            # Breakdown by area
            cur.execute(
                """
                select l.area, count(*)
                from jobs j
                join leads l on l.id = (j.payload->>'lead_id')
                where j.type = 'reactivation_sms' and j.status = 'done'
                group by l.area
                order by count(*) desc
                """
            )
            by_area = {row[0] or "unknown": row[1] for row in cur.fetchall()}

    return {
        "date": now_local.strftime("%Y-%m-%d"),
        "sent_today": sent_today,
        "queued_today": queued_today,
        "replies_today": replies_today,
        "total_sent_all_time": total_sent,
        "remaining_eligible": remaining_eligible,
        "days_remaining_at_current_pace": (
            round(remaining_eligible / 20) if remaining_eligible else 0
        ),
        "sent_by_area": by_area,
    }
