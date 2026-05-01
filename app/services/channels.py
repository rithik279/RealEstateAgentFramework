from __future__ import annotations

import smtplib
from email.message import EmailMessage
from uuid import uuid4

import httpx

from app.config import Settings
from app.models import Channel, Lead, SendResult


class ChannelSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(
        self,
        lead: Lead,
        channel: Channel,
        body: str,
        subject: str | None = None,
    ) -> SendResult:
        if channel == Channel.email:
            return self._send_email(lead, body, subject)
        if channel == Channel.sms:
            return self._send_sms(lead, body)
        if channel == Channel.facebook:
            return self._send_facebook_message(lead, body)
        raise ValueError(f"Unsupported channel: {channel}")

    def _simulated(self, detail: str) -> SendResult:
        return SendResult(
            status="simulated",
            provider_message_id=f"dry-run-{uuid4()}",
            detail=detail,
        )

    def _send_email(self, lead: Lead, body: str, subject: str | None) -> SendResult:
        if not lead.email:
            return SendResult(status="failed", detail="Lead is missing an email address.")
        if self.settings.dry_run:
            return self._simulated("Email send skipped because APP_DRY_RUN is true.")

        message = EmailMessage()
        message["From"] = self.settings.smtp_from_email
        message["To"] = lead.email
        message["Subject"] = subject or "Quick follow-up on your home search"
        message.set_content(body)

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as server:
            server.starttls()
            server.login(self.settings.smtp_username, self.settings.smtp_password)
            server.send_message(message)

        return SendResult(
            status="sent",
            provider_message_id=f"email-{uuid4()}",
            detail="Email sent successfully.",
        )

    def _send_sms(self, lead: Lead, body: str) -> SendResult:
        if not lead.phone:
            return SendResult(status="failed", detail="Lead is missing a phone number.")
        if self.settings.dry_run:
            return self._simulated("SMS send skipped because APP_DRY_RUN is true.")

        return self.send_sms_to_number(to_number=lead.phone, body=body)

    def send_sms_to_number(self, *, to_number: str, body: str) -> SendResult:
        if self.settings.dry_run:
            return self._simulated("SMS send skipped because APP_DRY_RUN is true.")

        response = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{self.settings.twilio_account_sid}/Messages.json",
            auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token),
            data={
                "From": self.settings.twilio_from_number,
                "To": to_number,
                "Body": body,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        return SendResult(
            status=payload.get("status", "sent"),
            provider_message_id=payload.get("sid"),
            detail="SMS request accepted by Twilio.",
        )

    def _send_facebook_message(self, lead: Lead, body: str) -> SendResult:
        if not lead.facebook_psid:
            return SendResult(
                status="failed",
                detail="Lead is missing a Facebook Page-Scoped ID.",
            )
        if self.settings.dry_run:
            return self._simulated("Facebook send skipped because APP_DRY_RUN is true.")

        response = httpx.post(
            "https://graph.facebook.com/v23.0/me/messages",
            params={"access_token": self.settings.meta_page_access_token},
            json={
                "recipient": {"id": lead.facebook_psid},
                "messaging_type": "RESPONSE",
                "message": {"text": body},
            },
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        return SendResult(
            status="sent",
            provider_message_id=payload.get("message_id"),
            detail="Facebook Messenger message sent.",
        )
