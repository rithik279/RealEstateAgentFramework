from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Channel(str, Enum):
    email = "email"
    sms = "sms"
    facebook = "facebook"


class LeadStatus(str, Enum):
    new = "new"
    nurturing = "nurturing"
    replied = "replied"
    booked = "booked"
    closed = "closed"
    archived = "archived"


class LeadStage(str, Enum):
    new_lead = "new_lead"
    contacted = "contacted"
    booked_consult = "booked_consult"
    homes_sent = "homes_sent"
    showing_booked = "showing_booked"


class MessageDirection(str, Enum):
    outbound = "outbound"
    inbound = "inbound"


class LeadBase(BaseModel):
    full_name: str = Field(..., min_length=2)
    email: str | None = None
    phone: str | None = None
    facebook_psid: str | None = None
    preferred_channels: list[Channel] = Field(default_factory=list)
    language_preference: str = "English"
    city: str = "Brampton"
    neighborhoods: list[str] = Field(default_factory=list)
    property_type: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    budget_notes: str | None = None
    lead_source: str | None = None
    notes: str | None = None


class LeadCreate(LeadBase):
    pass


class Lead(LeadBase):
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: LeadStatus = LeadStatus.new
    stage: LeadStage = LeadStage.new_lead
    message_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    last_contacted_at: datetime | None = None
    last_replied_at: datetime | None = None
    next_follow_up_at: datetime = Field(default_factory=lambda: utc_now())
    booked_call_at: datetime | None = None


class MessageRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    lead_id: str
    channel: Channel
    direction: MessageDirection
    body: str
    subject: str | None = None
    provider_status: str = "queued"
    provider_message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class MessageSendRequest(BaseModel):
    lead_id: str
    channel: Channel
    body: str | None = None
    subject: str | None = None
    template_key: str | None = None
    use_template: bool = True


class InboundMessageCreate(BaseModel):
    lead_id: str
    channel: Channel
    body: str
    sender_name: str | None = None


class StageUpdateRequest(BaseModel):
    stage: LeadStage
    status: LeadStatus | None = None


class FacebookLeadCreate(BaseModel):
    full_name: str = Field(..., min_length=2)
    email: str | None = None
    phone: str | None = None
    city: str = "Brampton"
    property_type: str | None = None


class ConversationStartRequest(BaseModel):
    script: str | None = None


class ConversationReplyRequest(BaseModel):
    body: str = Field(..., min_length=1)
    script: str | None = None


class SendResult(BaseModel):
    status: str
    provider_message_id: str | None = None
    detail: str


class StoreData(BaseModel):
    leads: list[Lead] = Field(default_factory=list)
    messages: list[MessageRecord] = Field(default_factory=list)
