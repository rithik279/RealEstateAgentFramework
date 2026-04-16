from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
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
        "booking_link_configured": bool(settings.booking_link),
        "openai_configured": bool(settings.openai_api_key),
        "openai_model": settings.openai_model,
    }


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
