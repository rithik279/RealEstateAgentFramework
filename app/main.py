from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse

from app.config import settings
from app.db import create_database, migrate
from app.models import (
    Channel,
    ConversationReplyRequest,
    ConversationStartRequest,
    FacebookLeadCreate,
    InboundMessageCreate,
    Lead,
    LeadCreate,
    MessageSendRequest,
    StageUpdateRequest,
)
from app.services.channels import ChannelSender
from app.services.follow_up import FollowUpService
from app.services.openai_chat import OpenAIChatService
from app.services.call_scheduler import CallScheduler
from app.orchestrator.crypto import verify_meta_signature, verify_retell_signature
from app.orchestrator.meta_graph import fetch_meta_lead
from app.orchestrator.phone import (
    is_start_message,
    is_stop_message,
    normalize_na_phone_to_e164,
)
from app.orchestrator.repository import OrchestratorRepo
from app.orchestrator.schedule import CallWindow
from app.orchestrator.worker import start_worker_in_thread
from app.storage import JsonStorage


app = FastAPI(
    title="Real Estate Auto Message Bot",
    description="Automatic real estate lead follow-up by email, SMS, and Facebook Messenger.",
    version="0.2.0",
)

storage = JsonStorage(settings.data_file)
sender = ChannelSender(settings)
service = FollowUpService(storage, sender, settings)
chat_service = OpenAIChatService(settings)

orchestrator_repo: OrchestratorRepo | None = None
worker_stop = None
call_scheduler: CallScheduler | None = None


def _parse_meta_created_time(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        # Meta often returns ISO with timezone; this handles "Z" and offsets.
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


@app.on_event("startup")
def _startup() -> None:
    global orchestrator_repo, worker_stop, call_scheduler
    if not settings.database_url:
        return

    db = create_database(settings.database_url)
    migrate(db)
    orchestrator_repo = OrchestratorRepo(db=db)

    _thread, worker_stop = start_worker_in_thread(orchestrator_repo, sender, settings)

    call_scheduler = CallScheduler(settings)
    call_scheduler.start()
    print("INFO:     Starting CallScheduler...")


@app.on_event("shutdown")
def _shutdown() -> None:
    global worker_stop, call_scheduler
    if worker_stop is not None:
        worker_stop.set()
    if call_scheduler is not None:
        call_scheduler.stop()


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Real Estate Auto Message Bot is running."}


@app.get("/mvp", response_class=FileResponse)
def mvp_ui() -> FileResponse:
    return FileResponse(settings.ui_file)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "dry_run": settings.dry_run,
    }


@app.get("/config-status")
def config_status() -> dict[str, bool | str]:
    return {
        "dry_run": settings.dry_run,
        "email_configured": bool(
            settings.smtp_host
            and settings.smtp_username
            and settings.smtp_password
            and settings.smtp_from_email
        ),
        "sms_configured": bool(
            settings.twilio_account_sid
            and settings.twilio_auth_token
            and settings.twilio_from_number
        ),
        "facebook_configured": bool(settings.meta_page_access_token),
        "booking_link_configured": bool(settings.calendly_booking_url or settings.booking_link),
        "openai_configured": bool(settings.openai_api_key),
        "openai_model": settings.openai_model,
        "database_configured": bool(settings.database_url),
        "meta_webhooks_configured": bool(
            settings.meta_verify_token and settings.meta_app_secret and settings.meta_access_token
        ),
        "retell_configured": bool(settings.retell_api_key and settings.retell_agent_id_en),
        "owner_alert_configured": bool(settings.owner_alert_phone),
    }


@app.get("/webhooks/meta")
def meta_webhook_verify(request: Request) -> Response:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token and token == settings.meta_verify_token and challenge:
        return Response(content=challenge, media_type="text/plain", status_code=200)
    return Response(content="Forbidden", media_type="text/plain", status_code=403)


