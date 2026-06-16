# Agentic Real Estate Brokerage — Architecture

_Last updated: June 2026_

---

## System Purpose

AI-leveraged real estate brokerage for Brampton/GTA. Agent handles trust, negotiation, representation, offer approval, client relationships. AI system handles everything else: lead intake, scoring, follow-up, SMS campaigns, compliance tracking.

---

## Live Services (Current State)

| Service | URL | Platform | Status |
|---------|-----|----------|--------|
| Python backend (dashboard + site) | https://realestateagentframework.onrender.com | Render free web service | ✅ Live |
| Static site fallback | https://anukabli-site.onrender.com | Render static | ✅ Live (DNS bypasses this) |
| Public site | https://anukabli.com | GoDaddy CNAME → Python backend | ✅ Live |

**Important:** `anukabli.com` DNS points to `realestateagentframework.onrender.com` (the Python backend), NOT to `anukabli-site`. The Python backend serves all 29 static site pages via a `StaticFiles` mount on `/`. Dashboard routes (`/login`, `/dashboard`, `/control`, `/api/*`) take priority over the static mount.

**Render free tier caveat:** Service spins down after 15 min inactivity → 50s cold start on first request. Upgrade to Starter ($7/mo) if cold starts become a problem.

---

## Database — Neon PostgreSQL

