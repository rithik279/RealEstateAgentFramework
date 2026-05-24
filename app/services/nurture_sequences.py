"""
Nurture Sequences
=================
Defines the follow-up message sequences for each buyer tier post-call.

Tier routing:
  hot   → immediate booking push (handled in worker._send_followup_sms)
  warm  → 3-message consult sequence over 48h
  early → 4-message nurture sequence over 7 days
  cold  → weekly drip (low frequency, automated only)

These sequences are enqueued as jobs after the call is scored.
Each message is personalized using the buyer's extracted profile.

Usage:
    from app.services.nurture_sequences import get_sequence, build_message

    jobs = get_sequence("warm", lead_id="abc", extracted=extracted_json, booking_url="...")
    for job in jobs:
        repo.enqueue_job(**job)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------

def _first_name(name: str | None) -> str:
    if not name:
        return "there"
    return name.strip().split()[0]


def build_warm_sequence(
    lead_id: str,
    name: str | None,
    extracted: dict[str, Any],
    booking_url: str,
) -> list[dict[str, Any]]:
    """
    3-message sequence for warm buyers (score 50-79).
    Sent over 48 hours.
    """
    first = _first_name(name)
    budget_max = extracted.get("budget_max")
    areas = extracted.get("preferred_areas")
    area_str = f" in {areas[0]}" if isinstance(areas, list) and areas else ""
    budget_str = f" up to ${int(budget_max):,}" if isinstance(budget_max, (int, float)) else ""
    timeline = (extracted.get("timeline") or "").strip()
    basement = extracted.get("basement_income_interest")

    msgs = [
        # Message 1 — immediate (3-15s after call, handled by worker)
        # Already sent. Sequence starts at +4h.

        # Message 2 — value add at 4h
        {
            "delay": timedelta(hours=4),
            "body": (
                f"Hi {first}! Quick follow-up on your search{area_str}{budget_str}. "
                f"I pulled the latest listings that match — "
                f"{'including homes with income suites' if basement else 'based on your criteria'}. "
                f"Want me to send the top 3? Just reply YES."
            ),
        },

        # Message 3 — urgency at 24h
        {
            "delay": timedelta(hours=24),
            "body": (
                f"Hi {first} — just checking in. "
                f"{'The income suite market in Brampton moves fast ' if basement else 'Good properties in your range '}"
                f"— homes{budget_str} are getting multiple offers. "
                f"Book a 15-min call and I'll walk you through what's available: {booking_url} "
                f"Reply STOP to opt out."
            ),
        },

        # Message 4 — final at 48h
        {
            "delay": timedelta(hours=48),
            "body": (
                f"Hi {first}, last message for now. "
                f"If your timeline is {timeline or 'coming up soon'}, "
                f"we should connect before the best options are gone. "
                f"Book here when ready: {booking_url} "
                f"Reply STOP to opt out."
            ),
        },
    ]
    return msgs


def build_early_sequence(
    lead_id: str,
    name: str | None,
    extracted: dict[str, Any],
    booking_url: str,
) -> list[dict[str, Any]]:
    """
    4-message sequence for early buyers (score 20-49).
    Sent over 7 days. Low-pressure, educational.
    """
    first = _first_name(name)
    budget_max = extracted.get("budget_max")
    budget_str = f" up to ${int(budget_max):,}" if isinstance(budget_max, (int, float)) else ""
    basement = extracted.get("basement_income_interest")
    first_time = extracted.get("first_time_buyer")

    msgs = [
        # Message 1 — Day 1 (value: market insight)
        {
            "delay": timedelta(hours=24),
            "body": (
                f"Hi {first}! When you're ready to explore homes{budget_str} in Brampton, "
                f"I'd love to help. "
                f"{'Did you know basement income can offset $1,200-$2,000/mo of your mortgage? ' if basement else ''}"
                f"No pressure — just here when you need it. Reply anytime."
            ),
        },

        # Message 2 — Day 3 (value: first-time buyer info)
        {
            "delay": timedelta(days=3),
            "body": (
                f"Hi {first} — "
                f"{'As a first-time buyer, you may qualify for up to $8,475 in Ontario LTT rebate. ' if first_time else 'Quick tip: '}"
                f"Brampton homes{budget_str} are often available with less competition than Toronto. "
                f"Happy to send you a free affordability breakdown — just reply YES."
            ),
        },

        # Message 3 — Day 5 (value: social proof)
        {
            "delay": timedelta(days=5),
            "body": (
                f"Hi {first}! A quick update: we helped a buyer last month find a 4-bed detached"
                f"{' with a legal basement suite' if basement else ''} in Brampton"
                f"{budget_str}. "
                f"The process took about 6 weeks from first call to keys. "
                f"When your timeline firms up, I'm here: {booking_url} "
                f"Reply STOP to opt out."
            ),
        },

        # Message 4 — Day 7 (gentle close)
        {
            "delay": timedelta(days=7),
            "body": (
                f"Hi {first} — stepping back now. "
                f"When you're ready to get serious about your search{budget_str}, "
                f"I'll be here. Book a free 15-min strategy call: {booking_url} "
                f"Reply STOP to opt out."
            ),
        },
    ]
    return msgs


def build_cold_sequence(
    lead_id: str,
    name: str | None,
    extracted: dict[str, Any],
    booking_url: str,
) -> list[dict[str, Any]]:
    """
    2-message drip for cold leads (<20).
    Minimal agent time. 2-week spacing.
    """
    first = _first_name(name)

    return [
        {
            "delay": timedelta(days=7),
            "body": (
                f"Hi {first} — just a quick note. "
                f"When you're thinking about buying a home in Brampton, I'm here to help. "
                f"No rush. Reply anytime or book here: {booking_url} "
                f"Reply STOP to opt out."
            ),
        },
        {
            "delay": timedelta(days=14),
            "body": (
                f"Hi {first} — last touch for a while. "
                f"Brampton real estate updates are available anytime you want them. "
                f"Reply YES for market updates or STOP to opt out."
            ),
        },
    ]


def get_sequence(
    tier: str,
    lead_id: str,
    name: str | None,
    extracted: dict[str, Any],
    booking_url: str,
) -> list[dict[str, Any]]:
    """
    Get the message sequence for a given tier.
    Returns list of {delay: timedelta, body: str}.
    """
    if tier == "warm":
        return build_warm_sequence(lead_id, name, extracted, booking_url)
    elif tier == "early":
        return build_early_sequence(lead_id, name, extracted, booking_url)
    elif tier == "cold":
        return build_cold_sequence(lead_id, name, extracted, booking_url)
    return []  # hot handled immediately in worker


def enqueue_sequence(
    repo: Any,  # OrchestratorRepo — avoid circular import
    tier: str,
    lead_id: str,
    name: str | None,
    extracted: dict[str, Any],
    booking_url: str,
) -> int:
    """
    Enqueue all sequence messages as send_followup_sms jobs.
    Returns number of jobs enqueued.
    """
    sequence = get_sequence(tier, lead_id, name, extracted, booking_url)
    now = utc_now()
    count = 0
    for i, msg in enumerate(sequence):
        run_at = now + msg["delay"]
        dedupe_key = f"lead:{lead_id}:seq:{tier}:{i}"
        try:
            repo.enqueue_job(
                job_type="send_followup_sms",
                dedupe_key=dedupe_key,
                payload={"lead_id": lead_id, "body_override": msg["body"]},
                run_at=run_at,
                max_attempts=3,
            )
            count += 1
        except Exception:
            pass  # deduplication conflict = already enqueued
    return count