@app.post("/webhooks/meta")
async def meta_webhook_event(request: Request) -> Response:
    if orchestrator_repo is None:
        return Response(status_code=503)

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
    now_utc = datetime.now(timezone.utc)
    for leadgen_id in lead_ids:
        details = fetch_meta_lead(settings.meta_access_token, leadgen_id)
        phone_e164 = normalize_na_phone_to_e164(details.phone)
        consent_ts = _parse_meta_created_time(details.created_time)
        lead_id, created = orchestrator_repo.create_lead_if_new(
            source="meta",
            meta_lead_id=details.meta_lead_id,
            name=details.full_name,
            phone_e164=phone_e164,
            email=details.email,
            consent_text="Meta Lead Ads opt-in",
            consent_timestamp=consent_ts,
            language="en",
        )
        orchestrator_repo.add_event(
            lead_id=lead_id,
            event_type="meta_lead_webhook_received",
            payload={"raw": payload, "created": created, "leadgen_id": leadgen_id, "lead_details": details.raw},
        )

        run_at = call_window.next_allowed(now_utc)
        orchestrator_repo.enqueue_job(
            job_type="call_lead",
            dedupe_key=f"lead:{lead_id}:call",
            payload={"lead_id": lead_id},
            run_at=run_at,
            max_attempts=3,
        )

        # If the lead arrives outside calling hours, send a single acknowledgement SMS right away.
        if run_at > now_utc:
            delay_seconds = random.randint(3, 15)
            orchestrator_repo.enqueue_job(
                job_type="send_followup_sms",
                dedupe_key=f"lead:{lead_id}:followup",
                payload={"lead_id": lead_id},
                run_at=now_utc + timedelta(seconds=delay_seconds),
                max_attempts=5,
            )

    return Response(status_code=200)


@app.post("/webhooks/retell")
async def retell_webhook(request: Request) -> Response:
    if orchestrator_repo is None:
        return Response(status_code=503)

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
    duration_sec = None
    if isinstance(start_ts, int) and isinstance(end_ts, int) and end_ts >= start_ts:
        duration_sec = int((end_ts - start_ts) / 1000)

    orchestrator_repo.add_event(lead_id=lead_id, event_type=f"retell_{event}", payload=payload)

    if isinstance(retell_call_id, str) and retell_call_id:
        orchestrator_repo.create_call(lead_id=lead_id, retell_call_id=retell_call_id)

    if event in {"call_ended", "call_analyzed"}:
        dedupe_key = f"call:{retell_call_id}:{event}" if isinstance(retell_call_id, str) and retell_call_id else None
        orchestrator_repo.enqueue_job(
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
            run_at=datetime.now(timezone.utc),
            max_attempts=5,
        )

    return Response(status_code=204)


@app.post("/webhooks/twilio/sms")
async def twilio_inbound_sms(request: Request) -> Response:
    if orchestrator_repo is None:
        return Response(status_code=503)

    form = await request.form()
    from_number_raw = str(form.get("From") or "")
    body = str(form.get("Body") or "")
    message_sid = str(form.get("MessageSid") or "")

    from_e164 = normalize_na_phone_to_e164(from_number_raw) or from_number_raw
    lead_id = orchestrator_repo.find_lead_id_by_phone(from_e164) if from_e164.startswith("+") else None
    if not lead_id:
        return Response(status_code=204)

    orchestrator_repo.create_message(
        lead_id=lead_id,
        direction="in",
        channel="sms",
        body=body,
        twilio_message_sid=message_sid or None,
        status="received",
    )
    orchestrator_repo.add_event(
        lead_id=lead_id,
        event_type="twilio_inbound_sms",
        payload={"from": from_e164, "body": body, "message_sid": message_sid},
    )

    if is_stop_message(body):
        orchestrator_repo.set_do_not_contact(lead_id, True)
        orchestrator_repo.set_status(lead_id, "opted_out")
        orchestrator_repo.cancel_jobs_for_lead(lead_id)
        sender.send_sms_to_number(to_number=from_e164, body="You’re opted out. Reply START to resubscribe.")
        return Response(status_code=204)

    if is_start_message(body):
        orchestrator_repo.set_do_not_contact(lead_id, False)
        orchestrator_repo.set_status(lead_id, "resubscribed")
        sender.send_sms_to_number(to_number=from_e164, body="You’re resubscribed. Reply STOP to opt out.")
        return Response(status_code=204)

    return Response(status_code=204)

