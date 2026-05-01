## Speed-to-Lead System (Brampton) — Week 1 MVP Plan

### Summary
Build a production-ready lead-orchestration backend that receives Facebook Lead Ads in real time, triggers a Retell/Twilio outbound qualification call within 5 minutes (respecting 9am–8pm call hours), stores outcomes in Postgres, and sends an SMS follow-up (with light randomized delay) containing a Calendly booking link. Initial qualification decisions are **manual-review-first**, with a “soft qualify” scoring path baked in for later automation.

### Implementation Changes (Decisions Locked)
- **Runtime/hosting**: Node.js (TypeScript) on **Railway**, single service process.
- **Database + job queue**: **Postgres** on Railway; use a Postgres-backed queue (e.g., `pg-boss`) to avoid Redis for Week 1.
- **Integrations**
  - **Meta/Facebook**: Direct **Graph API Webhooks** for Lead Ads (verify token + validate `X-Hub-Signature-256` using App Secret); fetch full lead details via Graph API on receipt.
  - **Voice**: Retell-managed agent + Twilio number for outbound call initiation; store transcript + extraction result.
  - **SMS**: Twilio Messaging; include STOP language; accept inbound replies via webhook for opt-out and “continue convo” later.
  - **Booking**: Send **Calendly link** in SMS (no Calendly API in Week 1).
  - **LLM**: OpenAI API used for (a) transcript → structured extraction, (b) concise lead summary for manual review alerts, (c) SMS personalization; model name and parameters are config-driven via env vars (no hardcoding).
- **Human-feel SMS timing (Week 1)**: single outbound SMS scheduled with **random 3–15s delay**; no multi-message typing simulation until Week 2+.
- **Hours policy**
  - Calls: schedule only **09:00–20:00 America/Toronto**; if lead arrives outside hours, schedule at next 09:00 (or earliest configured window).
  - SMS: send immediately (with light delay) because leads opted in via the form (and we persist consent evidence from the lead payload).

### System Interfaces (Decision-Complete)
- **Public webhook endpoints**
  1) `GET /webhooks/meta` — Meta webhook verification (uses `VERIFY_TOKEN`).
  2) `POST /webhooks/meta` — Meta webhook events (validates signature; enqueues lead-processing job; returns 200 quickly).
  3) `POST /webhooks/retell` — Retell call status/transcript callback (stores transcript; enqueues “post-call SMS + notify” job).
  4) `POST /webhooks/twilio/sms` — inbound SMS replies (STOP/START handling; store message; optional notify).
- **Key env vars (names fixed)**
  - `DATABASE_URL`
  - `META_VERIFY_TOKEN`, `META_APP_SECRET`, `META_ACCESS_TOKEN` (page/system user token), `META_FORM_ID`(s) if needed
  - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
  - `RETELL_API_KEY`, `RETELL_AGENT_ID_EN`
  - `OPENAI_API_KEY`, `OPENAI_MODEL` (default to a cost-efficient chat-capable model), `OPENAI_TEMPERATURE`
  - `CALENDLY_BOOKING_URL`
  - `OWNER_ALERT_PHONE` (your personal number to receive internal alerts)
- **Data model (Postgres tables)**
  - `leads`: id, created_at, source, meta_lead_id, name, phone_e164, email, consent_text, consent_timestamp, language, status
  - `events`: id, lead_id, type, payload_json, created_at (immutable audit trail)
  - `calls`: id, lead_id, retell_call_id, twilio_call_sid, started_at, ended_at, duration_sec, outcome, transcript_text, extracted_json
  - `messages`: id, lead_id, direction(in/out), channel(sms), twilio_message_sid, body, created_at, status
  - `tasks`: optional view into job state if queue library doesn’t already persist enough
- **Qualification rubric (Week 1)**
  - Always attempt to capture: budget range, timeline, preferred area(s), financing status, family size.
  - Compute a **soft score** (0–100) but do **not auto-disqualify**; instead:
    - If call completes: send Calendly link + “3 home matches within 24h” promise SMS.
    - If no answer: follow retry policy and still send a short SMS after first attempt.
  - Manual review: every lead triggers an internal “owner alert” SMS with summary + link to transcript payload in DB (or a simple admin view later).

### Execution Flow (Exact Behavior)
- **On Meta lead event**
  - Verify request signature; dedupe by `(meta_lead_id)` idempotency.
  - Fetch lead details from Graph API; normalize phone to E.164.
  - Insert `leads` + `events`.
  - Enqueue `call_lead` job:
    - If inside call hours: run immediately.
    - Else: schedule at next call window.
- **call_lead job**
  - Create outbound call via Retell (agent: English Week 1) using `TWILIO_FROM_NUMBER` → lead phone.
  - Record mapping ids in `calls`.
  - Enqueue `call_retry` jobs if no-answer/busy/failure (2 retries: +15 min, +2 hours; both still must respect call hours).
- **On Retell call end callback**
  - Store transcript; run OpenAI extraction to JSON (budget/timeline/areas/etc).
  - Enqueue `send_followup_sms` with random 3–15s delay.
  - Enqueue `notify_owner` with a concise summary (and key extracted fields).
- **send_followup_sms job**
  - Send one SMS: acknowledge, restate key info captured (if any), include Calendly link, include STOP language.
- **Inbound SMS webhook**
  - If STOP-like intent: mark lead `do_not_contact=true`, store event, confirm opt-out.
  - Else: store message; optionally send owner alert; Week 2+ can add OpenAI-driven SMS replies.

### Test Plan (Acceptance Criteria)
- **Webhook verification**
  - Meta `GET` verification succeeds with correct token; fails otherwise.
  - Meta `POST` rejects invalid signatures; accepts valid signatures.
- **Idempotency**
  - Same `meta_lead_id` posted twice produces one lead record and no double-call.
- **E2E “happy path”**
  - New lead during 09:00–20:00 triggers outbound call within 5 minutes.
  - Retell callback stored; extracted JSON present; follow-up SMS sent with 3–15s delay.
  - Owner alert SMS received with summary and lead phone.
- **Outside-hours path**
  - Lead at 23:00 schedules call for next 09:00; SMS still goes out immediately (light delay).
- **Retries**
  - No-answer triggers exactly 2 retries at +15m and +2h (within call window).
- **Compliance**
  - Every outbound SMS includes opt-out instruction; inbound STOP updates consent state and stops future jobs.

### Assumptions (Defaults Unless You Override)
- Meta Lead Ads provide valid consent for call/SMS; we store the consent string + timestamp from lead payload where possible.
- Week 1 property “3 homes in 24h” delivery is manual (agent-curated links); automation/MLS ingestion is Week 2+.
- Retell provides: outbound call creation API + call end webhooks including transcript text (or we store recording/transcript pointer if that’s what Retell returns).
- Single-market timezone is `America/Toronto`.
- Workspace cleanup later: remove the stray nested empty folder `C:\Users\manmi\GitHub\RealEstateAgentFramework\RealEstateAgentFramework` (it currently only contains an empty `.git`).
