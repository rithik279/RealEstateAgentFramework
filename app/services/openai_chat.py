from __future__ import annotations

import hashlib
import re
from time import sleep
from textwrap import dedent

import httpx

from app.config import Settings
from app.models import Lead, MessageDirection, MessageRecord


class OpenAIChatService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_sms_reply(
        self,
        lead: Lead,
        conversation: list[MessageRecord],
        script: str | None = None,
        initial_outreach: bool = False,
    ) -> str:
        if not self.settings.openai_api_key:
            return self._fallback_reply(lead, conversation, initial_outreach)

        prompt = self._build_prompt(lead, conversation, script, initial_outreach)
        try:
            response_json = self._create_response(prompt)
            reply = self._extract_text(response_json).strip()
            final_reply = reply or self._fallback_reply(lead, conversation, initial_outreach)
            return self._humanize_reply(final_reply, conversation, initial_outreach)
        except httpx.HTTPError:
            fallback = self._fallback_reply(lead, conversation, initial_outreach)
            return self._humanize_reply(fallback, conversation, initial_outreach)

    def _build_prompt(
        self,
        lead: Lead,
        conversation: list[MessageRecord],
        script: str | None,
        initial_outreach: bool,
    ) -> str:
        transcript_lines: list[str] = []
        for message in conversation:
            speaker = "Agent" if message.direction == MessageDirection.outbound else "Lead"
            transcript_lines.append(f"{speaker}: {message.body}")

        transcript = "\n".join(transcript_lines) or "No conversation yet."
        script_block = script.strip() if script and script.strip() else "No custom script provided."
        outreach_context = (
            "This is the first outbound text after a Facebook ad lead came in."
            if initial_outreach
            else "Continue the existing SMS conversation naturally."
        )

        return dedent(
            f"""
            You are texting a real estate lead like a warm, capable realtor or ISA.
            Sound human, local, and conversational. Never mention being an AI.

            Objective:
            - Build trust quickly.
            - Keep the lead engaged over SMS.
            - Ask one natural next question at a time.
            - Learn their home preferences and relevant personal context.

            Information to gradually uncover:
            - Target city or neighborhoods
            - Budget or monthly comfort range
            - Timeline to move
            - Property type
            - Bedroom/bathroom needs
            - Whether they need to sell first or are pre-approved
            - Family/lifestyle details only when natural and relevant

            Style rules:
            - 1 to 4 short sentences.
            - Friendly SMS tone, not corporate.
            - No bullet points, no markdown.
            - Do not ask more than 2 questions in one message.
            - Reference the lead's details when useful.
            - If the lead asks a question, answer it first, then guide the conversation.
            - If the lead seems hesitant, reduce pressure and keep it helpful.
            - In longer conversations, it is okay to very occasionally make one small natural spelling mistake and self-correct it inline, like "seperate*separate". Do this rarely, not in every message.

            Business context:
            - Company: {self.settings.company_name}
            - Advisor name: {self.settings.advisor_name}
            - Booking link: {self.settings.booking_link}
            - Lead source: Facebook ad
            - Outreach context: {outreach_context}

            Lead profile:
            - Name: {lead.full_name}
            - Email: {lead.email or "Unknown"}
            - Phone: {lead.phone or "Unknown"}
            - City: {lead.city}
            - Neighborhoods: {", ".join(lead.neighborhoods) if lead.neighborhoods else "Unknown"}
            - Property type: {lead.property_type or "Unknown"}
            - Budget min: {lead.price_min if lead.price_min is not None else "Unknown"}
            - Budget max: {lead.price_max if lead.price_max is not None else "Unknown"}
            - Notes: {lead.notes or "None"}

            Script guidance to roughly follow:
            {script_block}

            Conversation so far:
            {transcript}

            Write the next outbound SMS message only.
            """
        ).strip()

    def _create_response(self, prompt: str) -> dict:
        response = httpx.post(
            f"{self.settings.openai_base_url.rstrip('/')}/responses",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.openai_model,
                "input": prompt,
                "reasoning": {"effort": "minimal"},
                "max_output_tokens": 180,
            },
            timeout=45.0,
        )
        response.raise_for_status()
        return response.json()

    def _extract_text(self, payload: dict) -> str:
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        output = payload.get("output", [])
        if not isinstance(output, list):
            return ""

        text_parts: list[str] = []
        for item in output:
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                text_value = block.get("text")
                if isinstance(text_value, str):
                    text_parts.append(text_value)
        return "\n".join(text_parts).strip()

    def _fallback_reply(
        self,
        lead: Lead,
        conversation: list[MessageRecord],
        initial_outreach: bool,
    ) -> str:
        if initial_outreach:
            return (
                f"Hi {lead.full_name}, it's {self.settings.advisor_name} from "
                f"{self.settings.company_name}. Thanks for reaching out through Facebook. "
                "Are you mainly looking for a condo, townhouse, or detached home right now?"
            )

        latest_inbound = next(
            (message for message in reversed(conversation) if message.direction == MessageDirection.inbound),
            None,
        )
        if latest_inbound and "budget" in latest_inbound.body.lower():
            return "That helps a lot. Which areas are you most interested in, and how soon are you hoping to move?"
        if latest_inbound and any(word in latest_inbound.body.lower() for word in {"condo", "house", "townhouse"}):
            return "Nice, that gives me a better picture. What budget range would feel comfortable for you?"
        return (
            "Thanks for sharing that. To help narrow down good options, what areas are you most interested in and "
            "what kind of timeline are you working with?"
        )

    def wait_like_human(
        self,
        inbound_text: str | None,
        conversation: list[MessageRecord],
        initial_outreach: bool = False,
    ) -> float:
        delay_seconds = self._response_delay_seconds(inbound_text, conversation, initial_outreach)
        sleep(delay_seconds)
        return delay_seconds

    def _response_delay_seconds(
        self,
        inbound_text: str | None,
        conversation: list[MessageRecord],
        initial_outreach: bool,
    ) -> float:
        if initial_outreach:
            return 6.0

        message = (inbound_text or "").strip()
        message_length = len(message)
        delay = 5.0
        delay += min(message_length / 18.0, 9.0)
        delay += min(message.count("?") * 1.3, 2.6)
        delay += min(message.count(",") * 0.25, 1.0)
        delay += min(len(conversation) * 0.2, 2.0)

        hash_input = f"{message}|{len(conversation)}"
        variation = int(hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:2], 16) / 255
        delay += variation * 2.5

        return max(5.0, min(round(delay, 1), 20.0))

    def _humanize_reply(
        self,
        reply: str,
        conversation: list[MessageRecord],
        initial_outreach: bool,
    ) -> str:
        cleaned_reply = re.sub(r"\s+", " ", reply).strip()
        if initial_outreach or len(conversation) < 6 or "*" in cleaned_reply:
            return cleaned_reply

        outbound_count = sum(1 for message in conversation if message.direction == MessageDirection.outbound)
        if outbound_count < 3:
            return cleaned_reply

        if not self._should_add_typo(cleaned_reply, outbound_count):
            return cleaned_reply

        for correct, typo in (
            ("separate", "seperate"),
            ("definitely", "definitley"),
            ("available", "availible"),
            ("schedule", "scheduel"),
            ("mortgage", "mortage"),
            ("tomorrow", "tommorow"),
            ("property", "proeprty"),
            ("neighbourhood", "neigbourhood"),
        ):
            pattern = re.compile(rf"\b{re.escape(correct)}\b", re.IGNORECASE)
            match = pattern.search(cleaned_reply)
            if not match:
                continue

            found = match.group(0)
            replacement = f"{typo}*{correct}"
            if found[0].isupper():
                replacement = f"{typo.capitalize()}*{correct}"
            return f"{cleaned_reply[:match.start()]}{replacement}{cleaned_reply[match.end():]}"

        return cleaned_reply

    def _should_add_typo(self, reply: str, outbound_count: int) -> bool:
        if len(reply) < 70:
            return False

        signal = f"{reply}|{outbound_count}"
        score = int(hashlib.sha256(signal.encode("utf-8")).hexdigest()[:2], 16)
        return score % 5 == 0
