from __future__ import annotations

import random
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import ROOT_DIR, settings
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
from app.api.admin import router as admin_router
from app.api.curate_homes import router as curate_homes_router


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

        # Daily reactivation SMS seed — fires at 4 PM Toronto, seeds 20 jobs
        from app.orchestrator.reactivation import seed_reactivation_sms_jobs as _seed_fn
        call_scheduler.schedule_job(
            lambda: _seed_fn(
                db=db,
                tz=settings.app_timezone,
                window_start_hour=settings.reactivation_sms_window_start,
                window_end_hour=settings.reactivation_sms_window_end,
                daily_limit=settings.reactivation_sms_daily_limit,
            ),
            trigger="cron",
            cron_hour=settings.reactivation_sms_window_start,
            cron_minute=0,
            id="daily_reactivation_sms_seed",
        )
        print("INFO:     Reactivation SMS drip scheduled (daily 4 PM Toronto).")

        from app.orchestrator.reactivation import seed_reactivation_call_jobs as _seed_call_fn
        call_scheduler.schedule_job(
            lambda: _seed_call_fn(
                db=db,
                tz=settings.app_timezone,
                window_start_hour=settings.call_window_start_hour,
                window_end_hour=settings.call_window_end_hour,
                daily_limit=20,
                interval_minutes=5,  # HARD RULE: min 5 min between calls, never reduce
            ),
            trigger="cron",
            cron_hour=settings.call_window_start_hour,
            cron_minute=0,
            id="daily_reactivation_call_seed",
        )
        print("INFO:     Reactivation call drip scheduled (daily 9 AM Toronto, 1 call/5 min).")

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

app.include_router(admin_router)
app.include_router(curate_homes_router)

site_dir = ROOT_DIR / "site"


@app.get("/", response_class=FileResponse)
def root() -> FileResponse:
    return FileResponse(site_dir / "index.html")


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    return {
        "status": "ok",
        "message": "Real Estate Agentic Brokerage API",
        "version": "0.3.0",
    }


@app.middleware("http")
async def require_auth_middleware(request: Request, call_next: Any) -> Any:
    """Protect all internal dashboard routes with session auth."""
    from fastapi.responses import JSONResponse, RedirectResponse as _Redirect
    from app.auth import SESSION_COOKIE, verify_session_token

    path = request.url.path

    PROTECTED_PREFIXES = (
        "/leads", "/reactivation", "/admin",
        "/mls/chat", "/mls/sync",
        "/listings", "/copilot",
        "/mvp", "/dashboard",
    )
    # Always public even if they start with a protected prefix
    PUBLIC_PREFIXES = ("/webhooks/", "/api/curate-homes")
    PUBLIC_EXACT = {
        "/health", "/login", "/control", "/", "/api/status", "/config-status",
        "/admin/login", "/admin/logout",   # auth endpoints must stay public
    }

    needs_auth = (
        path.startswith(PROTECTED_PREFIXES)
        and path not in PUBLIC_EXACT
        and not any(path.startswith(p) for p in PUBLIC_PREFIXES)
    )

    if needs_auth:
        token = request.cookies.get(SESSION_COOKIE)
        if not token or not verify_session_token(token):
            accept = request.headers.get("accept", "")
            if "text/html" in accept:
                return _Redirect(url="/login", status_code=302)
            return JSONResponse({"detail": "Not authenticated."}, status_code=401)

    return await call_next(request)


@app.get("/mvp", response_class=FileResponse)
def mvp_ui() -> FileResponse:
    return FileResponse(settings.ui_file)


