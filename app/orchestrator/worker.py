from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.orchestrator.openai_extract import OpenAIClient
from app.orchestrator.repository import OrchestratorRepo
from app.orchestrator.retell_client import RetellClient
from app.orchestrator.schedule import CallWindow
from app.services.channels import ChannelSender


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class JobWorker:
    repo: OrchestratorRepo
    sender: ChannelSender
    settings: Settings
    call_window: CallWindow
    stop_event: threading.Event
    worker_id: str

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            job = self.repo.claim_next_job(worker_id=self.worker_id)
            if not job:
                time.sleep(0.5)
                continue

            try:
                self._handle_job(job)
                self.repo.mark_job_succeeded(int(job["id"]))
            except Exception as exc:  # noqa: BLE001
                backoff = utc_now() + timedelta(seconds=min(60, 2 ** int(job.get("attempts", 1))))
                self.repo.mark_job_failed(job_id=int(job["id"]), error=str(exc), run_at=backoff)

    def _handle_job(self, job: dict[str, Any]) -> None:
        job_type = job["type"]
        payload = job.get("payload") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)

        if job_type == "process_retell_call":
            self._process_retell_call(payload)
            return
        if job_type == "call_lead":
            self._call_lead(payload)
            return
        if job_type == "call_retry":
            self._call_lead(payload)
            return
        if job_type == "send_followup_sms":
            self._send_followup_sms(payload)
            return
        if job_type == "notify_owner":
            self._notify_owner(payload)
            return

        raise ValueError(f"Unknown job type: {job_type}")

    def _process_retell_call(self, payload: dict[str, Any]) -> None:
        lead_id = payload["lead_id"]
        retell_call_id = payload.get("retell_call_id")
        transcript = payload.get("transcript") or ""
        call_status = payload.get("call_status")
        disconnection_reason = payload.get("disconnection_reason")

        extracted_json: dict[str, Any] | None = None
        if transcript and self.settings.openai_api_key:
            client = OpenAIClient(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.openai_model,
                temperature=self.settings.openai_temperature,
            )
            extracted_json, _raw = client.extract_qualification(transcript)

        ended_at = utc_now()
        duration_sec = payload.get("duration_sec")
        if isinstance(duration_sec, float):
            duration_sec = int(duration_sec)

        if retell_call_id:
            self.repo.update_call_from_retell(
                retell_call_id=retell_call_id,
                ended_at=ended_at,
                duration_sec=duration_sec if isinstance(duration_sec, int) else None,
                outcome=call_status if isinstance(call_status, str) else None,
                disconnection_reason=disconnection_reason if isinstance(disconnection_reason, str) else None,
                transcript_text=transcript if isinstance(transcript, str) else None,
                extracted_json=extracted_json,
            )

        # Follow-up SMS (random 3–15s delay) + owner alert
        delay_seconds = random.randint(3, 15)
        self.repo.enqueue_job(
            job_type="send_followup_sms",
            dedupe_key=f"lead:{lead_id}:followup",
            payload={"lead_id": lead_id},
            run_at=utc_now() + timedelta(seconds=delay_seconds),
            max_attempts=5,
        )
        self.repo.enqueue_job(
            job_type="notify_owner",
            dedupe_key=f"lead:{lead_id}:owner_alert",
            payload={"lead_id": lead_id, "extracted_json": extracted_json},
            run_at=utc_now(),
            max_attempts=5,
        )

        # Retry policy: only for clear no-answer/busy cases.
        if disconnection_reason in {"no_answer", "busy"} or call_status in {"no_answer", "busy"}:
            retry_1 = self.call_window.clamp_delay(utc_now() + timedelta(minutes=15))
            retry_2 = self.call_window.clamp_delay(utc_now() + timedelta(hours=2))
            self.repo.enqueue_job(
                job_type="call_retry",
                dedupe_key=f"lead:{lead_id}:retry1",
                payload={"lead_id": lead_id, "retry": 1},
                run_at=retry_1,
                max_attempts=3,
            )
            self.repo.enqueue_job(
                job_type="call_retry",
                dedupe_key=f"lead:{lead_id}:retry2",
                payload={"lead_id": lead_id, "retry": 2},
                run_at=retry_2,
                max_attempts=3,
            )

    def _call_lead(self, payload: dict[str, Any]) -> None:
        lead_id = payload["lead_id"]
        lead = self.repo.get_lead_contact(lead_id)
        if not lead:
            raise ValueError("Lead not found for call.")
        if lead.get("do_not_contact"):
            self.repo.cancel_jobs_for_lead(lead_id)
            return

        to_number = lead.get("phone_e164")
        if not to_number:
            self.repo.set_status(lead_id, "missing_phone")
            return

        if not self.settings.retell_api_key or not self.settings.retell_agent_id_en:
            self.repo.set_status(lead_id, "retell_not_configured")
            return

        client = RetellClient(api_key=self.settings.retell_api_key, base_url=self.settings.retell_base_url)
        result = client.create_phone_call(
            from_number=self.settings.twilio_from_number,
            to_number=to_number,
            agent_id=self.settings.retell_agent_id_en,
            metadata={"lead_id": lead_id},
            dynamic_variables={"lead_name": lead.get("name") or "there"},
        )
        retell_call_id = result.get("call_id") or result.get("call", {}).get("call_id")
        self.repo.create_call(lead_id=lead_id, retell_call_id=retell_call_id, started_at=utc_now())
        self.repo.add_event(lead_id=lead_id, event_type="retell_call_created", payload=result)
        self.repo.set_status(lead_id, "call_started")

    def _send_followup_sms(self, payload: dict[str, Any]) -> None:
        lead_id = payload["lead_id"]
        lead = self.repo.get_lead_contact(lead_id)
        if not lead:
            return
        if lead.get("do_not_contact"):
            self.repo.cancel_jobs_for_lead(lead_id)
            return

        phone = lead.get("phone_e164")
        if not phone:
            return

        booking = self.settings.calendly_booking_url or self.settings.booking_link
        extracted = self.repo.get_latest_extracted_json(lead_id)
        details_parts: list[str] = []
        if extracted:
            areas = extracted.get("preferred_areas")
            if isinstance(areas, list) and areas:
                details_parts.append(", ".join(str(a) for a in areas[:3] if isinstance(a, str) and a.strip()))
            budget_min = extracted.get("budget_min")
            budget_max = extracted.get("budget_max")
            if isinstance(budget_min, (int, float)) or isinstance(budget_max, (int, float)):
                if budget_min and budget_max:
                    details_parts.append(f"${int(budget_min):,}–${int(budget_max):,}")
                elif budget_max:
                    details_parts.append(f"up to ${int(budget_max):,}")
                elif budget_min:
                    details_parts.append(f"from ${int(budget_min):,}")
            timeline = extracted.get("timeline")
            if isinstance(timeline, str) and timeline.strip():
                details_parts.append(timeline.strip())

        name = (lead.get("name") or "").strip()
        details = " (" + " / ".join([p for p in details_parts if p]) + ")" if details_parts else ""
        greeting = f"Thanks {name}" if name else "Thanks"
        body = f"{greeting}{details} — if you want, you can book a quick call here: {booking} Reply STOP to opt out."

        send_result = self.sender.send_sms_to_number(to_number=phone, body=body)
        self.repo.create_message(
            lead_id=lead_id,
            direction="out",
            channel="sms",
            body=body,
            twilio_message_sid=send_result.provider_message_id,
            status=send_result.status,
        )
        self.repo.add_event(lead_id=lead_id, event_type="followup_sms_sent", payload={"status": send_result.status})
        self.repo.set_status(lead_id, "sms_sent")

    def _notify_owner(self, payload: dict[str, Any]) -> None:
        lead_id = payload["lead_id"]
        lead = self.repo.get_lead_contact(lead_id)
        if not lead or not self.settings.owner_alert_phone:
            return

        extracted = payload.get("extracted_json")
        if self.settings.openai_api_key:
            client = OpenAIClient(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.openai_model,
                temperature=self.settings.openai_temperature,
            )
            summary = client.owner_summary(lead.get("name"), lead.get("phone_e164"), extracted)
        else:
            summary = f"New lead: {lead.get('name') or 'Unknown'} ({lead.get('phone_e164') or 'Unknown'})."

        send_result = self.sender.send_sms_to_number(to_number=self.settings.owner_alert_phone, body=summary)
        self.repo.add_event(
            lead_id=lead_id,
            event_type="owner_alert_sent",
            payload={"status": send_result.status, "sid": send_result.provider_message_id},
        )


def start_worker_in_thread(repo: OrchestratorRepo, sender: ChannelSender, settings: Settings) -> tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    worker = JobWorker(
        repo=repo,
        sender=sender,
        settings=settings,
        call_window=CallWindow(tz=settings.app_timezone, start_hour=settings.call_window_start_hour, end_hour=settings.call_window_end_hour),
        stop_event=stop_event,
        worker_id=f"worker-{uuid4()}",
    )
    thread = threading.Thread(target=worker.run_forever, name="job-worker", daemon=True)
    thread.start()
    return thread, stop_event
