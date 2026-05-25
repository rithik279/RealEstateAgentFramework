"""
Admin control center API router.

All routes except /login require valid session cookie (require_admin dependency).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from psycopg.rows import dict_row

from app.auth import clear_session_cookie, require_admin, set_session_cookie, verify_password
from app.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@router.post("/login")
async def admin_login(
    response: Response,
    password: str = Form(...),
) -> dict[str, str]:
    if not settings.admin_password_hash:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_PASSWORD_HASH not configured. Set it in Render env vars.",
        )
    if not verify_password(password):
        raise HTTPException(status_code=401, detail="Invalid password.")
    set_session_cookie(response)
    return {"status": "ok"}


@router.post("/logout")
async def admin_logout(response: Response) -> dict[str, str]:
    clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/check")
async def admin_check(_: None = Depends(require_admin)) -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Overview — aggregated stats
# ---------------------------------------------------------------------------

@router.get("/overview")
async def admin_overview(_: None = Depends(require_admin)) -> dict[str, Any]:
    from app.main import orchestrator_repo  # avoid circular at module level

    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="Database not configured.")

    today = datetime.now(timezone.utc).date()

    with orchestrator_repo.db.connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Total leads
            cur.execute("select count(*) as total from leads")
            total_leads = cur.fetchone()["total"]

            # Leads per tier
            cur.execute(
                "select readiness_tier, count(*) as cnt from leads "
                "where readiness_tier is not null group by readiness_tier"
            )
            tier_counts: dict[str, int] = {r["readiness_tier"]: r["cnt"] for r in cur.fetchall()}

            # Leads with no tier (unscored)
            cur.execute("select count(*) as cnt from leads where readiness_tier is null")
            unscored = cur.fetchone()["cnt"]

            # Calls today
            cur.execute(
                "select count(*) as cnt from calls where created_at::date = %s", (today,)
            )
            calls_today = cur.fetchone()["cnt"]

            # SMS today (outbound)
            cur.execute(
                "select count(*) as cnt from messages "
                "where direction = 'out' and channel = 'sms' and created_at::date = %s",
                (today,),
            )
            sms_today = cur.fetchone()["cnt"]

            # Jobs queued
            cur.execute("select count(*) as cnt from jobs where status = 'queued'")
            jobs_queued = cur.fetchone()["cnt"]

            # Jobs failed (last 24h)
            cur.execute(
                "select count(*) as cnt from jobs where status = 'failed' "
                "and updated_at > now() - interval '24 hours'"
            )
            jobs_failed_24h = cur.fetchone()["cnt"]

            # Reactivation leads
            cur.execute(
                "select count(*) as cnt from leads where source = 'legacy_reactivation'"
            )
            reactivation_total = cur.fetchone()["cnt"]

            cur.execute(
                "select count(*) as cnt from jobs "
                "where type = 'reactivation_sms' and status = 'done'"
            )
            reactivation_sent = cur.fetchone()["cnt"]

    return {
        "total_leads": total_leads,
        "tiers": {
            "hot": tier_counts.get("hot", 0),
            "warm": tier_counts.get("warm", 0),
            "early": tier_counts.get("early", 0),
            "cold": tier_counts.get("cold", 0),
            "unscored": unscored,
        },
        "calls_today": calls_today,
        "sms_today": sms_today,
        "jobs_queued": jobs_queued,
        "jobs_failed_24h": jobs_failed_24h,
        "reactivation_total": reactivation_total,
        "reactivation_sent": reactivation_sent,
    }


# ---------------------------------------------------------------------------
# Job queue
# ---------------------------------------------------------------------------

@router.get("/jobs")
async def admin_jobs(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    from app.main import orchestrator_repo

    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="Database not configured.")

    with orchestrator_repo.db.connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if status:
                cur.execute(
                    "select id, type, status, payload, run_at, attempts, max_attempts, "
                    "last_error, created_at, updated_at "
                    "from jobs where status = %s "
                    "order by run_at desc limit %s offset %s",
                    (status, limit, offset),
                )
            else:
                cur.execute(
                    "select id, type, status, payload, run_at, attempts, max_attempts, "
                    "last_error, created_at, updated_at "
                    "from jobs order by run_at desc limit %s offset %s",
                    (limit, offset),
                )
            rows = cur.fetchall()

            # total count
            if status:
                cur.execute("select count(*) as cnt from jobs where status = %s", (status,))
            else:
                cur.execute("select count(*) as cnt from jobs")
            total = cur.fetchone()["cnt"]

    jobs = []
    for r in rows:
        j = dict(r)
        for k, v in j.items():
            if hasattr(v, "isoformat"):
                j[k] = v.isoformat()
        jobs.append(j)

    return {"total": total, "limit": limit, "offset": offset, "jobs": jobs}


# ---------------------------------------------------------------------------
# Calls log
# ---------------------------------------------------------------------------

@router.get("/calls")
async def admin_calls(
    limit: int = 50,
    offset: int = 0,
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    from app.main import orchestrator_repo

    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="Database not configured.")

    with orchestrator_repo.db.connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select c.id, c.lead_id, l.name as lead_name, c.retell_call_id, "
                "c.started_at, c.ended_at, c.duration_sec, c.outcome, "
                "c.disconnection_reason, c.created_at "
                "from calls c left join leads l on l.id = c.lead_id "
                "order by c.created_at desc limit %s offset %s",
                (limit, offset),
            )
            rows = cur.fetchall()
            cur.execute("select count(*) as cnt from calls")
            total = cur.fetchone()["cnt"]

    calls = []
    for r in rows:
        c = dict(r)
        for k, v in c.items():
            if hasattr(v, "isoformat"):
                c[k] = v.isoformat()
        calls.append(c)

    return {"total": total, "calls": calls}