@app.get("/dashboard")
def dashboard_ui() -> Any:
    """Redirect old dashboard URL to control center."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/control", status_code=302)


@app.get("/login", response_class=FileResponse)
def login_page() -> FileResponse:
    return FileResponse(settings.ui_file.parent / "login.html")


@app.get("/control")
def control_center(request: Request) -> Any:
    """Agent control center — requires authentication."""
    from app.auth import SESSION_COOKIE, verify_session_token
    token = request.cookies.get(SESSION_COOKIE)
    if not token or not verify_session_token(token):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse(settings.ui_file.parent / "control.html")


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


class IngestKBRequest(BaseModel):
    overwrite: bool = False


@app.post("/copilot/ingest-kb")
def copilot_ingest_kb(payload: IngestKBRequest = IngestKBRequest()) -> dict[str, Any]:
    """
    Walk the knowledge-base/ folder and ingest all .md, .txt, .pdf files.
    One-click bulk ingestion — no CLI needed.
    """
    if knowledge_copilot is None:
        raise HTTPException(
            status_code=503,
            detail="Knowledge Copilot not available. Set OPENAI_API_KEY and DATABASE_URL.",
        )

    from pathlib import Path

    FOLDER_METADATA: dict[str, dict] = {
        "reco": {"topic": "reco_obligations", "jurisdiction": "ontario", "audience": "agent"},
        "orea": {"topic": "orea_forms", "jurisdiction": "ontario", "audience": "agent"},
        "fsra": {"topic": "fsra_mortgage", "jurisdiction": "ontario", "audience": "agent"},
        "brampton": {"topic": "brampton_market", "jurisdiction": "ontario", "audience": "agent"},
        "internal": {"topic": "internal_process", "jurisdiction": "ontario", "audience": "agent"},
    }

    kb_path = Path(settings.knowledge_base_path)
    if not kb_path.exists():
        raise HTTPException(status_code=404, detail=f"knowledge-base path not found: {kb_path}")

    total_chunks = 0
    total_inserted = 0
    total_skipped = 0
    files_processed: list[str] = []
    files_errored: list[dict] = []

    for folder in kb_path.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        meta = FOLDER_METADATA.get(
            folder.name,
            {"topic": folder.name, "jurisdiction": "ontario", "audience": "agent"},
        )
        for file in folder.iterdir():
            if file.suffix.lower() not in (".md", ".txt", ".pdf"):
                continue
            doc_id = f"{folder.name}/{file.stem}"
            try:
                if file.suffix.lower() == ".pdf":
                    chunks = chunk_pdf(str(file), doc_id=doc_id, source_path=str(file), **meta)
                else:
                    text = file.read_text(encoding="utf-8", errors="replace")
                    chunks = chunk_text(text, doc_id=doc_id, source_path=str(file), **meta)

                result = knowledge_copilot.ingest_chunks(chunks, overwrite=payload.overwrite)
                total_chunks += len(chunks)
                total_inserted += result.get("inserted", 0)
                total_skipped += result.get("skipped", 0)
                files_processed.append(doc_id)
            except Exception as exc:
                files_errored.append({"file": doc_id, "error": str(exc)})

    return {
        "files_processed": len(files_processed),
        "files_errored": len(files_errored),
        "total_chunks": total_chunks,
        "total_inserted": total_inserted,
        "total_skipped": total_skipped,
        "errored": files_errored,
    }


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


# ---------------------------------------------------------------------------
# MLS / RESO listing endpoints
# ---------------------------------------------------------------------------

class MLSSyncRequest(BaseModel):
    city: str = "Brampton"
    price_min: int = 500_000
    price_max: int = 2_000_000


class ListingSearchRequest(BaseModel):
    city: str = "Brampton"
    price_min: int | None = None
    price_max: int | None = None
    bedrooms_min: int | None = None
    property_type: str | None = None
    limit: int = 20


@app.get("/mls/status")
def mls_status() -> dict[str, Any]:
    """Check PropTx RESO API configuration status."""
    from app.services.mls_client import create_reso_client, MLSNotConfiguredError
    try:
        client = create_reso_client()
        return {
            "configured": True,
            "base_url": client.base_url,
            "auth_method": "api_key" if client.api_key else "basic",
        }
    except MLSNotConfiguredError as e:
        return {"configured": False, "message": str(e)}


@app.post("/mls/sync")
def mls_sync(payload: MLSSyncRequest) -> dict[str, Any]:
    """
    Trigger listing sync from PropTx RESO API.
    Requires PROPTX_BASE_URL + credentials set in env.
    """
    from app.services.mls_client import create_reso_client, ListingIngester, MLSNotConfiguredError
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="Database not configured.")
    try:
        client = create_reso_client()
    except MLSNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))
    ingester = ListingIngester(client=client, db=orchestrator_repo.db)
    result = ingester.sync_active_listings(
        city=payload.city,
        price_min=payload.price_min,
        price_max=payload.price_max,
    )
    return {"city": payload.city, **result}


def _proptx_client():
    from app.services.proptx import PropTXClient
    if not settings.proptx_token:
        raise HTTPException(status_code=503, detail="PROPTX_TOKEN not configured")
    return PropTXClient(token=settings.proptx_token, base_url=settings.proptx_base_url)


@app.get("/listings/search")
def listings_search(
    city: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_bedrooms: int | None = None,
    transaction_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search active MLS listings via PropTX (Amplify Syndication)."""
    client = _proptx_client()
    cities = [city] if city else None
    listings = client.search(
        cities=cities,
        min_price=min_price,
        max_price=max_price,
        min_bedrooms=min_bedrooms,
        transaction_type=transaction_type,
        limit=min(limit, 50),
    )
    return {"count": len(listings), "listings": [l.to_dict() for l in listings]}


