from __future__ import annotations

from datetime import timedelta

from app.config import Settings
from app.models import (
    Channel,
    InboundMessageCreate,
    Lead,
    LeadStage,
    LeadStatus,
    MessageDirection,
    MessageRecord,
    MessageSendRequest,
    StageUpdateRequest,
    utc_now,
)
from app.services.channels import ChannelSender
from app.services.templates import render_sequence_message
from app.storage import JsonStorage


class FollowUpService:
    def __init__(
        self,
        storage: JsonStorage,
        sender: ChannelSender,
        settings: Settings,
    ) -> None:
        self.storage = storage
        self.sender = sender
        self.settings = settings

    def create_lead(self, payload: Lead) -> Lead:
        return self.storage.create_lead(payload)

    def update_stage(self, lead_id: str, request: StageUpdateRequest) -> Lead:
        lead = self.storage.get_lead(lead_id)
        if lead is None:
            raise ValueError("Lead not found.")

        lead.stage = request.stage
        if request.status is not None:
            lead.status = request.status

        if request.stage == LeadStage.booked_consult:
            lead.booked_call_at = utc_now()

        return self.storage.update_lead(lead)

    def send_message(self, request: MessageSendRequest) -> MessageRecord:
        lead = self.storage.get_lead(request.lead_id)
        if lead is None:
            raise ValueError("Lead not found.")

        body = request.body
        subject = request.subject

        if request.use_template and not body:
            step = lead.message_count
            subject, body = render_sequence_message(
                lead=lead,
                channel=request.channel,
                step=step,
                settings=self.settings,
            )

        if not body:
            raise ValueError("Message body is empty.")

        result = self.sender.send(lead, request.channel, body, subject)
        message = MessageRecord(
            lead_id=lead.id,
            channel=request.channel,
            direction=MessageDirection.outbound,
            body=body,
            subject=subject,
            provider_status=result.status,
            provider_message_id=result.provider_message_id,
            metadata={"detail": result.detail, "message_step": lead.message_count},
        )
        self.storage.add_message(message)

        lead.status = LeadStatus.nurturing
        lead.last_contacted_at = utc_now()
        lead.message_count += 1
        lead.stage = LeadStage.contacted
        lead.next_follow_up_at = utc_now() + self._next_delay(lead.message_count)
        self.storage.update_lead(lead)
        return message

    def record_inbound_message(self, inbound: InboundMessageCreate) -> MessageRecord:
        lead = self.storage.get_lead(inbound.lead_id)
        if lead is None:
            raise ValueError("Lead not found.")

        lead.status = LeadStatus.replied
        lead.last_replied_at = utc_now()
        self.storage.update_lead(lead)

        message = MessageRecord(
            lead_id=inbound.lead_id,
            channel=inbound.channel,
            direction=MessageDirection.inbound,
            body=inbound.body,
            provider_status="received",
            metadata={"sender_name": inbound.sender_name},
        )
        return self.storage.add_message(message)

    def run_follow_ups(self) -> list[MessageRecord]:
        created_messages: list[MessageRecord] = []
        now = utc_now()

        for lead in self.storage.list_leads():
            if lead.status in {LeadStatus.replied, LeadStatus.booked, LeadStatus.closed, LeadStatus.archived}:
                continue
            if lead.message_count >= 4:
                continue
            if lead.next_follow_up_at > now:
                continue

            channel = self._pick_channel(lead)
            request = MessageSendRequest(
                lead_id=lead.id,
                channel=channel,
                use_template=True,
            )
            created_messages.append(self.send_message(request))

        return created_messages

    def _pick_channel(self, lead: Lead) -> Channel:
        for channel in lead.preferred_channels:
            if channel == Channel.email and lead.email:
                return channel
            if channel == Channel.sms and lead.phone:
                return channel
            if channel == Channel.facebook and lead.facebook_psid:
                return channel

        if lead.phone:
            return Channel.sms
        if lead.email:
            return Channel.email
        if lead.facebook_psid:
            return Channel.facebook
        raise ValueError("Lead has no reachable channel.")

    def _next_delay(self, message_count: int) -> timedelta:
        if message_count == 1:
            return timedelta(hours=24)
        if message_count == 2:
            return timedelta(hours=24)
        if message_count == 3:
            return timedelta(hours=48)
        return timedelta(days=7)