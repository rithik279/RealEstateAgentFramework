from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from psycopg.rows import dict_row

from app.db import Database


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Job states that are finished — a dedupe-key re-enqueue on one of these must
# requeue the row, not silently no-op (dedupe keys are not tombstones).
TERMINAL_JOB_STATUSES = ("succeeded", "failed", "canceled", "cancelled")

# Outbound-touch job types. These are the ONLY types a lead reply / opt-out may
# cancel. Processing types (process_retell_call, notify_owner, classify_sms_reply,
# fetch_meta_lead) must never be canceled — canceling them loses transcripts,
# scoring, and alerts.
CAMPAIGN_JOB_TYPES = ("call_lead", "call_retry", "send_followup_sms", "reactivation_sms")


@dataclass(frozen=True)
class OrchestratorRepo:
    db: Database

    def create_lead_if_new(
        self,
        *,
        source: str,
        meta_lead_id: str,
        name: str | None,
        phone_e164: str | None,
        email: str | None,
        consent_text: str | None,
        consent_timestamp: datetime | None,
        language: str = "en",
    ) -> tuple[str, bool]:
        lead_id = str(uuid4())
        with self.db.connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    insert into leads (id, source, meta_lead_id, name, phone_e164, email, consent_text, consent_timestamp, language)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (meta_lead_id) do nothing
                    returning id
                    """,
                    (
                        lead_id,
                        source,
                        meta_lead_id,
                        name,
                        phone_e164,
                        email,
                        consent_text,
                        consent_timestamp,
                        language,
                    ),
                )
                row = cur.fetchone()
                conn.commit()

        if row and row.get("id"):
            return str(row["id"]), True

        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select id from leads where meta_lead_id=%s", (meta_lead_id,))
                existing = cur.fetchone()
        return str(existing[0]), False

    def add_event(self, *, lead_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into events (lead_id, type, payload_json) values (%s,%s,%s::jsonb)",
                    (lead_id, event_type, json.dumps(payload)),
                )
            conn.commit()

    def get_lead_contact(self, lead_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select id, name, phone_e164, email, do_not_contact, status, source, area from leads where id=%s",
                    (lead_id,),
                )
                return cur.fetchone()

    def find_lead_id_by_phone(self, phone_e164: str) -> str | None:
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select id from leads where phone_e164=%s order by created_at desc limit 1", (phone_e164,))
                row = cur.fetchone()
                return str(row[0]) if row else None

    def get_latest_extracted_json(self, lead_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select extracted_json
                    from calls
                    where lead_id=%s and extracted_json is not null
                    order by ended_at desc nulls last, id desc
                    limit 1
                    """,
                    (lead_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                value = row.get("extracted_json")
                return value if isinstance(value, dict) else None

    def set_do_not_contact(self, lead_id: str, value: bool) -> None:
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("update leads set do_not_contact=%s where id=%s", (value, lead_id))
            conn.commit()

    def set_status(self, lead_id: str, status: str) -> None:
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("update leads set status=%s where id=%s", (status, lead_id))
            conn.commit()

    def create_call(
        self,
        *,
        lead_id: str,
        retell_call_id: str | None,
        twilio_call_sid: str | None = None,
        started_at: datetime | None = None,
    ) -> None:
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into calls (lead_id, retell_call_id, twilio_call_sid, started_at)
                    values (%s,%s,%s,%s)
                    on conflict (retell_call_id) do nothing
                    """,
                    (lead_id, retell_call_id, twilio_call_sid, started_at),
                )
            conn.commit()

    def update_call_from_retell(
        self,
        *,
        retell_call_id: str,
        ended_at: datetime | None,
        duration_sec: int | None,
        outcome: str | None,
        disconnection_reason: str | None,
        transcript_text: str | None,
        extracted_json: dict[str, Any] | None,
    ) -> None:
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update calls
                    set ended_at=%s,
                        duration_sec=%s,
                        outcome=%s,
                        disconnection_reason=%s,
                        transcript_text=coalesce(%s, transcript_text),
                        extracted_json=coalesce(%s::jsonb, extracted_json)
                    where retell_call_id=%s
                    """,
                    (
                        ended_at,
                        duration_sec,
                        outcome,
                        disconnection_reason,
                        transcript_text,
                        json.dumps(extracted_json) if extracted_json is not None else None,
                        retell_call_id,
                    ),
                )
            conn.commit()

    def create_message(
        self,
        *,
        lead_id: str,
        direction: str,
        channel: str,
        body: str,
        twilio_message_sid: str | None = None,
        status: str | None = None,
    ) -> None:
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into messages (lead_id, direction, channel, twilio_message_sid, body, status)
                    values (%s,%s,%s,%s,%s,%s)
                    """,
                    (lead_id, direction, channel, twilio_message_sid, body, status),
                )
            conn.commit()

    def enqueue_job(
        self,
        *,
        job_type: str,
        payload: dict[str, Any],
        run_at: datetime,
        dedupe_key: str | None = None,
        max_attempts: int = 3,
    ) -> None:
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into jobs (type, dedupe_key, payload, run_at, max_attempts)
                    values (%s,%s,%s::jsonb,%s,%s)
                    on conflict (type, dedupe_key) where dedupe_key is not null do update set
                      payload=excluded.payload,
                      run_at=case when jobs.status = any(%s)
                                  then excluded.run_at
                                  else least(jobs.run_at, excluded.run_at) end,
                      status=case when jobs.status = any(%s)
                                  then 'queued' else jobs.status end,
                      attempts=case when jobs.status = any(%s)
                                    then 0 else jobs.attempts end,
                      locked_at=case when jobs.status = any(%s)
                                     then null else jobs.locked_at end,
                      locked_by=case when jobs.status = any(%s)
                                     then null else jobs.locked_by end,
                      updated_at=now()
                    """,
                    (
                        job_type, dedupe_key, json.dumps(payload), run_at, max_attempts,
                        list(TERMINAL_JOB_STATUSES), list(TERMINAL_JOB_STATUSES),
                        list(TERMINAL_JOB_STATUSES), list(TERMINAL_JOB_STATUSES),
                        list(TERMINAL_JOB_STATUSES),
                    ),
                )
            conn.commit()

    def claim_next_job(self, *, worker_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    with next as (
                      select id
                      from jobs
                      where status='queued' and run_at <= now()
                      order by run_at asc, id asc
                      for update skip locked
                      limit 1
                    )
                    update jobs
                    set status='running', locked_at=now(), locked_by=%s, attempts=attempts+1, updated_at=now()
                    where id in (select id from next)
                    returning *
                    """,
                    (worker_id,),
                )
                row = cur.fetchone()
            conn.commit()
            return row

    def mark_job_succeeded(self, job_id: int) -> None:
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update jobs set status='succeeded', updated_at=now() where id=%s",
                    (job_id,),
                )
            conn.commit()

    def mark_job_failed(self, *, job_id: int, error: str, run_at: datetime | None) -> None:
        with self.db.connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select attempts, max_attempts from jobs where id=%s", (job_id,))
                row = cur.fetchone()
                attempts = int(row["attempts"]) if row else 999
                max_attempts = int(row["max_attempts"]) if row else 0

            status = "failed" if attempts >= max_attempts else "queued"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update jobs
                    set status=%s,
                        last_error=%s,
                        run_at=coalesce(%s, run_at),
                        locked_at=null,
                        locked_by=null,
                        updated_at=now()
                    where id=%s
                    """,
                    (status, error[:2000], run_at, job_id),
                )
            conn.commit()

    # -----------------------------------------------------------------------
    # v2: Buyer profile + readiness scoring
    # -----------------------------------------------------------------------

    def set_readiness(
        self,
        lead_id: str,
        *,
        score: int,
        tier: str,
        tags: list[str],
        components: dict[str, int],
        buyer_profile: dict[str, Any] | None = None,
    ) -> None:
        """Persist scorer output to leads table."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update leads
                    set readiness_score = %s,
                        readiness_tier  = %s,
                        tags            = %s::jsonb,
                        scores          = %s::jsonb,
                        buyer_profile   = coalesce(%s::jsonb, buyer_profile)
                    where id = %s
                    """,
                    (
                        score,
                        tier,
                        json.dumps(tags),
                        json.dumps(components),
                        json.dumps(buyer_profile) if buyer_profile is not None else None,
                        lead_id,
                    ),
                )
            conn.commit()

    def get_lead_profile(self, lead_id: str) -> dict[str, Any] | None:
        """Return full lead row with scoring fields."""
        with self.db.connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select id, name, phone_e164, email, status,
                           readiness_score, readiness_tier, tags, scores, buyer_profile,
                           created_at
                    from leads
                    where id = %s
                    """,
                    (lead_id,),
                )
                return cur.fetchone()

    def list_leads_scored(
        self,
        *,
        tier: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Return leads ordered by readiness_score desc.
        Optional filter by tier (hot/warm/early/cold).
        """
        conditions = []
        params: list[Any] = []
        if tier:
            conditions.append("readiness_tier = %s")
            params.append(tier)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.extend([limit, offset])
        with self.db.connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    SELECT id, name, phone_e164, email, status,
                           readiness_score, readiness_tier, tags, created_at
                    FROM leads
                    {where}
                    ORDER BY readiness_score DESC NULLS LAST, created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    params,
                )
                return cur.fetchall() or []

    def cancel_campaign_jobs_for_lead(self, lead_id: str) -> None:
        """Cancel queued outbound touches only. Never cancels processing jobs
        (transcript/scoring/alerts) and never touches running jobs."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update jobs
                    set status='canceled', updated_at=now()
                    where status = 'queued'
                      and type = any(%s)
                      and payload->>'lead_id' = %s
                    """,
                    (list(CAMPAIGN_JOB_TYPES), lead_id),
                )
            conn.commit()

    # Backwards-compatible alias — old callers meant "stop contacting them".
    def cancel_jobs_for_lead(self, lead_id: str) -> None:
        self.cancel_campaign_jobs_for_lead(lead_id)

    def set_do_not_contact_by_phone(self, phone_e164: str, value: bool) -> list[str]:
        """Latch DNC on EVERY lead row sharing this phone (a person can exist as
        both a Meta lead and a legacy import). Returns affected lead ids."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update leads set do_not_contact=%s where phone_e164=%s returning id",
                    (value, phone_e164),
                )
                rows = cur.fetchall()
            conn.commit()
        return [str(r[0]) for r in rows]

    def reclaim_stale_jobs(self, *, older_than_minutes: int = 10) -> int:
        """Requeue jobs stuck in 'running' — the worker thread dies with the web
        process on every deploy, orphaning claimed jobs forever otherwise."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update jobs
                    set status='queued', locked_at=null, locked_by=null, updated_at=now()
                    where status='running'
                      and locked_at < now() - (%s * interval '1 minute')
                    returning id
                    """,
                    (older_than_minutes,),
                )
                rows = cur.fetchall()
            conn.commit()
        return len(rows)

    def reschedule_job(self, job_id: int, *, run_at: datetime) -> None:
        """Push a claimed job back to the queue without burning an attempt
        (used for quiet-hours deferral)."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update jobs
                    set status='queued', run_at=%s,
                        attempts=greatest(attempts-1, 0),
                        locked_at=null, locked_by=null, updated_at=now()
                    where id=%s
                    """,
                    (run_at, job_id),
                )
            conn.commit()

    def recent_duplicate_message_exists(
        self, *, lead_id: str, body: str, within_minutes: int = 60
    ) -> bool:
        """Idempotency guard: a retried job whose first attempt actually reached
        Twilio must not text the lead twice."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select 1 from messages
                    where lead_id=%s and direction='out' and channel='sms' and body=%s
                      and created_at > now() - (%s * interval '1 minute')
                    limit 1
                    """,
                    (lead_id, body, within_minutes),
                )
                return cur.fetchone() is not None

    def count_recent_leads_with_phone(self, *, phone_e164: str, exclude_lead_id: str, hours: int = 24) -> int:
        """Same person submitting two ad forms creates two lead rows — used to
        skip double-calling the same phone within a day."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select count(*) from leads
                    where phone_e164=%s and id <> %s
                      and created_at > now() - (%s * interval '1 hour')
                    """,
                    (phone_e164, exclude_lead_id, hours),
                )
                return int(cur.fetchone()[0])

    def count_calls_created_since(self, since: datetime) -> int:
        """Daily Retell budget guard."""
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select count(*) from calls where created_at >= %s", (since,))
                return int(cur.fetchone()[0])

    def update_message_status(self, *, twilio_message_sid: str, status: str) -> None:
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update messages set status=%s where twilio_message_sid=%s",
                    (status, twilio_message_sid),
                )
            conn.commit()
