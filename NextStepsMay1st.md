# Next Steps — May 1st, 2026

## Where We Are

Production-ready lead-orchestration backend. Code is complete. Retell voice agent not yet created. Legacy leads not yet loaded. You are one step from live outbound calls.

---

## Architecture Overview

### Stack
- **Runtime**: Python 3 / FastAPI (single service process)
- **Database + Job Queue**: Postgres on Railway (`pg-boss` equivalent is custom Postgres-backed queue via `jobs` table)
- **Voice**: Retell AI agent + Twilio number for outbound calls
- **SMS**: Twilio Messaging
- **LLM**: OpenAI API (transcript extraction, SMS personalization, owner alerts)
- **Scheduling**: APScheduler for intra-process time-bound calls; Postgres `jobs` table for distributed queue

### Data Flow

```
Meta Lead Ad form
  ↓ POST /webhooks/meta
leads table (insert if new)
  ↓ enqueue job: call_lead
jobs table (queued)
  ↓ worker thread claims job
Retell API → create outbound call
  ↓ Retell calls lead's phone
  ↓ On call end → POST /webhooks/retell
enqueue: process_retell_call
  ↓ worker processes:
  - OpenAI extract transcript → extracted_json
  - enqueue: send_followup_sms (+3-15s delay)
  - enqueue: notify_owner (immediate)
  ↓ worker sends SMS via Twilio
  ↓ lead receives SMS with Calendly link
```

### Key Files

| File | Role |
|---|---|
| `app/main.py` | FastAPI app, all webhook endpoints |
| `app/config.py` | All env vars, one `Settings` dataclass |
| `app/db.py` | Postgres connection pool + migration SQL |
| `app/orchestrator/repository.py` | All DB operations (OrchestratorRepo) |
| `app/orchestrator/worker.py` | Background thread, claims + processes jobs |
| `app/orchestrator/retell_client.py` | Lightweight Retell HTTP client |
| `app/services/retell_call.py` | RetellCallService with dry-run support |
| `app/services/transcript_extraction.py` | OpenAI transcript → structured JSON |
| `app/services/call_scheduler.py` | APScheduler wrapper for time-window calls |
| `app/services/channels.py` | Twilio SMS sender |
| `app/orchestrator/openai_extract.py` | OpenAI client for extraction + owner summary |

### Postgres Tables

- **`leads`**: core lead record. Fields: id, name, phone_e164, email, consent_text, consent_timestamp, status, do_not_contact, source, meta_lead_id
- **`events`**: immutable audit log. Every state transition + webhook received
- **`calls`**: Retell call record. Fields: retell_call_id, started_at, ended_at, duration_sec, outcome, transcript_text, extracted_json
- **`messages`**: SMS log. Fields: direction (in/out), channel, twilio_message_sid, body, status
- **`jobs`**: job queue. Fields: type, payload (JSON), run_at, status, attempts, dedupe_key. Dedupe via `(type, dedupe_key)` unique index

### Job Types

| Job Type | Trigger | Action |
|---|---|---|
| `call_lead` | Meta webhook (or legacy load) | Call lead via Retell |
| `call_retry` | `process_retell_call` on no-answer/busy | Retell call at +15m / +2h |
| `process_retell_call` | Retell webhook | Extract transcript, enqueue SMS + alert |
| `send_followup_sms` | `process_retell_call` | Send Twilio SMS with Calendly link |
| `notify_owner` | `process_retell_call` | SMS owner with lead summary |

### Call Window
- **Hours**: 09:00–20:00 America/Toronto
- Leads arriving outside hours: call scheduled at next window open. SMS still sent immediately (with 3–15s randomized delay).

---

## What's Complete

- [x] Meta Lead Ads webhook → verify + parse + dedupe
- [x] Lead insert with `meta_lead_id` dedup
- [x] Job queue (postgres-backed, `claim_next_job` with `FOR UPDATE SKIP LOCKED`)
- [x] Worker thread: claim → handle job → mark succeeded / exponential backoff
- [x] Retell client + `create_phone_call()` API call
- [x] Retell webhook handler (`/webhooks/retell`)
- [x] Transcript extraction via OpenAI → `extracted_json`
- [x] Follow-up SMS + Calendly link
- [x] Owner alert SMS
- [x] Retry policy: no-answer / busy → +15m, +2h
- [x] Call window clamping
- [x] Do Not Contact / STOP handling
- [x] Postgres schema migration
- [x] Dry-run mode (`APP_DRY_RUN=true`)
- [x] Config status endpoint (`/config-status`)

---

## What's Left

### 1. Create Retell Voice Agent (Priority #1 — blocking)

**Retell dashboard → create agent. This is the only thing stopping live calls.**

#### Steps:

1. Log in to Retell dashboard (retellai.com)
2. Create new agent:
   - Name: "Brampton Lead Qualification"
   - Type: "Phone" (outbound-capable)
   - Link your Twilio number (`TWILIO_FROM_NUMBER`)