@app.get("/listings/{listing_key}")
def listing_get(listing_key: str) -> dict[str, Any]:
    """Fetch single listing by ListingKey from PropTX."""
    client = _proptx_client()
    listing = client.get_listing(listing_key)
    if not listing:
        raise HTTPException(status_code=404, detail=f"Listing {listing_key} not found")
    return listing.to_dict()


@app.get("/leads/{lead_id}/listings")
def lead_matched_listings(lead_id: str, limit: int = 10) -> dict[str, Any]:
    """Return active MLS listings matched to a lead's buyer profile."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    extracted = orchestrator_repo.get_latest_extracted_json(lead_id)
    if not extracted:
        raise HTTPException(status_code=404, detail="No buyer profile found for this lead. Lead must have completed a call first.")
    client = _proptx_client()
    listings = client.search_for_buyer(extracted, limit=min(limit, 20))
    return {
        "lead_id": lead_id,
        "buyer_profile_summary": {
            "budget_max": extracted.get("budget_max"),
            "preferred_areas": extracted.get("preferred_areas"),
            "min_bedrooms": extracted.get("min_bedrooms"),
            "property_type": extracted.get("property_type"),
        },
        "count": len(listings),
        "listings": [l.to_dict() for l in listings],
    }


class MLSChatRequest(BaseModel):
    query: str
    limit: int = 10


@app.post("/mls/chat")
def mls_chat(payload: MLSChatRequest) -> dict[str, Any]:
    """Natural language MLS search: OpenAI parses query → PropTX search → photos."""
    import json as _json
    from app.orchestrator.openai_extract import OpenAIClient

    client = _proptx_client()

    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    ai = OpenAIClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        temperature=0.0,
    )

    parse_prompt = (
        "Parse this real estate search query and return ONLY valid JSON with these exact fields:\n"
        "{\n"
        '  "cities": ["City"] or null,\n'
        '  "property_types": ["Type"] or null,\n'
        '  "transaction_type": "For Sale" or "For Lease" or null,\n'
        '  "min_price": number or null,\n'
        '  "max_price": number or null,\n'
        '  "min_bedrooms": integer or null,\n'
        '  "limit": integer (from query like "find me 5", default 10, max 20),\n'
        '  "interpretation": "brief plain English summary of what we are searching"\n'
        "}\n\n"
        "GTA city names: Brampton, Mississauga, Toronto, Vaughan, Markham, Richmond Hill, "
        "Oakville, Burlington, Caledon, Halton Hills, Milton, Hamilton, Kitchener, London.\n"
        'PropertyType values: "Residential Freehold" (houses/detached/semi/townhouse/row), '
        '"Residential Condo & Other" (condos/stacked), "Commercial" (retail/office/industrial/commercial).\n'
        "Return ONLY the JSON object, no markdown, no backticks.\n\n"
        f"Query: {payload.query}"
    )

    try:
        raw_payload = ai._responses(parse_prompt)
        text = ai._extract_text(raw_payload).strip()
        # Strip markdown fences if model adds them
        if "```" in text:
            parts = text.split("```")
            text = parts[1].lstrip("json").strip() if len(parts) > 1 else text
        params = _json.loads(text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse query: {exc}")

    limit = min(int(params.get("limit") or payload.limit or 10), 20)

    try:
        listings = client.search(
            cities=params.get("cities") or None,
            min_price=params.get("min_price"),
            max_price=params.get("max_price"),
            min_bedrooms=params.get("min_bedrooms"),
            property_types=params.get("property_types") or None,
            transaction_type=params.get("transaction_type") or None,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PropTX error: {exc}")

    results = []
    for listing in listings:
        d = listing.to_dict()
        media = client.get_media(listing.listing_key, limit=1)
        d["photo_url"] = media[0].get("MediaURL") if media else None
        results.append(d)

    return {
        "interpretation": params.get("interpretation", ""),
        "search_params": {k: v for k, v in params.items() if k != "interpretation"},
        "count": len(results),
        "listings": results,
    }


# Keep old route for backward compat
@app.post("/mls/search")
def mls_search_legacy(
    city: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Deprecated — use GET /listings/search instead."""
    return listings_search(city=city, min_price=min_price, max_price=max_price, limit=limit)


