from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from app.config import Settings
from app.orchestrator.crypto import verify_meta_signature, verify_retell_signature
from app.orchestrator.meta_graph import fetch_meta_lead
from app.orchestrator.phone import (
    is_start_message,
    is_stop_message,
    normalize_na_phone_to_e164,
)
from app.orchestrator.repository import OrchestratorRepo
from app.orchestrator.schedule import CallWindow
from app.services.channels import ChannelSender

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_meta_created_time(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


@router.get("/meta")
def meta_webhook_verify(request: Request, response: Response) -> Response:
    settings: Settings = request.state.settings
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token and token == settings.meta_verify_token and challenge:
        return Response(content=challenge, media_type="text/plain", status_code=200)
    return Response(content="Forbidden", media_type="text/plain", status_code=403)


@router.post("/meta")
async def meta_webhook_event(request: Request, response: Response) -> Response:
    repo: OrchestratorRepo = request.state.repo
    settings: Settings = request.state.settings
    sender: ChannelSender = request.state.sender

    raw = await request.body()
    if not verify_meta_signature(raw, settings.meta_app_secret, request.headers.get("x-hub-signature-256")):
        return Response(status_code=401)

    payload = await request.json()
    if not isinstance(payload, dict):
        return Response(status_code=400)

    lead_ids: list[str] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            leadgen_id = value.get("leadgen_id")
            if isinstance(leadgen_id, str) and leadgen_id:
                lead_ids.append(leadgen_id)

    call_window = CallWindow(
        tz=settings.app_timezone,
        start_hour=settings.call_window_start_hour,
        end_hour=settings.call_window_end_hour,
    )
    now_utc = utc_now()

    for leadgen_id in lead_ids:
        details = fetch_meta_lead(settings.meta_access_token, leadgen_id)
        phone_e164 = normalize_na_phone_to_e164(details.phone)
        consent_ts = _parse_meta_created_time(details.created_time)

        lead_id, created = repo.create_lead_if_new(
            source="meta",
            meta_lead_id=details.meta_lead_id,
            name=details.full_name,
            phone_e164=phone_e164,
            email=details.email,
            consent_text="Meta Lead Ads opt-in",
            consent_timestamp=consent_ts,
            language="en",
        )

        repo.add_event(
            lead_id=lead_id,
            event_type="meta_lead_webhook_received",
            payload={"raw": payload, "created": created, "leadgen_id": leadgen_id},
        )

        run_at = call_window.next_allowed(now_utc)
        repo.enqueue_job(
            job_type="call_lead",
            dedupe_key=f"lead:{lead_id}:call",
            payload={"lead_id": lead_id},
            run_at=run_at,
            max_attempts=3,
        )

        if run_at > now_utc:
            delay_seconds = random.randint(3, 15)
            repo.enqueue_job(
                job_type="send_followup_sms",
                dedupe_key=f"lead:{lead_id}:followup",
                payload={"lead_id": lead_id},
                run_at=now_utc + timedelta(seconds=delay_seconds),
                max_attempts=5,
            )

    return Response(status_code=200)


@router.post("/retell")
async def retell_webhook(request: Request, response: Response) -> Response:
    repo: OrchestratorRepo = request.state.repo
    settings: Settings = request.state.settings

    raw_bytes = await request.body()
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    signature = request.headers.get("x-retell-signature")
    if not verify_retell_signature(raw_text, settings.retell_api_key, signature):
        return Response(status_code=401)

    payload = await request.json()
    event = payload.get("event")
    call = payload.get("call") or {}

    if not isinstance(call, dict) or not isinstance(event, str):
        return Response(status_code=204)

    metadata = call.get("metadata") or {}
    lead_id = metadata.get("lead_id") if isinstance(metadata, dict) else None
    if not isinstance(lead_id, str) or not lead_id:
        return Response(status_code=204)

    retell_call_id = call.get("call_id")
    transcript = call.get("transcript") or ""
    start_ts = call.get("start_timestamp")
    end_ts = call.get("end_timestamp")
    duration_sec: int | None = None
    if isinstance(start_ts, int) and isinstance(end_ts, int) and end_ts >= start_ts:
        duration_sec = int((end_ts - start_ts) / 1000)

    repo.add_event(lead_id=lead_id, event_type=f"retell_{event}", payload=payload)

    if isinstance(retell_call_id, str) and retell_call_id:
        repo.create_call(lead_id=lead_id, retell_call_id=retell_call_id)

    if event in {"call_ended", "call_analyzed"}:
        dedupe_key = f"call:{retell_call_id}:{event}" if retell_call_id else None
        repo.enqueue_job(
            job_type="process_retell_call",
            dedupe_key=dedupe_key,
            payload={
                "lead_id": lead_id,
                "retell_call_id": retell_call_id,
                "call_status": call.get("call_status"),
                "disconnection_reason": call.get("disconnection_reason"),
                "transcript": transcript,
                "duration_sec": duration_sec,
            },
            run_at=utc_now(),
            max_attempts=5,
        )

    return Response(status_code=204)


@router.post("/twilio/sms")
async def twilio_inbound_sms(request: Request, response: Response) -> Response:
    repo: OrchestratorRepo = request.state.repo
    sender: ChannelSender = request.state.sender

    form = await request.form()
    from_number_raw = str(form.get("From") or "")
    body = str(form.get("Body") or "")
    message_sid = str(form.get("MessageSid") or "")

    from_e164 = normalize_na_phone_to_e164(from_number_raw) or from_number_raw
    lead_id = repo.find_lead_id_by_phone(from_e164) if from_e164.startswith("+") else None
    if not lead_id:
        return Response(status_code=204)

    repo.create_message(
        lead_id=lead_id,
        direction="in",
        channel="sms",
        body=body,
        twilio_message_sid=message_sid or None,
        status="received",
    )
    repo.add_event(
        lead_id=lead_id,
        event_type="twilio_inbound_sms",
        payload={"from": from_e164, "body": body, "message_sid": message_sid},
    )

    if is_stop_message(body):
        repo.set_do_not_contact(lead_id, True)
        repo.set_status(lead_id, "opted_out")
        repo.cancel_jobs_for_lead(lead_id)
        sender.send_sms_to_number(to_number=from_e164, body="You're opted out. Reply START to resubscribe.")
        return Response(status_code=204)

    if is_start_message(body):
        repo.set_do_not_contact(lead_id, False)
        repo.set_status(lead_id, "resubscribed")
        sender.send_sms_to_number(to_number=from_e164, body="You're resubscribed. Reply STOP to opt out.")
        return Response(status_code=204)

    return Response(status_code=204)
