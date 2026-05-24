from __future__ import annotations

import random
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.copilot.chunker import chunk_text, chunk_pdf
from app.services.home_fit_report import HomeFitReportGenerator
from app.copilot.copilot import KnowledgeCopilot, CopilotResponse
from app.copilot.embedder import Embedder
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


storage = JsonStorage(settings.data_file)
sender = ChannelSender(settings)
service = FollowUpService(storage, sender, settings)
chat_service = OpenAIChatService(settings)

orchestrator_repo: OrchestratorRepo | None = None
worker_stop = None
call_scheduler: CallScheduler | None = None
knowledge_copilot: KnowledgeCopilot | None = None


def _parse_meta_created_time(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    global orchestrator_repo, worker_stop, call_scheduler, knowledge_copilot
    # --- Startup ---
    if settings.database_url:
        db = create_database(settings.database_url)
        migrate(db)
        orchestrator_repo = OrchestratorRepo(db=db)
        _thread, worker_stop = start_worker_in_thread(orchestrator_repo, sender, settings)
        call_scheduler = CallScheduler(settings)
        call_scheduler.start()
        print("INFO:     Starting CallScheduler...")

        if settings.openai_api_key:
            from app.orchestrator.openai_extract import OpenAIClient
            _oai = OpenAIClient(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.openai_model,
                temperature=settings.openai_temperature,
            )
            _embedder = Embedder(
                api_key=settings.openai_api_key,
                model=settings.embedding_model,
            )
            knowledge_copilot = KnowledgeCopilot(
                db=db,
                openai_client=_oai,
                embedder=_embedder,
                top_k=settings.copilot_top_k,
            )
            print("INFO:     Knowledge Copilot initialized.")

    yield  # app runs

    # --- Shutdown ---
    if worker_stop is not None:
        worker_stop.set()
    if call_scheduler is not None:
        call_scheduler.stop()


app = FastAPI(
    title="Real Estate Auto Message Bot",
    description="Agentic real estate brokerage — Brampton/GTA lead intake, scoring, and copilot.",
    version="0.3.0",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Real Estate Auto Message Bot is running."}


@app.get("/mvp", response_class=FileResponse)
def mvp_ui() -> FileResponse:
    return FileResponse(settings.ui_file)


@app.get("/dashboard", response_class=FileResponse)
def dashboard_ui() -> FileResponse:
    """Lead scoring dashboard — view all leads with readiness scores and tags."""
    return FileResponse(settings.ui_file.parent / "dashboard.html")


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


# ---------------------------------------------------------------------------
# v2 Endpoints: Lead Profile + Copilot
# ---------------------------------------------------------------------------

@app.get("/leads-scored")
def list_leads_scored(
    tier: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    List leads ordered by readiness score (highest first).
    Optional ?tier=hot|warm|early|cold filter.
    """
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="Database not configured.")
    rows = orchestrator_repo.list_leads_scored(tier=tier, limit=limit, offset=offset)
    result = []
    for row in rows:
        d: dict[str, Any] = {}
        for k, v in row.items():
            d[k] = v.isoformat() if hasattr(v, "isoformat") else v
        result.append(d)
    return result


@app.get("/leads/{lead_id}/profile")
def get_lead_profile(lead_id: str) -> dict[str, Any]:
    """Return lead row with buyer readiness score, tier, tags, and profile."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="Database not configured.")
    profile = orchestrator_repo.get_lead_profile(lead_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Lead not found.")
    # Serialize datetime fields
    result: dict[str, Any] = {}
    for k, v in profile.items():
        if hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


class CopilotQueryRequest(BaseModel):
    query: str
    jurisdiction: str = "ontario"
    audience: str | None = None


class CopilotIngestRequest(BaseModel):
    text: str
    doc_id: str
    source_path: str
    topic: str | None = None
    jurisdiction: str = "ontario"
    audience: str = "agent"
    overwrite: bool = False


class HomeFitReportRequest(BaseModel):
    lead_id: str
    listing: dict[str, Any] | None = None   # None = template mode


class CopilotIngestPDFRequest(BaseModel):
    pdf_path: str          # absolute path on server filesystem
    doc_id: str
    topic: str | None = None
    jurisdiction: str = "ontario"
    audience: str = "agent"
    overwrite: bool = False


@app.post("/copilot/query")
def copilot_query(payload: CopilotQueryRequest) -> dict[str, Any]:
    """
    Query the Ontario Knowledge Copilot.
    Returns answer, sources, risk level, and review flag.
    """
    if knowledge_copilot is None:
        raise HTTPException(
            status_code=503,
            detail="Knowledge Copilot not available. Set OPENAI_API_KEY and DATABASE_URL.",
        )
    response = knowledge_copilot.query(
        payload.query,
        jurisdiction=payload.jurisdiction,
        audience=payload.audience,
    )
    return {
        "query": response.query,
        "answer": response.answer,
        "risk_level": response.risk_level,
        "requires_review": response.requires_review,
        "top_k_used": response.top_k_used,
        "model": response.model_used,
        "sources": [
            {
                "doc_id": s.doc_id,
                "source_path": s.source_path,
                "heading": s.heading,
                "chunk_index": s.chunk_index,
                "risk_level": s.risk_level,
                "similarity": s.similarity,
            }
            for s in response.sources
        ],
    }


@app.post("/copilot/ingest")
def copilot_ingest_text(payload: CopilotIngestRequest) -> dict[str, Any]:
    """
    Ingest plain text or markdown into the knowledge base.
    Chunks, embeds, classifies risk, and stores in knowledge_chunks.
    """
    if knowledge_copilot is None:
        raise HTTPException(
            status_code=503,
            detail="Knowledge Copilot not available. Set OPENAI_API_KEY and DATABASE_URL.",
        )
    chunks = chunk_text(
        payload.text,
        doc_id=payload.doc_id,
        source_path=payload.source_path,
        topic=payload.topic,
        jurisdiction=payload.jurisdiction,
        audience=payload.audience,
    )
    result = knowledge_copilot.ingest_chunks(chunks, overwrite=payload.overwrite)
    return {"doc_id": payload.doc_id, "chunks_generated": len(chunks), **result}


@app.post("/leads/{lead_id}/home-fit-report")
def generate_home_fit_report(lead_id: str, payload: HomeFitReportRequest) -> dict[str, Any]:
    """
    Generate a Home Fit Report for a lead against a listing.
    If listing is omitted, returns template mode (agent fills in scores).
    Requires lead to have a buyer_profile (must have completed a call).
    """
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="Database not configured.")

    profile = orchestrator_repo.get_lead_profile(lead_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Lead not found.")

    buyer_profile = profile.get("buyer_profile") or {}
    # Merge top-level lead fields
    buyer_profile["lead_id"] = lead_id
    buyer_profile["lead_name"] = profile.get("name")

    gen = HomeFitReportGenerator()
    report = gen.generate(buyer_profile, listing=payload.listing)

    return {
        "lead_id": lead_id,
        "lead_name": report.lead_name,
        "listing_address": report.listing_address,
        "listing_price": report.listing_price,
        "mls_number": report.mls_number,
        "overall_score": report.overall_score,
        "fit_tier": report.fit_tier,
        "template_mode": report.template_mode,
        "buyer_signals": report.buyer_signals,
        "agent_notes": report.agent_notes,
        "dimensions": [
            {
                "name": d.name,
                "score": d.score,
                "weight": d.weight,
                "notes": d.notes,
                "flags": d.flags,
            }
            for d in report.dimensions
        ],
    }


@app.post("/copilot/ingest-pdf")
def copilot_ingest_pdf(payload: CopilotIngestPDFRequest) -> dict[str, Any]:
    """
    Ingest a PDF from the server filesystem into the knowledge base.
    The PDF must be accessible at the given path on the server.
    """
    if knowledge_copilot is None:
        raise HTTPException(
            status_code=503,
            detail="Knowledge Copilot not available. Set OPENAI_API_KEY and DATABASE_URL.",
        )
    try:
        chunks = chunk_pdf(
            payload.pdf_path,
            doc_id=payload.doc_id,
            topic=payload.topic,
            jurisdiction=payload.jurisdiction,
            audience=payload.audience,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = knowledge_copilot.ingest_chunks(chunks, overwrite=payload.overwrite)
    return {"doc_id": payload.doc_id, "chunks_generated": len(chunks), **result}
