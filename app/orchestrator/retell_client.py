from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class RetellClient:
    api_key: str
    base_url: str = "https://api.retellai.com"

    def create_phone_call(
        self,
        *,
        from_number: str,
        to_number: str,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
        dynamic_variables: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/v2/create-phone-call",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "from_number": from_number,
                "to_number": to_number,
                "override_agent_id": agent_id,
                "metadata": metadata or {},
                "retell_llm_dynamic_variables": dynamic_variables or {},
            },
            timeout=45.0,
        )
        response.raise_for_status()
        return response.json()

