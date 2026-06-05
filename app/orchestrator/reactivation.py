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
# Touch 2 (Day 4) — personalized value hook based on call extracted data
# ---------------------------------------------------------------------------

def build_touch2_body(
    name: str | None,
    area: str | None,
    extracted: dict | None,
) -> str:
    """
    Personalized Touch 2 SMS. Uses call transcript data if available.
    Falls back to generic area value hook.
    """
    first_name = (name or "").split()[0] if name else "there"
    ex = extracted or {}

    # area_confirmed from call overrides area-code guess
    confirmed_area = ex.get("area_confirmed") or ""
    display_area = confirmed_area if confirmed_area else messaging_area(area or "unknown")

    priority = ex.get("priority_signal") or ""
    renting = ex.get("currently_renting")
    basement = ex.get("basement_income_interest")
    lot_interest = ex.get("lot_size_interest")
    kitchen = ex.get("kitchen_priority")
    investor = ex.get("investor_minded")

    # --- Decision tree ---
    if renting:
        return (
            f"Hey {first_name}, Alex here again. Quick thought since we chatted: "
            f"a lot of people renting in {display_area} right now are actually closer to owning than they think. "
            f"The rent vs. buy math has shifted. Happy to run the numbers for you, no strings attached. Interested?"
        )

    if priority == "income_potential" or basement:
        return (
            f"Hey {first_name}, Alex here. Wanted to share something relevant to what you mentioned: "
            f"homes in {display_area} with legal basement suites are still generating solid rental income. "
            f"Some buyers are covering 30-40% of their mortgage that way. Worth a 10 min chat if you're curious."
        )

    # Garden suite angle: lot interest in sw_ontario (KW/London/Woodstock area has ADU momentum)
    if lot_interest and area in ("sw_ontario", "gta_suburbs", "gta_core"):
        return (
            f"Hey {first_name}, Alex here. Based on what you were looking for in {display_area}, "
            f"garden suites are picking up steam. Some lots qualify for a second unit in the backyard, "
            f"which adds serious value. Wanted to flag it. Want me to pull a few options that would work?"
        )

    if priority == "kitchen" or kitchen:
        return (
            f"Hey {first_name}, Alex here. I pulled together a short list of the top homes in {display_area} "
            f"right now with standout kitchens and good bones. Buyer's market means you have options. "
            f"Want me to send them over?"
        )

    if investor:
        return (
            f"Hey {first_name}, Alex here. Circling back since we spoke. "
            f"Cash flow on the right property in {display_area} is still very achievable in this market. "
            f"Happy to walk you through a quick ROI breakdown on a real listing. Interested?"
        )

    # Generic: top homes value hook
    return (
        f"Hey {first_name}, Alex here. Just wanted to follow up from our chat. "
        f"I put together a short list of the top homes in {display_area} right now, "
        f"buyer's market so timing is actually good. Want me to send it over?"
    )


# ---------------------------------------------------------------------------
# Touch 3 (Day 10) — soft close + referral ask
# ---------------------------------------------------------------------------

def build_touch3_body(name: str | None, area: str | None, extracted: dict | None) -> str:
    first_name = (name or "").split()[0] if name else "there"
    ex = extracted or {}
    confirmed_area = ex.get("area_confirmed") or ""
    display_area = confirmed_area if confirmed_area else messaging_area(area or "unknown")

    return (
        f"Hey {first_name}, Alex one last time. No pressure at all. "
        f"If the timing isn't right for you right now in {display_area}, totally understood. "
        f"And if you know anyone who's thinking about buying or selling, I'd love an intro. "
        f"I take good care of people. Either way, good luck and feel free to reach out anytime."
    )


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

def seed_reactivation_call_jobs(
    *,
    db: Database,
    tz: str = "America/Toronto",
    window_start_hour: int = 9,
    window_end_hour: int = 20,
    daily_limit: int = 20,
    interval_minutes: int = 5,
) -> int:
    """
    Seed outbound ALEX call jobs for legacy_reactivation leads.

    HARD RULE: Calls fire ONE AT A TIME, minimum 5 minutes apart.
    Never batch-fire calls. interval_minutes must never be set below 5.
    Exceeding daily_limit=20 requires explicit approval — do not raise limit
    without discussing cost and Retell rate-limit implications.

    Picks next `daily_limit` leads that:
    - Have no existing call_lead job (queued, running, or succeeded)
    - Are not do_not_contact
    - Have a phone number
    - Source is legacy_reactivation

    Spaces calls evenly across the call window (9am–8pm Toronto).
    Returns number of jobs seeded.
    """
    if interval_minutes < 5:
        raise ValueError("interval_minutes must be >= 5. Hard rule: calls fire one at a time, min 5 min apart.")

    repo = OrchestratorRepo(db=db)
    local_tz = ZoneInfo(tz)
    now_local = datetime.now(local_tz)
    today = now_local.date()

    # Build call window for today
    window_start = datetime(today.year, today.month, today.day, window_start_hour, 0, tzinfo=local_tz)
    window_end = datetime(today.year, today.month, today.day, window_end_hour, 0, tzinfo=local_tz)

    # If window already past, schedule for tomorrow
    if now_local >= window_end:
        tomorrow = today + timedelta(days=1)
        window_start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, window_start_hour, 0, tzinfo=local_tz)
        window_end = datetime(tomorrow.year, tomorrow.month, tomorrow.day, window_end_hour, 0, tzinfo=local_tz)

    # Start from now if inside window
    if window_start < now_local < window_end:
        window_start = now_local + timedelta(minutes=1)

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select l.id, l.name, l.area
                from leads l
                where l.source = 'legacy_reactivation'
                  and l.do_not_contact = false
                  and l.phone_e164 is not null
                  and not exists (
                    select 1 from jobs j
                    where j.type = 'call_lead'
                      and j.payload->>'lead_id' = l.id
                      and j.status in ('queued', 'running', 'succeeded')
                  )
                order by l.created_at asc
                limit %s
                """,
                (daily_limit,),
            )
            rows = cur.fetchall()

    seeded = 0
    for i, (lead_id, name, area) in enumerate(rows):
        call_at = window_start + timedelta(minutes=i * interval_minutes)
        # Don't schedule past window end
        if call_at >= window_end:
            break
        repo.enqueue_job(
            job_type="call_lead",
            dedupe_key=f"call_lead:{lead_id}:reactivation",
            payload={"lead_id": lead_id},
            run_at=call_at.astimezone(timezone.utc),
            max_attempts=2,
        )
        seeded += 1

    return seeded


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
