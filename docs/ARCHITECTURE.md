# Agentic Real Estate Brokerage — Architecture

## System Purpose

AI-leveraged real estate brokerage for Brampton/GTA. Partner + Analyst model:
- **Partner (Harvey Specter)** = Licensed agent. Handles: trust, negotiation, representation, offer approval, client relationship.
- **Analyst (Mike Ross)** = AI system. Handles: everything else (lead intake, scoring, research, reports, compliance memory, follow-up, tracking).

Target: agent spends 80% of time on high-trust human tasks. AI covers 80% of current workload.

---

## Business Model

**Phase 1 (now):** Agentic brokerage — use system to close own deals. Prove unit economics.
**Phase 2 (when lead volume exceeds capacity):** Recruit agents under brokerage umbrella. System becomes the offer.

Revenue model: commission on closed deals. No SaaS until Phase 2.

---

## Budget Economics

```
$500 ad spend (Facebook/Meta)
→ ~17 leads at $30/lead worst case
→ 30% AI call answer rate = ~5 conversations
→ 2-3 qualified (readiness score 50+)
→ 1-2 appointments booked
→ 1 show-up

Target metric: cost per qualified appointment < $300
Scale only when this is proven.
```

---

## System Architecture

```
[Facebook Lead Ad]
       │
       ▼
[Meta Webhook] ──► [leads table] ──► [jobs queue]
                                          │
                              ┌───────────┼───────────┐
                              ▼           ▼           ▼
                        [call_lead] [send_followup] [notify_owner]
                              │
                              ▼
                    [Retell AI Caller]
                    (speed-to-lead < 5min)
                              │
                    [call transcript]
                              │
                              ▼
                    [OpenAI Extraction]
                    (Brampton-specific fields)
                              │
                              ▼
                    [Buyer Readiness Scorer]
                    (deterministic score 0-100)
                              │
                    ┌─────────┼──────────┐
                    ▼         ▼          ▼
                  Hot       Warm       Cold
               (80+)     (50-79)    (<50)
                    │         │          │
              Owner SMS  Book consult  Drip
              + booking   sequence    nurture
```

---

## Module Map

```
app/
├── config.py                 — settings, env vars
├── db.py                     — postgres connection pool + migrations
├── main.py                   — FastAPI app, routes, webhooks
├── models.py                 — Pydantic models (legacy JSON storage)
├── storage.py                — JSON storage (legacy, pre-DB)
│
├── orchestrator/
│   ├── meta_graph.py         — fetch Facebook lead details from Graph API
│   ├── openai_extract.py     — extract qualification fields from call transcript
│   ├── phone.py              — phone normalization, STOP/START detection
│   ├── repository.py         — all DB read/write operations
│   ├── retell_client.py      — Retell AI API client (make calls)
│   ├── schedule.py           — call window enforcement (9am-8pm ET)
│   ├── scoring.py            — [NEW] buyer readiness scorer (deterministic)
│   ├── crypto.py             — webhook signature verification
│   └── worker.py             — background job processor
│
├── services/
│   ├── channels.py           — SMS/email/FB send abstraction
│   ├── follow_up.py          — legacy follow-up sequences
│   ├── home_fit_report.py    — [NEW] Home Fit Report generator
│   ├── call_scheduler.py     — periodic call scheduling
│   ├── templates.py          — message templates
│   ├── transcript_extraction.py — transcript helpers
│   └── retell_call.py        — Retell call helpers
│
└── copilot/                  — [NEW] Ontario Knowledge Copilot
    ├── __init__.py
    ├── chunker.py            — PDF/text → semantic chunks
    ├── embedder.py           — OpenAI text-embedding-3-small
    ├── retriever.py          — pgvector search (cosine similarity)
    ├── classifier.py         — risk level classifier (low/medium/high/critical)
    └── copilot.py            — main RAG query handler

docs/
├── ARCHITECTURE.md           — this file
├── SCORING.md                — buyer readiness scoring logic
├── HOME_FIT_REPORT.md        — report template and agent guide
├── COPILOT.md                — knowledge copilot setup and usage
└── DEPLOYMENT.md             — handoff guide (what to do when back)

knowledge-base/               — [TO BE POPULATED by human]
├── reco/                     — RECO Information Guide, rep bulletins, TRESA FAQs
├── fsra/                     — mortgage ad rules, compliance manual
├── orea/                     — purchased textbooks, forms
├── brampton/                 — ARU rules, zoning, permit process
└── internal/                 — SOPs, scripts, checklists
```

---

## Database Schema

```sql
-- Core tables (existing)
leads           — lead identity, consent, status, do_not_contact
events          — audit log of all activity per lead
calls           — Retell call records + transcripts + extracted_json
messages        — SMS/email sent/received
jobs            — background job queue with deduplication

-- New columns on leads (added in migration v2)
tags            JSONB     — array of string tags e.g. ["basement_income","kitchen_priority"]
readiness_score INTEGER   — 0-100 buyer readiness score
readiness_tier  TEXT      — "hot" | "warm" | "early" | "cold"
buyer_profile   JSONB     — full extracted + scored buyer profile
scores          JSONB     — individual score components for transparency

-- New table (copilot)
knowledge_chunks            — embedded document chunks for RAG
```

---

## Lead Tagging System

Tags applied automatically from AI extraction + scoring:

| Tag | Trigger |
|-----|---------|
| `basement_income` | buyer expressed interest in rental income |
| `kitchen_priority` | kitchen/cooking mentioned as key factor |
| `parking_priority` | parking/garage mentioned as key factor |
| `two_family` | buying with parents or two families |
| `housepooling` | two families pooling budget |
| `pre_approved` | confirmed pre-approval |
| `needs_mortgage_review` | no pre-approval, interested in financing |
| `hot_buyer` | readiness score 80+ |
| `warm_buyer` | readiness score 50-79 |
| `already_represented` | mentioned working with another agent |
| `family_agent_risk` | mentioned family member is an agent |
| `move_up_seller` | already owns, looking to upgrade |
| `investor_minded` | mentioned investment/cashflow goals |
| `first_time_buyer` | mentioned first time buying |

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
- **80+** (Hot) → Immediate owner SMS alert + booking push SMS to lead
- **50-79** (Warm) → Book buyer consult sequence
- **20-49** (Early) → Save, nurture, affordability guide
- **<20** (Cold) → Automated drip only

See `docs/SCORING.md` for full detail.

---

## Ontario Knowledge Copilot

RAG (Retrieval-Augmented Generation) system. Not fine-tuning.
- Model does NOT memorize rules permanently
- Searches private knowledge base
- Retrieves relevant chunk
- Returns source-backed answer
- Flags risk level
- Human professional reviews high/critical responses before use

Query endpoint: `POST /copilot/query`
Ingest endpoint: `POST /copilot/ingest`

See `docs/COPILOT.md` for setup.

---

## MLS Integration (Pending — needs human)

Requires TRREB member API credentials (DDF or TREB data program).
Once connected, property intelligence agents can:
- Query listings by budget/area
- Score each listing against buyer profile
- Generate Home Fit Report automatically

Until MLS connected: report generator outputs template with placeholders agent fills manually.

---

## What Human Needs To Do (Deployment)

See `docs/DEPLOYMENT.md` for full checklist.

Short version:
1. Run DB migration (auto-runs on app startup)
2. Drop PDF documents into `knowledge-base/` subfolders
3. Call `POST /copilot/ingest` for each document
4. Update Retell agent script to ask Brampton-specific questions
5. Register for TRREB DDF API access
6. Deploy to Render (existing pipeline)
7. Test with real Facebook lead
