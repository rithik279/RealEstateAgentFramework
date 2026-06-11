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
from app.orchestrator.reactivation import seed_reactivation_sms_jobs
from app.orchestrator.repository import OrchestratorRepo
from app.orchestrator.retell_client import RetellClient
from app.orchestrator.schedule import CallWindow
from app.orchestrator.scoring import score_lead
from app.services.channels import ChannelSender
from app.services.nurture_sequences import enqueue_sequence


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
        if job_type == "reactivation_sms":
            self._send_reactivation_sms(payload)
            return
        if job_type == "seed_reactivation_sms":
            self._seed_reactivation_sms()
            return
        if job_type == "classify_sms_reply":
            self._classify_sms_reply(payload)
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

        # --- Score the lead ---
        call_answered = call_status not in {"no_answer", "busy", "failed", "voicemail"}
        score_result = score_lead(extracted_json or {}, call_answered=call_answered)
        self.repo.set_readiness(
            lead_id,
            score=score_result.score,
            tier=score_result.tier,
            tags=score_result.tags,
            components=score_result.components,
            buyer_profile=extracted_json,
        )
        self.repo.add_event(
            lead_id=lead_id,
            event_type="readiness_scored",
            payload={
                "score": score_result.score,
                "tier": score_result.tier,
                "tags": score_result.tags,
                "components": score_result.components,
                "recommended_action": score_result.recommended_action,
            },
        )

        # Follow-up SMS (random 3–15s delay) + owner alert
        delay_seconds = random.randint(3, 15)
        self.repo.enqueue_job(
            job_type="send_followup_sms",
            dedupe_key=f"lead:{lead_id}:followup",
            payload={"lead_id": lead_id, "tier": score_result.tier},
            run_at=utc_now() + timedelta(seconds=delay_seconds),
            max_attempts=5,
        )

        # Enqueue nurture sequence for warm/early/cold
        if score_result.tier in ("warm", "early", "cold"):
            lead = self.repo.get_lead_contact(lead_id)
            booking = self.settings.calendly_booking_url or self.settings.booking_link
            enqueue_sequence(
                repo=self.repo,
                tier=score_result.tier,
                lead_id=lead_id,
                name=lead.get("name") if lead else None,
                extracted=extracted_json or {},
                booking_url=booking,
            )
        self.repo.enqueue_job(
            job_type="notify_owner",
            dedupe_key=f"lead:{lead_id}:owner_alert",
            payload={
                "lead_id": lead_id,
                "extracted_json": extracted_json,
                "tier": score_result.tier,
                "score": score_result.score,
                "recommended_action": score_result.recommended_action,
            },
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

        # Route reactivation leads to dedicated agent if configured, else fall back to default
        source = lead.get("source", "")
        area = lead.get("area") or "unknown"
        is_reactivation = source == "legacy_reactivation"
        agent_id = (
            self.settings.retell_agent_id_reactivation
            if is_reactivation and self.settings.retell_agent_id_reactivation
            else self.settings.retell_agent_id_en
        )

        from app.orchestrator.area import messaging_area
        area_label = messaging_area(area)

        client = RetellClient(api_key=self.settings.retell_api_key, base_url=self.settings.retell_base_url)
        result = client.create_phone_call(
            from_number=self.settings.twilio_from_number,
            to_number=to_number,
            agent_id=agent_id,
            metadata={"lead_id": lead_id, "source": source, "area": area},
            dynamic_variables={
                "lead_name": lead.get("name") or "there",
                "area": area_label,
                "is_reactivation": "true" if is_reactivation else "false",
            },
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

        # Nurture sequence messages have a pre-built body — send directly
        body_override = payload.get("body_override")
        if body_override:
            send_result = self.sender.send_sms_to_number(to_number=phone, body=body_override)
            self.repo.create_message(
                lead_id=lead_id, direction="out", channel="sms", body=body_override,
                twilio_message_sid=send_result.provider_message_id, status=send_result.status,
            )
            self.repo.add_event(lead_id=lead_id, event_type="nurture_sms_sent",
                                payload={"status": send_result.status})
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

        tier = payload.get("tier", "")
        name = (lead.get("name") or "").strip()
        details = " (" + " / ".join([p for p in details_parts if p]) + ")" if details_parts else ""
        greeting = f"Thanks {name}" if name else "Thanks"

        if tier == "hot":
            body = (
                f"Hi {name or 'there'}! I just reviewed your inquiry{details}. "
                f"I have exactly what you're looking for. Let's connect today: {booking} "
                f"Reply STOP to opt out."
            )
        elif tier == "warm":
            body = (
                f"{greeting}{details}. I'd love to set up a quick buyer consultation. "
                f"Pick a time that works: {booking} Reply STOP to opt out."
            )
        else:
            body = f"{greeting}{details}. If you want, you can book a quick call here: {booking} Reply STOP to opt out."

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

    def _send_reactivation_sms(self, payload: dict[str, Any]) -> None:
        from app.orchestrator.reactivation import (
            _random_send_time,
            build_touch2_body,
            build_touch3_body,
        )

        lead_id = payload["lead_id"]
        touch = int(payload.get("touch", 1))
        lead = self.repo.get_lead_contact(lead_id)
        if not lead or lead.get("do_not_contact"):
            return
        phone = lead.get("phone_e164")
        if not phone:
            return

        area = lead.get("area")
        name = lead.get("name")

        # Compute body — Touch 1 has pre-built body; Touch 2/3 built dynamically
        if touch == 1:
            body = payload.get("body", "")
        elif touch == 2:
            extracted = self.repo.get_latest_extracted_json(lead_id)
            body = build_touch2_body(name=name, area=area, extracted=extracted)
        elif touch == 3:
            extracted = self.repo.get_latest_extracted_json(lead_id)
            body = build_touch3_body(name=name, area=area, extracted=extracted)
        else:
            body = payload.get("body", "")

        if not body:
            return

        self.sender.send_sms_to_number(to_number=phone, body=body)
        self.repo.create_message(
            lead_id=lead_id, direction="out", channel="sms", body=body,
        )
        self.repo.add_event(
            lead_id=lead_id,
            event_type="reactivation_sms_sent",
            payload={"body": body, "touch": touch},
        )

        # After Touch 1: schedule Touch 2 (Day 4), Touch 3 (Day 10), and ALEX call (30-90 min later)
        if touch == 1:
            tz = self.settings.app_timezone
            ws = self.settings.reactivation_sms_window_start
            we = self.settings.reactivation_sms_window_end

            from datetime import timedelta
            from zoneinfo import ZoneInfo
            local_tz = ZoneInfo(tz)
            today = datetime.now(local_tz).date()

            # Touch 2: Day 4 from today
            day4 = today + timedelta(days=4)
            send2 = _random_send_time(tz=tz, window_start_hour=ws, window_end_hour=we,
                                      base_date=datetime(day4.year, day4.month, day4.day, ws, 0, tzinfo=local_tz))
            self.repo.enqueue_job(
                job_type="reactivation_sms",
                dedupe_key=f"reactivation_sms:{lead_id}:t2",
                payload={"lead_id": lead_id, "touch": 2},
                run_at=send2,
                max_attempts=2,
            )

            # Touch 3: Day 10 from today
            day10 = today + timedelta(days=10)
            send3 = _random_send_time(tz=tz, window_start_hour=ws, window_end_hour=we,
                                      base_date=datetime(day10.year, day10.month, day10.day, ws, 0, tzinfo=local_tz))
            self.repo.enqueue_job(
                job_type="reactivation_sms",
                dedupe_key=f"reactivation_sms:{lead_id}:t3",
                payload={"lead_id": lead_id, "touch": 3},
                run_at=send3,
                max_attempts=2,
            )

            # ALEX call: 14 min after SMS, clamped to reactivation window (4-8pm)
            # Increases response rate — warm call right after the text
            if self.settings.retell_api_key and (
                self.settings.retell_agent_id_reactivation or self.settings.retell_agent_id_en
            ):
                call_delay = 14
                raw_call_time = utc_now() + timedelta(minutes=call_delay)
                reactivation_window = CallWindow(
                    tz=tz,
                    start_hour=ws,  # 16 (4pm)
                    end_hour=we,    # 20 (8pm)
                )
                clamped_call_time = reactivation_window.clamp_delay(raw_call_time)
                self.repo.enqueue_job(
                    job_type="call_lead",
                    dedupe_key=f"reactivation_sms:{lead_id}:call_t1",
                    payload={"lead_id": lead_id},
                    run_at=clamped_call_time,
                    max_attempts=2,
                )

    def _classify_sms_reply(self, payload: dict[str, Any]) -> None:
        lead_id = payload["lead_id"]
        body = payload.get("body", "")
        phone = payload.get("phone", "")

        if not self.settings.openai_api_key:
            return

        client = OpenAIClient(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
            model=self.settings.openai_model,
            temperature=0.0,
        )
        intent = client.classify_sms_reply(body)

        self.repo.add_event(
            lead_id=lead_id,
            event_type="sms_reply_classified",
            payload={"body": body, "intent": intent},
        )

        if intent == "opted_out":
            self.repo.set_do_not_contact(lead_id, True)
            self.repo.set_status(lead_id, "opted_out")
        elif intent == "closed":
            self.repo.set_status(lead_id, "closed")
        elif intent == "interested" and self.settings.owner_alert_phone:
            lead = self.repo.get_lead_contact(lead_id)
            name = (lead.get("name") or phone) if lead else phone
            alert = f"Reply from {name} ({phone}): \"{body[:160]}\" — they seem interested. Check dashboard."
            self.sender.send_sms_to_number(to_number=self.settings.owner_alert_phone, body=alert[:320])

    def _seed_reactivation_sms(self) -> None:
        count = seed_reactivation_sms_jobs(
            db=self.repo.db,
            tz=self.settings.app_timezone,
            window_start_hour=self.settings.reactivation_sms_window_start,
            window_end_hour=self.settings.reactivation_sms_window_end,
            daily_limit=self.settings.reactivation_sms_daily_limit,
        )
        import logging
        logging.getLogger(__name__).info("Reactivation SMS: seeded %d jobs", count)

    def _notify_owner(self, payload: dict[str, Any]) -> None:
        lead_id = payload["lead_id"]
        lead = self.repo.get_lead_contact(lead_id)
        if not lead or not self.settings.owner_alert_phone:
            return

        extracted = payload.get("extracted_json")
        tier = payload.get("tier")
        score = payload.get("score")
        recommended_action = payload.get("recommended_action")
        if self.settings.openai_api_key:
            client = OpenAIClient(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.openai_model,
                temperature=self.settings.openai_temperature,
            )
            summary = client.owner_summary(
                lead.get("name"),
                lead.get("phone_e164"),
                extracted,
                tier=tier,
                score=score,
                recommended_action=recommended_action,
            )
        else:
            tier_str = f" [{tier.upper()} {score}/100]" if tier and score is not None else ""
            summary = f"New lead{tier_str}: {lead.get('name') or 'Unknown'} ({lead.get('phone_e164') or 'Unknown'})."

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
