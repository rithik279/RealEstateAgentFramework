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
            "\n"
            "CORE FIELDS:\n"
            "  budget_min              - number or null (CAD, no commas)\n"
            "  budget_max              - number or null (CAD, no commas)\n"
            "  timeline                - string or null (e.g. '3 months', 'ASAP', 'this year')\n"
            "  timeline_days           - integer or null (estimated days to purchase, e.g. 30, 90, 180)\n"
            "  preferred_areas         - array of strings or null (e.g. ['Brampton', 'Mississauga'])\n"
            "  financing_status        - string or null (e.g. 'pre-approved', 'working with broker', 'not started')\n"
            "  pre_approval_status     - string or null ('approved', 'in progress', 'not started', 'declined')\n"
            "  down_payment_amount     - number or null (CAD)\n"
            "  down_payment_confirmed  - boolean or null (true if they confirmed a specific down payment amount/range)\n"
            "  property_type           - string or null (e.g. 'detached', 'semi-detached', 'townhouse', 'condo')\n"
            "  bedrooms                - integer or null\n"
            "  bathrooms               - integer or null\n"
            "  family_size             - integer or null\n"
            "  specific_property       - boolean or null (true if they mention a specific listing or address)\n"
            "  specific_property_address - string or null (the address/MLS# if mentioned)\n"
            "\n"
            "BRAMPTON-SPECIFIC SIGNALS (critical for Brampton GTA market):\n"
            "  basement_income_interest - boolean or null (interested in basement rental income / income suite)\n"
            "  kitchen_priority         - boolean or null (kitchen quality/size is a key factor for them)\n"
            "  parking_needed           - integer or null (number of parking spots needed, e.g. 2, 3)\n"
            "  parking_priority         - boolean or null (parking/garage is explicitly important to them)\n"
            "  two_family_interest      - boolean or null (buying with parents or two families together)\n"
            "  housepooling_interest    - boolean or null (two+ families pooling budget to buy together)\n"
            "\n"
            "BUYER PROFILE:\n"
            "  currently_represented   - string or null ('yes', 'no') — working with another agent?\n"
            "  family_agent_risk       - boolean or null (mentioned a family member who is an agent)\n"
            "  first_time_buyer        - boolean or null\n"
            "  move_up_seller          - boolean or null (already owns, looking to upgrade)\n"
            "  investor_minded         - boolean or null (mentioned investment goals, cashflow, ROI)\n"
            "  currently_renting       - boolean or null (true if they are currently renting, not owning)\n"
            "  priority_signal         - string or null (their single top priority: 'income_potential', 'kitchen', 'parking', 'space', 'location', 'price')\n"
            "  area_confirmed          - string or null (the specific city/area they confirmed on the call, e.g. 'Brampton', 'Kitchener', 'London')\n"
            "  lot_size_interest       - boolean or null (mentioned interest in large lot, backyard, outdoor space)\n"
            "\n"
            "LEGACY:\n"
            "  notes                   - string or null (anything important not captured above)\n"
            "  score_0_100             - integer 0-100 (your subjective call quality estimate)\n"
            "\n"
            "Rules:\n"
            "- Use null when unknown or not mentioned.\n"
            "- preferred_areas must be an array of strings or null.\n"
            "- Do not include markdown, backticks, or extra text.\n"
            "- Return ONLY the JSON object, nothing else.\n\n"
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

    def owner_summary(
        self,
        lead_name: str | None,
        lead_phone: str | None,
        extracted: dict[str, Any] | None,
        tier: str | None = None,
        score: int | None = None,
        recommended_action: str | None = None,
    ) -> str:
        tier_line = ""
        if tier and score is not None:
            tier_line = f"Readiness: {tier.upper()} ({score}/100). "
        action_line = f"Action: {recommended_action} " if recommended_action else ""
        prompt = (
            "Write a concise SMS alert for a real estate agent about a new lead call.\n"
            "Include name, phone, readiness tier, budget, timeline, and top signals.\n"
            "No emojis. Keep under 320 characters. Start with tier if hot/warm.\n\n"
            f"Lead name: {lead_name or 'Unknown'}\n"
            f"Lead phone: {lead_phone or 'Unknown'}\n"
            f"{tier_line}{action_line}\n"
            f"Extracted: {json.dumps(extracted or {}, ensure_ascii=False)}"
        )
        payload = self._responses(prompt)
        text = self._extract_text(payload).strip()
        fallback = f"New lead: {lead_name or 'Unknown'} ({lead_phone or 'Unknown'}). {tier_line}"
        return text[:320] if text else fallback[:320]

