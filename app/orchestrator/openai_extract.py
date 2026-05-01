from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class OpenAIClient:
    api_key: str
    base_url: str
    model: str
    temperature: float = 0.2

    def _responses(self, input_text: str) -> dict[str, Any]:
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
        return response.json()

    def _extract_text(self, payload: dict[str, Any]) -> str:
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        output = payload.get("output", [])
        if not isinstance(output, list):
            return ""

        parts: list[str] = []
        for item in output:
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                text_value = block.get("text")
                if isinstance(text_value, str):
                    parts.append(text_value)
        return "\n".join(parts).strip()

    def extract_qualification(self, transcript: str) -> tuple[dict[str, Any] | None, str]:
        prompt = (
            "Extract these fields from the call transcript and return ONLY valid JSON.\n"
            "Keys: budget_min, budget_max, timeline, preferred_areas, financing_status, property_type, bedrooms, bathrooms, family_size, notes, score_0_100.\n"
            "Rules:\n"
            "- Use null when unknown.\n"
            "- preferred_areas must be an array of strings or null.\n"
            "- score_0_100 must be an integer 0-100.\n"
            "- Do not include markdown, backticks, or extra text.\n\n"
            f"Transcript:\n{transcript}"
        )

        payload = self._responses(prompt)
        text = self._extract_text(payload).strip()
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj, text
            return None, text
        except json.JSONDecodeError:
            return None, text

    def owner_summary(self, lead_name: str | None, lead_phone: str | None, extracted: dict[str, Any] | None) -> str:
        prompt = (
            "Write a concise 1-2 sentence SMS summary for the owner about a new real estate lead call.\n"
            "Include name, phone, and any extracted qualification details (budget/timeline/areas/financing).\n"
            "No emojis. Keep under 240 characters.\n\n"
            f"Lead name: {lead_name or 'Unknown'}\n"
            f"Lead phone: {lead_phone or 'Unknown'}\n"
            f"Extracted: {json.dumps(extracted or {}, ensure_ascii=False)}"
        )
        payload = self._responses(prompt)
        text = self._extract_text(payload).strip()
        return text[:240] if text else f"New lead call: {lead_name or 'Unknown'} ({lead_phone or 'Unknown'})."