@app.post("/leads", response_model=Lead)
def create_lead(payload: LeadCreate) -> Lead:
    lead = Lead(**payload.model_dump())
    return service.create_lead(lead)


@app.get("/leads", response_model=list[Lead])
def list_leads() -> list[Lead]:
    return storage.list_leads()


@app.get("/leads/{lead_id}", response_model=Lead)
def get_lead(lead_id: str) -> Lead:
    lead = storage.get_lead(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return lead


@app.patch("/leads/{lead_id}/stage", response_model=Lead)
def update_lead_stage(lead_id: str, payload: StageUpdateRequest) -> Lead:
    try:
        return service.update_stage(lead_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/leads/{lead_id}/messages")
def list_messages(lead_id: str) -> list[dict]:
    return [
        message.model_dump(mode="json")
        for message in storage.list_messages_for_lead(lead_id)
    ]


@app.post("/messages/send")
def send_message(payload: MessageSendRequest) -> dict:
    try:
        message = service.send_message(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return message.model_dump(mode="json")


@app.post("/messages/inbound")
def record_inbound_message(payload: InboundMessageCreate) -> dict:
    try:
        message = service.record_inbound_message(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return message.model_dump(mode="json")


@app.post("/mvp/facebook-leads", response_model=Lead)
def create_facebook_lead(payload: FacebookLeadCreate) -> Lead:
    lead = Lead(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        city=payload.city,
        property_type=payload.property_type,
        preferred_channels=[Channel.sms],
        lead_source="facebook_ad",
    )
    return service.create_lead(lead)


@app.post("/mvp/leads/{lead_id}/start")
def start_mvp_conversation(lead_id: str, payload: ConversationStartRequest) -> dict:
    lead = storage.get_lead(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found.")

    conversation = storage.list_messages_for_lead(lead_id)
    if conversation:
        raise HTTPException(status_code=400, detail="Conversation already started for this lead.")

    delay_seconds = chat_service.wait_like_human(
        inbound_text=None,
        conversation=conversation,
        initial_outreach=True,
    )
    body = chat_service.generate_sms_reply(
        lead=lead,
        conversation=conversation,
        script=payload.script,
        initial_outreach=True,
    )
    service.send_message(
        MessageSendRequest(
            lead_id=lead_id,
            channel=Channel.sms,
            body=body,
            use_template=False,
        )
    )
    messages = storage.list_messages_for_lead(lead_id)
    return {
        "lead_id": lead_id,
        "delay_seconds": delay_seconds,
        "messages": [message.model_dump(mode="json") for message in messages],
    }


@app.post("/mvp/leads/{lead_id}/reply")
def continue_mvp_conversation(lead_id: str, payload: ConversationReplyRequest) -> dict:
    lead = storage.get_lead(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found.")

    service.record_inbound_message(
        InboundMessageCreate(
            lead_id=lead_id,
            channel=Channel.sms,
            body=payload.body,
            sender_name=lead.full_name,
        )
    )
    conversation = storage.list_messages_for_lead(lead_id)
    delay_seconds = chat_service.wait_like_human(
        inbound_text=payload.body,
        conversation=conversation,
        initial_outreach=False,
    )
    body = chat_service.generate_sms_reply(
        lead=lead,
        conversation=conversation,
        script=payload.script,
        initial_outreach=False,
    )
    service.send_message(
        MessageSendRequest(
            lead_id=lead_id,
            channel=Channel.sms,
            body=body,
            use_template=False,
        )
    )
    messages = storage.list_messages_for_lead(lead_id)
    return {
        "lead_id": lead_id,
        "delay_seconds": delay_seconds,
        "messages": [message.model_dump(mode="json") for message in messages],
    }


@app.post("/follow-ups/run")
def run_follow_ups() -> dict[str, object]:
    try:
        messages = service.run_follow_ups()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "sent_count": len(messages),
        "messages": [message.model_dump(mode="json") for message in messages],
    }