# ---------------------------------------------------------------------------
# Reactivation SMS drip
# ---------------------------------------------------------------------------

@app.get("/reactivation/report")
def reactivation_report() -> dict[str, Any]:
    """Daily reactivation SMS drip stats — sent, queued, replies, remaining."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    from app.orchestrator.reactivation import daily_reactivation_report
    return daily_reactivation_report(db=orchestrator_repo.db, tz=settings.app_timezone)


@app.post("/reactivation/seed")
def reactivation_seed_now() -> dict[str, Any]:
    """Manually trigger today's reactivation SMS seed (bypass daily schedule)."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    from app.orchestrator.reactivation import seed_reactivation_sms_jobs
    count = seed_reactivation_sms_jobs(
        db=orchestrator_repo.db,
        tz=settings.app_timezone,
        window_start_hour=settings.reactivation_sms_window_start,
        window_end_hour=settings.reactivation_sms_window_end,
        daily_limit=settings.reactivation_sms_daily_limit,
    )
    return {"seeded": count, "daily_limit": settings.reactivation_sms_daily_limit}


@app.get("/reactivation")
def reactivation_ui() -> Any:
    """Redirect reactivation page to control center (reactivation tab)."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/control", status_code=302)


@app.get("/reactivation/replies")
def reactivation_replies(limit: int = 200) -> list[dict[str, Any]]:
    """
    All legacy_reactivation leads that have sent at least one inbound SMS.
    Returns lead info + last inbound message for inbox view.
    """
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    with orchestrator_repo.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                    l.id          as lead_id,
                    l.name,
                    l.phone_e164  as phone,
                    l.area,
                    l.status,
                    l.do_not_contact as opted_out,
                    m.body        as last_inbound_body,
                    m.created_at  as last_inbound_at,
                    (
                        select max((j.payload->>'touch')::int)
                        from jobs j
                        where j.type = 'reactivation_sms'
                          and j.status = 'done'
                          and j.payload->>'lead_id' = l.id
                    ) as touch_sent
                from leads l
                join messages m on m.lead_id = l.id
                where l.source = 'legacy_reactivation'
                  and m.direction = 'in'
                  and m.channel = 'sms'
                  and m.created_at = (
                      select max(m2.created_at) from messages m2
                      where m2.lead_id = l.id and m2.direction = 'in' and m2.channel = 'sms'
                  )
                order by m.created_at desc
                limit %s
                """,
                (limit,),
            )
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()
    result = []
    for row in rows:
        d = dict(zip(cols, row))
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        result.append(d)
    return result


@app.get("/reactivation/thread/{lead_id}")
def reactivation_thread(lead_id: str) -> list[dict[str, Any]]:
    """Full SMS thread (in + out) for a reactivation lead."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    with orchestrator_repo.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select direction, body, created_at, status
                from messages
                where lead_id = %s and channel = 'sms'
                order by created_at asc
                limit 200
                """,
                (lead_id,),
            )
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()
    result = []
    for row in rows:
        d = dict(zip(cols, row))
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        result.append(d)
    return result