3. Write the agent prompt. Core flow:
   ```
   Introduction:
   "Hi, this is [ Advisor Name ] calling from [ Company Name ].
    We recently connected through our real estate advisory.
    I'm calling to briefly qualify your interest — this should only take 2-3 minutes.
    Are you still in the market for a property in Brampton?"

   If yes → ask:
   - Budget range (e.g., "$500k–$700k"?)
   - Preferred area(s) in Brampton?
   - Property type (detached/semi/condo)?
   - Timeline (buying in 3 months? 6 months?)
   - Financing status (pre-approved? mortgage pending?)
   - Family size / bedrooms needed?

   Closing:
   - "Based on what you've shared, I'd love to send you 3-5
      home matches within 24 hours."
   - "Can I book a quick 15-min call to go over these?
      Here's the link: [ CALENDLY_BOOKING_URL ]"
   - "If not a good time, no problem — we'll send a text.
      Have a great day!"

   Objections / Hanging up:
   - "No problem at all. I'll send you a text with the booking
      link so you can reach out when ready."
   - "Thanks for your time. Take care."
   ```
4. Enable **outbound calling** (Retell → agent settings → Outbound tab → enter your Twilio number)
5. Set your Twilio number as the caller ID in Retell
6. Copy the **Agent ID** from the dashboard (format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
7. Set env var:
   ```
   RETELL_AGENT_ID_EN=<your-agent-id>
   ```

#### Test in dry-run first:
```bash
APP_DRY_RUN=true python -m app.main
# Check /health → retell_configured: true
# Submit a test lead → check logs for "DRY RUN" Retell call
```

#### Then go live:
```bash
APP_DRY_RUN=false python -m app.main
```

---

### 2. Load Legacy Leads (Priority #2 — enable calling old leads)

You have two files in the project root:
- `Old RE Leads for Reactivation.csv`
- `Leads Until March.xlsx`

These need to be bulk-inserted into Postgres so the worker can call them.

#### What to do:

**Option A: One-shot script (recommended for one-time import)**

Write a script `scripts/import_legacy_leads.py`:

```
1. Read CSV + Excel files
2. For each row:
   - Parse: name, phone (normalize to E.164), email, source='legacy_reactivation'
   - Insert into leads table (ignore duplicates by phone_e164)
   - Enqueue call_lead job for each, clamped to call window
3. Run it once
```

**Option B: Admin API endpoint**

POST `/leads/import` that accepts a CSV file and does the same.

#### Key considerations:
- Normalize phone numbers (North America → E.164 via `normalize_na_phone_to_e164`)
- Skip leads where `do_not_contact=true` in original data
- Set `language='en'` for all (Week 1 English only)
- `meta_lead_id` left null (these aren't from Meta)
- Enqueue `call_lead` jobs with `max_attempts=3`

#### Suggested priority: batch by lead creation date
- 2023 leads → low priority, maybe skip or manual review
- 2024 leads → moderate priority
- 2025 leads → high priority (treat like new leads)

---

### 3. Optional: Admin Dashboard (Nice to Have)

Current UI (`/mvp`) is minimal. An admin panel to:
- View all leads + pipeline status
- See call history + transcripts
- Trigger manual call / SMS
- Cancel pending jobs

Quick path: use Retool, or a simple React single-page app hitting your existing `/leads` + `/leads/{id}/messages` APIs.

---

## Env Vars Summary

All required env vars for live operation:

```bash
# Core
APP_ENV=production
DATABASE_URL=postgresql://user:pass@host/db

# Twilio (SMS + outbound calling)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_FROM_NUMBER=+1XXXXXXXXXX

# Meta (lead capture)
META_VERIFY_TOKEN=your_verify_token
META_APP_SECRET=your_app_secret
META_ACCESS_TOKEN=EAAAFxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Retell (voice agent) ← SET THIS FIRST
RETELL_API_KEY=your_retell_api_key
RETELL_AGENT_ID_EN=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
RETELL_BASE_URL=https://api.retellai.com

# OpenAI (transcription + extraction)
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.2

# Booking
CALENDLY_BOOKING_URL=https://calendly.com/your-link

# Owner alert
OWNER_ALERT_PHONE=+1XXXXXXXXXX

# Call window (ET)
CALL_WINDOW_START_HOUR=9
CALL_WINDOW_END_HOUR=20
APP_TIMEZONE=America/Toronto
```

---

## Test Checklist Before Going Live

- [ ] `APP_DRY_RUN=false` set
- [ ] Retell agent created + `RETELL_AGENT_ID_EN` set
- [ ] `RETELL_API_KEY` set
- [ ] `TWILIO_FROM_NUMBER` verified in Retell dashboard
- [ ] `/config-status` returns `true` for all integrations
- [ ] Send a test Meta lead → verify call initiated (check Retell dashboard)
- [ ] Verify SMS sent after call with Calendly link
- [ ] Verify owner alert received
- [ ] Legacy leads imported + `call_lead` jobs enqueued
- [ ] STOP/START SMS handling tested
- [ ] Retry policy tested (let a call go to no-answer → verify +15m retry)
