from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class QualificationResult:
    budget_min: int | None = None
    budget_max: int | None = None
    timeline: str | None = None
    preferred_areas: list[str] | None = None
    financing_status: str | None = None
    property_type: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    family_size: int | None = None
    notes: str | None = None
    score_0_100: int | None = None
    raw_json: dict[str, Any] | None = None
    raw_text: str = ""


@dataclass
class SummaryResult:
    sms_body: str = ""
    owner_alert: str = ""


class TranscriptExtractionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_key = settings.openai_api_key
        self.base_url = settings.openai_base_url
        self.model = settings.openai_model
        self.temperature = settings.openai_temperature

    def _call_openai(self, input_text: str) -> str:
        if not self.api_key:
            return ""

        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "temperature": self.temperature,
                    "input": input_text,
                },
                timeout=45.0,
            )
            response.raise_for_status()
            payload = response.json()

            output_text = payload.get("output_text")
            if isinstance(output_text, str) and output_text.strip():
                return output_text.strip()

            output = payload.get("output", [])
            if isinstance(output, list):
                parts = []
                for item in output:
                    for block in item.get("content", []):
                        text = block.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                return "\n".join(parts).strip()

            return ""
        except Exception as exc:  # noqa: BLE001
            logger.error("OpenAI call failed: %s", exc)
            return ""

    def extract_qualification(self, transcript: str) -> QualificationResult:
        prompt = (
            "Extract these fields from the call transcript and return ONLY valid JSON.\n"
            "Keys: budget_min, budget_max, timeline, preferred_areas, financing_status, "
            "property_type, bedrooms, bathrooms, family_size, notes, score_0_100.\n"
            "Rules:\n"
            "- Use null when unknown.\n"
            "- preferred_areas must be an array of strings or null.\n"
            "- score_0_100 must be an integer 0-100.\n"
            "- Do not include markdown, backticks, or extra text.\n\n"
            f"Transcript:\n{transcript}"
        )

        text = self._call_openai(prompt)
        try:
            obj = json.loads(text) if text else {}
        except json.JSONDecodeError:
            logger.warning("Failed to parse qualification JSON: %s", text[:200])
            obj = {}

        return QualificationResult(
            budget_min=obj.get("budget_min"),
            budget_max=obj.get("budget_max"),
            timeline=obj.get("timeline"),
            preferred_areas=obj.get("preferred_areas"),
            financing_status=obj.get("financing_status"),
            property_type=obj.get("property_type"),
            bedrooms=obj.get("bedrooms"),
            bathrooms=obj.get("bathrooms"),
            family_size=obj.get("family_size"),
            notes=obj.get("notes"),
            score_0_100=obj.get("score_0_100"),
            raw_json=obj if isinstance(obj, dict) else None,
            raw_text=text,
        )

    def generate_sms_body(
        self,
        lead_name: str,
        extracted: QualificationResult,
        booking_url: str,
    ) -> str:
        name = (lead_name or "").strip()
        greeting = f"Thanks {name}" if name else "Thanks"

        details: list[str] = []
        if extracted.preferred_areas:
            areas = ", ".join(extracted.preferred_areas[:2])
            details.append(f"looking in {areas}")
        if extracted.budget_max:
            details.append(f"up to ${extracted.budget_max // 1000}k")
        if extracted.timeline:
            details.append(extracted.timeline)

        detail_str = " (" + " / ".join(details) + ")" if details else ""
        return (
            f"{greeting}{detail_str} — "
            f"you can book a quick call here: {booking_url} "
            f"Reply STOP to opt out."
        )

    def generate_owner_alert(
        self,
        lead_name: str,
        lead_phone: str,
        extracted: QualificationResult,
    ) -> str:
        prompt = (
            "Write a concise 1-2 sentence SMS summary for the real estate agent owner "
            "about a new qualified lead call. Include name, phone, and any key "
            "qualification details (budget/timeline/areas/financing). "
            "No emojis. Keep under 240 characters.\n\n"
            f"Lead name: {lead_name or 'Unknown'}\n"
            f"Lead phone: {lead_phone or 'Unknown'}\n"
            f"Budget: {extracted.budget_min or '?'}–{extracted.budget_max or '?'}\n"
            f"Timeline: {extracted.timeline or 'unknown'}\n"
            f"Areas: {', '.join(extracted.preferred_areas or []) or 'unknown'}\n"
            f"Financing: {extracted.financing_status or 'unknown'}\n"
            f"Qualification score: {extracted.score_0_100 or 'N/A'}/100"
        )

        text = self._call_openai(prompt)
        result = text[:240] if text else ""
        if not result:
            result = f"New lead: {lead_name or 'Unknown'} ({lead_phone or 'Unknown'})."
        return result