@app.get("/reactivation/queue")
def reactivation_queue(limit: int = 100) -> list[dict[str, Any]]:
    """Upcoming queued reactivation SMS jobs with lead info."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    with orchestrator_repo.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                    j.id, j.run_at, j.status,
                    j.payload->>'lead_id' as lead_id,
                    (j.payload->>'touch')::int as touch,
                    j.payload->>'body' as body,
                    coalesce(l.name, l.phone_e164, 'Unknown') as name,
                    l.phone_e164 as phone, l.area
                from jobs j
                left join leads l on l.id = (j.payload->>'lead_id')
                where j.type = 'reactivation_sms'
                  and j.status = 'queued'
                order by j.run_at asc
                limit %s
                """,
                (limit,),
            )
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()
    result = []
    for row in rows:
        d = dict(zip(cols, row))
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        result.append(d)
    return result


@app.get("/reactivation/calls")
def reactivation_calls(limit: int = 200) -> list[dict[str, Any]]:
    """Recent calls for legacy_reactivation leads with transcript."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    with orchestrator_repo.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                    c.id, c.retell_call_id, c.started_at, c.ended_at,
                    c.duration_sec, c.outcome, c.disconnection_reason,
                    c.transcript_text,
                    l.id as lead_id, l.name, l.phone_e164 as phone, l.area
                from calls c
                join leads l on l.id = c.lead_id
                where l.source = 'legacy_reactivation'
                order by c.started_at desc nulls last
                limit %s
                """,
                (limit,),
            )
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()
    result = []
    for row in rows:
        d = dict(zip(cols, row))
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Reactivation job queue management
# ---------------------------------------------------------------------------

@app.get("/reactivation/jobs")
def reactivation_jobs(status: str = "queued", limit: int = 100) -> list[dict[str, Any]]:
    """List scheduled call/SMS jobs for reactivation leads."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    statuses = status.split(",")
    with orchestrator_repo.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select j.id, j.type, j.status, j.run_at, j.attempts, j.last_error,
                       l.id as lead_id,
                       coalesce(l.name, l.phone_e164, 'Unknown') as name,
                       l.phone_e164 as phone, l.area
                from jobs j
                left join leads l on l.id = (j.payload->>'lead_id')
                where j.type in ('call_lead','reactivation_sms','send_followup_sms')
                  and j.status = any(%s)
                order by j.run_at asc nulls last
                limit %s
                """,
                (statuses, limit),
            )
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()
    result = []
    for row in rows:
        d = dict(zip(cols, row))
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        result.append(d)
    return result


@app.post("/reactivation/jobs/seed-calls")
def seed_reactivation_calls_now(daily_limit: int = 20, interval_minutes: int = 5) -> dict[str, Any]:
    """Manually trigger today's reactivation call seeding."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    if interval_minutes < 5:
        raise HTTPException(status_code=400, detail="interval_minutes must be >= 5 (hard rule)")
    if daily_limit > 50:
        raise HTTPException(status_code=400, detail="daily_limit max 50")
    from app.orchestrator.reactivation import seed_reactivation_call_jobs
    count = seed_reactivation_call_jobs(
        db=orchestrator_repo.db,
        tz=settings.app_timezone,
        window_start_hour=settings.call_window_start_hour,
        window_end_hour=settings.call_window_end_hour,
        daily_limit=daily_limit,
        interval_minutes=interval_minutes,
    )
    return {"seeded": count, "interval_minutes": interval_minutes, "daily_limit": daily_limit}


@app.post("/reactivation/jobs/seed-sms")
def seed_reactivation_sms_now(daily_limit: int = 20) -> dict[str, Any]:
    """Manually trigger today's reactivation SMS seeding."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    if daily_limit > 50:
        raise HTTPException(status_code=400, detail="daily_limit max 50")
    from app.orchestrator.reactivation import seed_reactivation_sms_jobs
    count = seed_reactivation_sms_jobs(
        db=orchestrator_repo.db,
        tz=settings.app_timezone,
        window_start_hour=settings.reactivation_sms_window_start,
        window_end_hour=settings.reactivation_sms_window_end,
        daily_limit=daily_limit,
    )
    return {"seeded": count, "daily_limit": daily_limit}