**Provider:** [Neon](https://neon.tech) free tier  
**Host:** `ep-empty-paper-ajn0deyx.c-3.us-east-2.aws.neon.tech`  
**Database:** `neondb`  
**Region:** US East 2 (AWS)  
**Expiry:** None — Neon free tier has no time-based expiry (unlike Render free PostgreSQL)  
**Storage limit:** 0.5 GB free  
**Set via:** `DATABASE_URL` env var in Render dashboard (manually set — NOT from render.yaml `fromDatabase`)

### What NOT to use

| DB | Status | Notes |
|----|--------|-------|
| `campaign-db` (Render) | ❌ Expired / Suspended | Orphaned. Data deleted ~June 2026. Not connected to live app. |
| `real-estate-db` (Render) | ❌ Never provisioned | Listed in render.yaml `fromDatabase` but blueprint was never applied. Ignore. |

---

## Database Schema

### `leads`
```sql
id                  text primary key          -- UUID string
created_at          timestamptz
source              text                      -- 'meta' | 'manual' | 'import'
meta_lead_id        text unique               -- Facebook lead ID
name                text
phone_e164          text                      -- e.g. +14165551234
email               text
consent_text        text                      -- e.g. 'Meta Lead Ads opt-in'
consent_timestamp   timestamptz
language            text default 'en'
status              text default 'new'        -- new | called | opted_out | needs_review | closed | resubscribed
do_not_contact      boolean default false
area                text                      -- e.g. 'Brampton', 'Mississauga' (from area code)
-- Buyer profile (populated after call)
tags                jsonb default '[]'
readiness_score     integer                   -- 0-100
readiness_tier      text                      -- hot | warm | early | cold
buyer_profile       jsonb                     -- full extracted + scored profile
scores              jsonb                     -- individual score components
```

### `jobs` (background queue)
```sql
id          bigserial primary key
type        text          -- job type (see Job Types below)
dedupe_key  text          -- unique index on (type, dedupe_key) where not null
payload     jsonb         -- job-specific data, e.g. {"lead_id": "..."}
run_at      timestamptz   -- when to execute
status      text          -- queued | running | done | failed | cancelled
attempts    integer
max_attempts integer
locked_at   timestamptz
locked_by   text
last_error  text
```

### `messages`
```sql
id                  bigserial primary key
lead_id             text → leads(id)
direction           text    -- 'in' | 'out'
channel             text    -- 'sms' | 'email'
twilio_message_sid  text
body                text
status              text    -- 'received' | 'sent' | 'delivered' | 'failed'
created_at          timestamptz
```

### `calls`
```sql
id                  bigserial primary key
lead_id             text → leads(id)
retell_call_id      text unique
twilio_call_sid     text
started_at          timestamptz
ended_at            timestamptz
duration_sec        integer
outcome             text
disconnection_reason text
transcript_text     text
extracted_json      jsonb
```

### `events` (audit log)
```sql
id          bigserial primary key
lead_id     text → leads(id)
type        text          -- e.g. 'meta_lead_webhook_received', 'twilio_inbound_sms'
payload_json jsonb
created_at  timestamptz
```

### `knowledge_chunks` (RAG store)
```sql
id          bigserial primary key
doc_id      text
source_path text
chunk_index integer
heading     text
body        text
topic       text
jurisdiction text default 'ontario'
audience    text default 'agent'
risk_level  text default 'low'
embedding   jsonb   -- float array, cosine similarity in Python
```

### `listings` (MLS cache — not yet populated)
```sql
id, mls_number, status, list_price, sold_price, address, city,
bedrooms, bathrooms, parking_spaces, has_garage, basement_suite,
basement_separate_entrance, basement_legal, ... (full schema in db.py)
```

### `audit_log`
```sql
id, entity_type, entity_id, action, user_id, details, created_at
```

---

## Job Types

| Job Type | Trigger | Handler |
|----------|---------|---------|
| `call_lead` | Meta webhook (new lead) | Calls lead via Retell AI |
| `send_followup_sms` | Meta webhook (if outside call window) | Sends intro SMS |
| `process_retell_call` | Retell webhook (call_ended / call_analyzed) | Extracts, scores, alerts owner |
| `reactivation_sms` | `POST /reactivation/jobs/seed` | Sends drip SMS to cold leads |
| `classify_sms_reply` | Inbound SMS (ambiguous reply) | OpenAI classifies intent |

---

## SMS Compliance — 3-Layer Defense

Triggered by any inbound SMS via `POST /webhooks/twilio/sms`:

1. **Layer 1 — Exact TCPA keywords** (`STOP`, `STOPALL`, `UNSUBSCRIBE`, `CANCEL`, `END`, `QUIT`):
   - Set `do_not_contact = true`
   - Set `status = 'opted_out'`
   - Cancel all queued jobs for lead
   - Reply: "You're opted out. Reply START to resubscribe."

2. **Layer 2 — Soft opt-out phrases** ("leave me alone", "don't text me", "not interested", "found a home", etc. — 27 fragments):
   - Set `do_not_contact = true`
   - Set `status = 'opted_out'`
   - Cancel all queued jobs for lead
   - No auto-reply

3. **Layer 3 — Any other reply** (ambiguous — "yes", "who is this?", "call me"):
   - Cancel all queued jobs for lead immediately
   - Set `status = 'needs_review'`
   - Enqueue `classify_sms_reply` job → OpenAI classifies as `opted_out | interested | closed | needs_review`
   - If `interested`: owner gets SMS alert with lead name, phone, message
   - If `opted_out` or `closed`: status updated accordingly

**Key rule:** ANY inbound reply (regardless of content) cancels all queued campaign jobs. No lead can receive a scheduled SMS after they've replied.

---

## Reactivation SMS Campaign

Endpoint: `POST /reactivation/jobs/seed`  
Daily limit: 20 leads/day (configurable via `REACTIVATION_SMS_DAILY_LIMIT` env var, default 20)  
Send window: 4–8 PM Toronto time (`REACTIVATION_SMS_WINDOW_START` / `_END`)  
Eligible leads: `status NOT IN ('opted_out', 'closed', 'needs_review')` AND `do_not_contact = false`

Admin endpoints (require auth):
- `GET /admin/sms-queue/diagnostics` — counts queued jobs by type, orphaned jobs, eligible leads
- `POST /admin/sms-queue/cancel-all` — cancels all queued SMS jobs (not calls)

---

## System Architecture

```
[Facebook Lead Ad]
       │
       ▼
[Meta Webhook POST /webhooks/meta]
       │
       ├──► create lead in `leads` table
       ├──► enqueue `call_lead` job (next call window)
       └──► enqueue `send_followup_sms` job (3-15s delay)
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    [Retell AI call]                [Twilio SMS out]
              │
    [Retell webhook POST /webhooks/retell]
              │
    enqueue `process_retell_call`
              │
    [OpenAI extraction] → buyer profile, score, tags
              │
    ┌─────────┴──────────┐
    ▼                    ▼
  Hot (80+)          Warm/Early/Cold
  Owner SMS alert    Book consult / drip
  + booking push

[Inbound SMS POST /webhooks/twilio/sms]
    │
    ├── TCPA keyword → DNC immediately
    ├── Soft opt-out → DNC immediately
    └── Any reply → cancel jobs + classify intent
```

---

## Module Map

```
app/
├── config.py                 — settings, env vars (reads DATABASE_URL, all API keys)
├── db.py                     — Neon connection pool (psycopg3) + MIGRATION_SQL
├── main.py                   — FastAPI app, all routes, StaticFiles mount
├── models.py                 — Pydantic models (legacy JSON storage fallback)
├── storage.py                — JSON storage (legacy, pre-DB, still used locally)
│
├── orchestrator/
│   ├── meta_graph.py         — fetch Facebook lead details from Graph API
│   ├── openai_extract.py     — extract qualification fields + classify_sms_reply()
│   ├── phone.py              — phone normalization, STOP/START/soft-optout detection
│   ├── repository.py         — all DB read/write operations (OrchestratorRepo)
│   ├── retell_client.py      — Retell AI API client (make calls)
│   ├── schedule.py           — call window enforcement (9am-8pm ET)
│   ├── scoring.py            — buyer readiness scorer (deterministic)
│   ├── crypto.py             — webhook signature verification (Meta + Retell)
│   └── worker.py             — background job processor (polls jobs table)
│
├── api/
│   ├── webhooks.py           — /webhooks/meta, /webhooks/retell, /webhooks/twilio/sms
│   └── ...
│
├── services/
│   ├── channels.py           — SMS/email send abstraction (Twilio)
│   ├── follow_up.py          — follow-up sequences
│   ├── home_fit_report.py    — Home Fit Report generator
│   ├── templates.py          — message templates
│   └── ...
│
└── copilot/                  — Ontario Knowledge Copilot (RAG)
    ├── chunker.py
    ├── embedder.py           — OpenAI text-embedding-3-small
    ├── retriever.py          — cosine similarity search in Python (no pgvector)
    └── copilot.py            — RAG query handler

site/                         — 29 static HTML pages served by Python backend
├── index.html                — anukabli.com homepage
├── brampton-homes-for-sale.html
├── hamilton-homes-for-sale.html
└── ... (all SEO pages)
```

---

## Route Priority in main.py

FastAPI routes are registered in order. `StaticFiles` mount is last (catch-all):

```
/health                       → health check (no auth)
/login                        → dashboard login page
/dashboard                    → dashboard UI (auth required)
/control                      → control center UI (auth required)
/api/*                        → API endpoints
/webhooks/*                   → inbound webhooks (Twilio, Retell, Meta)
/reactivation/*               → reactivation campaign endpoints
/admin/*                      → admin endpoints (auth required)
/                             → StaticFiles(site/) — catch-all for all site pages
```

---

## Buyer Readiness Scoring

Deterministic. Computed from OpenAI extraction output.

| Signal | Points |
|--------|--------|
| Phone verified (answered call) | +15 |
| Wants to tour within 7 days | +25 |
| Has specific property in mind | +20 |
| Pre-approved | +30 |
| Not currently represented | +20 |
| Budget matches GTA market (>400k) | +15 |
| Has down payment range confirmed | +10 |
| Buying within 90 days | +15 |
| **Max possible** | **150 → normalized to 100** |

Routing:
- **80+** (Hot) → Immediate owner SMS alert + booking push SMS
- **50-79** (Warm) → Book buyer consult sequence
- **20-49** (Early) → Save, nurture, affordability guide
- **<20** (Cold) → Automated drip only

---

## Lead Status Values

| Status | Meaning |
|--------|---------|
| `new` | Just created from Meta webhook |
| `called` | Retell call completed |
| `needs_review` | Replied to SMS ambiguously — human review needed |
| `opted_out` | TCPA or soft opt-out — do not contact |
| `resubscribed` | Sent START after opting out |
| `closed` | Found a home / deal closed |

---

## MLS Integration

Currently using **PropTx RESO API** (not TRREB DDF).  
Credentials: `PROPTX_API_KEY` or `PROPTX_USER` + `PROPTX_PASSWORD` env vars.  
Base URL: `https://query.ampre.ca/odata`  
Status: Not yet implemented — `listings` table exists but not populated.

---

## Ontario Knowledge Copilot

RAG system using OpenAI embeddings. No pgvector — cosine similarity computed in Python.

- Ingest: `POST /copilot/ingest` (text) or `POST /copilot/ingest-pdf` (PDF)
- Query: `POST /copilot/query`
- Store: `knowledge_chunks` table in Neon

---

## Environment Variables (Key Ones)

| Variable | Value / Source |
|----------|---------------|
| `DATABASE_URL` | Neon connection string (set manually in Render dashboard) |
| `APP_ENV` | `production` |
| `APP_DRY_RUN` | `false` |
| `APP_TIMEZONE` | `America/Toronto` |
| `CALL_WINDOW_START_HOUR` | `9` |
| `CALL_WINDOW_END_HOUR` | `20` |
| `REACTIVATION_SMS_DAILY_LIMIT` | `20` |
| `REACTIVATION_SMS_WINDOW_START` | `16` (4 PM) |
| `REACTIVATION_SMS_WINDOW_END` | `20` (8 PM) |
| `OPENAI_MODEL` | `gpt-4o-mini` |
| `TWILIO_FROM_NUMBER` | Your Twilio number |
| `OWNER_ALERT_PHONE` | Your phone (gets hot lead alerts) |
| `ADMIN_PASSWORD_HASH` | bcrypt hash — generate via `python scripts/gen_admin_hash.py` |
| `SECRET_KEY` | Session signing key — generate via `python -c "import secrets; print(secrets.token_hex(32))"` |
