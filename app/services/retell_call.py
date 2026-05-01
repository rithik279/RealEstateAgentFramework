from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class CallResult:
    call_id: str | None
    status: str
    detail: str


class RetellCallService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_key = settings.retell_api_key
        self.agent_id = settings.retell_agent_id_en
        self.base_url = settings.retell_base_url
        self.dry_run = settings.dry_run

    def initiate_outbound_call(
        self,
        *,
        from_number: str,
        to_number: str,
        lead_id: str,
        lead_name: str,
        dynamic_variables: dict[str, str] | None = None,
    ) -> CallResult:
        if not self.api_key or not self.agent_id:
            return CallResult(
                call_id=None,
                status="failed",
                detail="Retell API key or agent ID not configured.",
            )

        if self.dry_run:
            logger.info(
                "[DRY RUN] Retell call: from=%s to=%s lead_id=%s",
                from_number,
                to_number,
                lead_id,
            )
            return CallResult(
                call_id=f"dry-run-{lead_id}",
                status="simulated",
                detail="Call simulated (APP_DRY_RUN=true).",
            )

        variables = dynamic_variables or {}
        variables.setdefault("lead_name", lead_name or "there")

        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/v2/create-phone-call",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from_number": from_number,
                    "to_number": to_number,
                    "override_agent_id": self.agent_id,
                    "metadata": {"lead_id": lead_id},
                    "retell_llm_dynamic_variables": variables,
                },
                timeout=45.0,
            )
            response.raise_for_status()
            payload = response.json()
            call_id = payload.get("call_id") or payload.get("call", {}).get("call_id")
            return CallResult(
                call_id=call_id,
                status="initiated",
                detail="Retell call created successfully.",
            )
        except httpx.HTTPStatusError as exc:
            logger.error("Retell API error: %s %s", exc.response.status_code, exc.response.text)
            return CallResult(
                call_id=None,
                status="error",
                detail=f"Retell API error: {exc.response.status_code}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Retell call failed: %s", exc)
            return CallResult(
                call_id=None,
                status="error",
                detail=str(exc),
            )

    def parse_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = payload.get("event")
        call = payload.get("call") or {}
        metadata = call.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        start_ts = call.get("start_timestamp")
        end_ts = call.get("end_timestamp")
        duration_sec: int | None = None
        if isinstance(start_ts, int) and isinstance(end_ts, int) and end_ts >= start_ts:
            duration_sec = int((end_ts - start_ts) / 1000)

        return {
            "event": event,
            "lead_id": metadata.get("lead_id"),
            "retell_call_id": call.get("call_id"),
            "transcript": call.get("transcript") or "",
            "call_status": call.get("call_status"),
            "disconnection_reason": call.get("disconnection_reason"),
            "duration_sec": duration_sec,
            "recording_url": call.get("recording_url") or call.get("audio_url"),
            "sentiment": call.get("sentiment"),
            "ended_at": datetime.now(timezone.utc),
        }