@app.delete("/reactivation/jobs/{job_id}")
def cancel_reactivation_job(job_id: int) -> dict[str, Any]:
    """Cancel a queued reactivation job."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    with orchestrator_repo.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs SET status='cancelled'
                WHERE id=%s AND status='queued'
                AND type in ('call_lead','reactivation_sms','send_followup_sms')
                RETURNING id
                """,
                (job_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found or not cancellable")
    return {"cancelled": job_id}


# ---------------------------------------------------------------------------
# SMS queue admin — bulk cancel + diagnostics
# ---------------------------------------------------------------------------

@app.post("/admin/sms-queue/cancel-all")
def cancel_all_sms_jobs() -> dict[str, Any]:
    """Cancel all queued SMS jobs (send_followup_sms + reactivation_sms). Does NOT touch calls."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    with orchestrator_repo.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs SET status='cancelled'
                WHERE status='queued'
                  AND type IN ('send_followup_sms', 'reactivation_sms', 'classify_sms_reply')
                RETURNING id, type
                """
            )
            rows = cur.fetchall()
        conn.commit()
    by_type: dict[str, int] = {}
    for _, jtype in rows:
        by_type[jtype] = by_type.get(jtype, 0) + 1
    return {"cancelled": len(rows), "by_type": by_type}


@app.get("/admin/sms-queue/diagnostics")
def sms_queue_diagnostics() -> dict[str, Any]:
    """Count queued SMS jobs, orphaned jobs (no matching lead), and leads eligible for fresh campaign."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    with orchestrator_repo.db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE j.type IN ('send_followup_sms','reactivation_sms') AND j.status='queued') AS queued_sms,
                  COUNT(*) FILTER (WHERE j.type IN ('send_followup_sms','reactivation_sms') AND j.status='queued'
                                     AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.id = j.payload->>'lead_id')) AS orphaned,
                  COUNT(*) FILTER (WHERE j.type = 'call_lead' AND j.status='queued') AS queued_calls
                FROM jobs j
                """
            )
            row = cur.fetchone()
            cur.execute(
                """
                SELECT COUNT(*) FROM leads
                WHERE do_not_contact = false
                  AND phone_e164 IS NOT NULL
                  AND status NOT IN ('opted_out','needs_review','booked','closed','archived')
                  AND NOT EXISTS (
                    SELECT 1 FROM jobs j
                    WHERE j.type IN ('send_followup_sms','reactivation_sms')
                      AND j.status = 'queued'
                      AND j.payload->>'lead_id' = leads.id
                  )
                """
            )
            eligible = cur.fetchone()[0]
    return {
        "queued_sms": row[0],
        "orphaned_jobs": row[1],
        "queued_calls": row[2],
        "eligible_for_fresh_campaign": eligible,
    }


# ---------------------------------------------------------------------------
# Audit log (compliance — RECO best practice)
# ---------------------------------------------------------------------------

@app.get("/audit-log")
def get_audit_log(entity_type: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Compliance audit log — all AI outputs, data access, listing views."""
    if orchestrator_repo is None:
        raise HTTPException(status_code=503, detail="Database not configured.")
    try:
        with orchestrator_repo.db.connect() as conn:
            with conn.cursor() as cur:
                if entity_type:
                    cur.execute(
                        "SELECT * FROM audit_log WHERE entity_type = %s "
                        "ORDER BY created_at DESC LIMIT %s",
                        (entity_type, limit),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT %s",
                        (limit,),
                    )
                rows = cur.fetchall()
                cols = [d.name for d in cur.description] if cur.description else []
                return {"entries": [dict(zip(cols, r)) for r in rows], "total": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/{page}", response_class=FileResponse)
def serve_site_page(page: str) -> FileResponse:
    file_path = site_dir / f"{page}.html"
    if file_path.exists():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Not Found")
