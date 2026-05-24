# Master Guide — Agentic Real Estate Brokerage

**Read this first when you return. Everything you need to understand, deploy, and complete the system.**

---

## 1. What Was Built (AI Sessions)

Two AI sessions built the core system. Here is every file that exists and what it does.

---

### The Full File Map

```
RealEstateAgentFramework/
│
├── app/
│   ├── main.py                         ← FastAPI app, all endpoints, startup
│   ├── config.py                       ← All env var config (Settings class)
│   ├── db.py                           ← DB connection + schema migrations
│   ├── models.py                       ← Pydantic models (Lead, Message, etc.)
│   ├── storage.py                      ← JSON fallback storage (dev only)
│   │
│   ├── orchestrator/
│   │   ├── worker.py                   ← Post-call pipeline: extract→score→nurture→alert
│   │   ├── scoring.py                  ← Buyer readiness scorer (0-100, 8 signals)
│   │   ├── openai_extract.py           ← GPT transcript extraction (30+ fields)
│   │   ├── repository.py               ← All DB queries (leads, knowledge chunks)
│   │   ├── crypto.py                   ← HMAC signature verification (Meta, Retell)
│   │   ├── meta_graph.py               ← Meta Lead Ads API (fetch lead details)
│   │   ├── phone.py                    ← Phone number normalization, STOP/START
│   │   ├── retell_client.py            ← Retell API client (trigger calls)
│   │   └── schedule.py                 ← Call window (9am-8pm EST enforcement)
│   │
│   ├── copilot/
│   │   ├── copilot.py                  ← Main RAG engine (embed→retrieve→GPT)
│   │   ├── chunker.py                  ← Text/PDF → semantic chunks
│   │   ├── embedder.py                 ← OpenAI text-embedding-3-small wrapper
│   │   ├── retriever.py                ← Cosine similarity search over JSONB
│   │   └── classifier.py              ← Risk level classifier (low/medium/high/critical)
│   │
│   ├── services/
│   │   ├── home_fit_report.py          ← 5-dimension buyer-property match report
│   │   ├── listing_scorer.py           ← Score/rank/shortlist MLS listings vs buyer
│   │   ├── nurture_sequences.py        ← Tier-aware SMS sequences (warm/early/cold)
│   │   ├── mls_client.py              ← TRREB DDF API client (skeleton, needs creds)
│   │   ├── channels.py                 ← SMS/channel sender
│   │   ├── call_scheduler.py           ← Retry call scheduling
│   │   ├── follow_up.py                ← Legacy follow-up service
│   │   ├── openai_chat.py              ← OpenAI chat wrapper
│   │   ├── retell_call.py              ← Retell call service
│   │   ├── templates.py                ← SMS message templates
│   │   └── transcript_extraction.py    ← Transcript post-processing
│   │
│   └── ui/
│       ├── dashboard.html              ← Dark mode buyer intelligence dashboard
│       └── index.html                  ← Legacy MVP UI
│
├── knowledge-base/
│   ├── reco/
│   │   └── reco-key-obligations.md     ← TRESA, BRA, multiple rep, advertising rules
│   ├── brampton/
│   │   └── market-overview.md          ← Price ranges, neighbourhoods, ARU rules
│   ├── internal/
│   │   ├── buyer-consultation-script.md ← Full call script with Brampton probes
│   │   ├── objection-handlers.md        ← 20+ objection responses with RECO notes
│   │   └── offer-strategy-guide.md      ← APS clauses, offer night, CMA, red flags
│   ├── orea/                            ← EMPTY — add your OREA PDFs here
│   └── fsra/                            ← EMPTY — add FSRA mortgage content here
│
├── scripts/
│   ├── smoke_test.py                   ← 12-test deployment smoke test
│   ├── ingest_knowledge_base.py        ← CLI bulk knowledge base ingestion
│   └── import_legacy_leads.py          ← Import old lead CSV files
│
├── tests/
│   ├── test_scoring.py                 (44 tests)
│   ├── test_copilot.py                 (35 tests)
│   ├── test_home_fit_report.py         (32 tests)
│   ├── test_nurture_sequences.py       (26 tests)
│   ├── test_pipeline_integration.py    (22 tests)
│   ├── test_listing_scorer.py          (38 tests)
│   └── test_api.py                     (53 tests)  ← 250 total, all pass
│
├── docs/
│   ├── MASTER_GUIDE.md                 ← This file
│   ├── ARCHITECTURE.md                 ← System architecture deep-dive
│   ├── DEPLOYMENT.md                   ← Step-by-step deployment checklist
│   ├── SCORING.md                      ← Buyer readiness scoring logic
│   ├── COPILOT.md                      ← Knowledge copilot setup and usage
│   ├── HOME_FIT_REPORT.md              ← Home fit report agent guide
│   └── RESUME.md                       ← Session checkpoint / quick reference
│
├── render.yaml                         ← Render.com deploy config
├── requirements.txt                    ← Python dependencies
└── .env.example                        ← All env vars with descriptions
```

---

## 2. How to See What's Built (Run Locally)

### Prerequisites
- Python 3.11+
- Install deps: `pip install -r requirements.txt`
- No database required to run in dev mode

### Start the server
```bash
cd C:\Users\manmi\GitHub\RealEstateAgentFramework
uvicorn app.main:app --port 8000 --reload
```

### What you can see immediately (no credentials needed)

| URL | What you see |
|-----|-------------|
| `http://localhost:8000/docs` | Interactive API docs — every endpoint listed |
| `http://localhost:8000/dashboard` | Buyer Intelligence Dashboard (shows DB error without DB — that's fine locally) |
| `http://localhost:8000/health` | `{"status":"ok","environment":"development"}` |
| `http://localhost:8000/config-status` | Which env vars are set vs missing |

### Run all tests
```bash
python -m pytest tests/ -v
# 250 tests, all pass in ~3 seconds, zero external dependencies
```

### Run smoke test (after server started)
```bash
python scripts/smoke_test.py --url http://localhost:8000
# 12/12 pass
```

---

## 3. Master Plan — What's Done vs What's Left

### SYSTEM 1: Lead Intake (Facebook → CRM)

| Feature | Built? | Notes |
|---------|--------|-------|
| Meta Lead Ads webhook | ✅ Done | `POST /webhooks/meta` |
| HMAC signature verification | ✅ Done | Cryptographically secure |
| Lead deduplication by phone | ✅ Done | No duplicate leads created |
| Lead stored to Postgres | ✅ Done | Full schema with all v2 columns |
| Auto-trigger Retell AI call | ✅ Done | Within 9am-8pm EST call window |
| Inbound SMS handling | ✅ Done | STOP/START/replies handled |

**Status: 100% complete. Just needs credentials wired (see Section 4).**

---

### SYSTEM 2: AI Phone Qualification (Retell + GPT)

| Feature | Built? | Notes |
|---------|--------|-------|
| Retell call trigger API | ✅ Done | `app/services/retell_call.py` |
| Post-call webhook | ✅ Done | `POST /webhooks/retell` |
| Transcript → 30+ field extraction | ✅ Done | GPT-4o-mini, Brampton-specific |
| Buyer readiness score (0-100) | ✅ Done | 8 signals, deterministic |
| 14 auto-tags applied | ✅ Done | `basement_income`, `pre_approved`, etc. |
| **Retell agent voice script** | ❌ NOT BUILT | You configure this in Retell dashboard |

**Retell script gap:** The AI knows what to extract but you need to configure the actual voice agent prompt in the Retell dashboard. See Section 5 for what to put there.

---

### SYSTEM 3: Lead Intelligence & Scoring

| Feature | Built? | Notes |
|---------|--------|-------|
| Readiness scoring (0-100) | ✅ Done | `app/orchestrator/scoring.py` |
| Tier classification (hot/warm/early/cold) | ✅ Done | Hot=80+, Warm=50-79, Early=20-49, Cold=<20 |
| 14 lead tags auto-applied | ✅ Done | From extraction signals |
| Score stored to DB | ✅ Done | `readiness_score`, `readiness_tier` columns |
| Buyer profile stored | ✅ Done | JSONB in `buyer_profile` column |

**Status: 100% complete.**

---

### SYSTEM 4: Nurture & Follow-Up

| Feature | Built? | Notes |
|---------|--------|-------|
| Warm sequence (3 SMS, 4h/24h/48h) | ✅ Done | `app/services/nurture_sequences.py` |
| Early sequence (4 SMS, 24h/3d/5d/7d) | ✅ Done | |
| Cold sequence (2 SMS, 7d/14d) | ✅ Done | |
| Owner alert SMS (hot leads) | ✅ Done | Score + tier + recommended action |
| **Post-tour follow-up** | ❌ NOT BUILT | Need to add tour-completed trigger |
| **Offer day sequence** | ❌ NOT BUILT | Pre-offer + post-offer SMS |
| **Post-closing sequence** | ❌ NOT BUILT | Thank you, referral ask, review request |

**Status: Pre-call nurture complete. Post-tour lifecycle not built.**

---

### SYSTEM 5: Knowledge Copilot (AI Analyst)

| Feature | Built? | Notes |
|---------|--------|-------|
| RAG pipeline | ✅ Done | Embed → JSONB retrieval → GPT answer |
| Risk classification | ✅ Done | low/medium/high/critical auto-tagged |
| Dashboard copilot widget | ✅ Done | Floating button → modal |
| PDF/text ingestion endpoints | ✅ Done | `/copilot/ingest`, `/copilot/ingest-pdf`, `/copilot/ingest-kb` |
| RECO/TRESA seed content | ✅ Done | BRA, multiple rep, advertising rules |
| Brampton market seed content | ✅ Done | Prices, neighbourhoods, ARU rules |
| Buyer script + objections | ✅ Done | Full call script, 20+ objection handlers |
| Offer strategy guide | ✅ Done | APS clauses, CMA, red flags |
| **OREA forms content** | ❌ NOT ADDED | Drop your OREA PDFs in `knowledge-base/orea/` |
| **FSRA mortgage content** | ❌ NOT ADDED | Optional — for mortgage referral questions |

**Status: Infrastructure 100% done. Content needs your OREA PDFs added.**

---

### SYSTEM 6: Home Fit Report

| Feature | Built? | Notes |
|---------|--------|-------|
| 5-dimension scorer (budget/basement/parking/kitchen/layout) | ✅ Done | |
| Template mode (no MLS data) | ✅ Done | Agent fills in manually |
| Listing mode (with MLS data) | ✅ Done | Auto-scored — needs MLS creds |
| Multi-listing rank/shortlist | ✅ Done | `app/services/listing_scorer.py` |
| API endpoint | ✅ Done | `POST /leads/{id}/home-fit-report` |
| **MLS data connection** | ❌ SKELETON | `app/services/mls_client.py` — needs TRREB DDF creds |
| **Auto-send report to buyer** | ❌ NOT BUILT | Report generates but not SMS'd/emailed |

**Status: Works in template mode now. Full auto mode needs MLS credentials.**

---

### SYSTEM 7: Dashboard & UI

| Feature | Built? | Notes |
|---------|--------|-------|
| Buyer Intelligence Dashboard | ✅ Done | Dark mode, live data |
| Tier filter + score bars | ✅ Done | |
| Lead detail modal | ✅ Done | Click any row → full profile |
| Copilot widget | ✅ Done | |
| **Lead editing** | ❌ NOT BUILT | Can't manually update lead status from UI |
| **Home Fit Report view** | ❌ NOT BUILT | Report data not shown in dashboard |
| **Call initiation from dashboard** | ❌ NOT WIRED | Button exists, not connected to Retell |

---

## 4. What Needs to Be Wired for Deployment

### Step-by-step in order

#### STEP 1 — Connect repo to Render (15 min)
1. Go to [render.com](https://render.com), create account
2. New → Web Service → Connect GitHub repo `rithik279/RealEstateAgentFramework`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. New → PostgreSQL → name it `real-estate-db`, free tier
6. Copy the `DATABASE_URL` from the DB → paste into Web Service env vars

#### STEP 2 — Set all environment variables in Render dashboard
Go to your Web Service → Environment → add these:

```
# Required for anything to work
DATABASE_URL          (auto from Render DB — copy the Internal Connection String)
OPENAI_API_KEY        sk-...  (from platform.openai.com)
OPENAI_MODEL          gpt-4o-mini
EMBEDDING_MODEL       text-embedding-3-small

# Required for SMS (Twilio)
TWILIO_ACCOUNT_SID    ACxxxxxxxxxxxx  (from console.twilio.com)
TWILIO_AUTH_TOKEN     xxxxxxxxxxxx
TWILIO_FROM_NUMBER    +1XXXXXXXXXX   (your Twilio number)
OWNER_ALERT_PHONE     +1XXXXXXXXXX   (YOUR cell — gets hot lead alerts)

# Required for AI phone calls (Retell)
RETELL_API_KEY        key_xxxxxxxxxx  (from app.retellai.com)
RETELL_AGENT_ID_EN    agent_xxxxxxxxxx (your Retell agent ID)

# Required for Facebook Lead Ads
META_VERIFY_TOKEN     any-secret-string-you-choose
META_APP_SECRET       xxxxxxxxxx  (from Meta Developer App)
META_ACCESS_TOKEN     xxxxxxxxxx  (from Meta Lead Ads)

# Optional but recommended
CALENDLY_BOOKING_URL  https://calendly.com/yourname
COMPANY_NAME          Your Brokerage Name
ADVISOR_NAME          Your Name

# Already set in render.yaml (don't need to add)
APP_ENV               production
APP_DRY_RUN           false
APP_TIMEZONE          America/Toronto
CALL_WINDOW_START_HOUR  9
CALL_WINDOW_END_HOUR    20
```

#### STEP 3 — Configure Retell AI agent (30-60 min)

Go to [app.retellai.com](https://app.retellai.com) → your agent → edit the prompt.

**What the Retell agent needs to ask and extract:**

```
You are a friendly real estate qualification assistant for [COMPANY_NAME].
Your job is to qualify buyers for Brampton/GTA homes.

REQUIRED questions to ask (in a natural conversation):
1. What area and type of home are you looking for? (detached, semi, condo?)
2. What's your budget range?
3. How soon are you looking to buy? (specific timeline)
4. Do you have a mortgage pre-approval? If yes, for how much?
5. Do you need a basement income suite? (important for Brampton buyers)
6. How many parking spots do you need? Garage?
7. How many bedrooms? Any extended family living with you?
8. Are you currently working with a real estate agent?
9. Is there a specific property address you're interested in?
10. Do you have your down payment ready? Roughly how much?

IMPORTANT: Sound natural, not like a form. One question at a time.
End the call by booking a consultation: [CALENDLY_BOOKING_URL]
```

After configuring, copy the Agent ID → set as `RETELL_AGENT_ID_EN` in Render.

#### STEP 4 — Configure Meta Lead Ads webhook (20 min)

1. Go to [developers.facebook.com](https://developers.facebook.com) → your App
2. Products → Webhooks → Subscribe to `leadgen` events
3. Callback URL: `https://your-app.onrender.com/webhooks/meta`
4. Verify Token: the same string you set as `META_VERIFY_TOKEN` in Render
5. Subscribe to your Facebook Page
6. Get your Meta App Secret → set as `META_APP_SECRET` in Render
7. Generate a Page Access Token → set as `META_ACCESS_TOKEN` in Render

#### STEP 5 — Configure Twilio inbound SMS (10 min)

1. Go to [console.twilio.com](https://console.twilio.com)
2. Phone Numbers → your number → Configure
3. When a message comes in → Webhook → `https://your-app.onrender.com/webhooks/twilio/sms`
4. HTTP POST

#### STEP 6 — Configure Retell post-call webhook (5 min)

1. In Retell dashboard → your agent → Post Call Webhook
2. URL: `https://your-app.onrender.com/webhooks/retell`

#### STEP 7 — Deploy and verify

```bash
# Run smoke test against live URL
python scripts/smoke_test.py --url https://your-app.onrender.com

# Run full test with actual call simulation
python scripts/smoke_test.py --url https://your-app.onrender.com --full
```

#### STEP 8 — Ingest knowledge base

After deploy, hit this endpoint once:
```bash
curl -X POST https://your-app.onrender.com/copilot/ingest-kb
```

Or from Render dashboard → Shell → `python scripts/ingest_knowledge_base.py`

#### STEP 9 — Add OREA content (optional but high value)

Drop your OREA PDF forms into `knowledge-base/orea/` → re-run ingest.
The copilot will then answer questions about specific form clauses.

#### STEP 10 — Get TRREB DDF credentials (unlocks MLS features)

1. Log into [trreb.ca](https://www.trreb.ca) member portal
2. Apply for DDF (Data Distribution Facility) API access
3. You'll get a username + password
4. Set in Render: `TRREB_DDF_USER` and `TRREB_DDF_PASSWORD`
5. Now `POST /leads/{id}/home-fit-report` works in full auto mode with real listing data

---

## 5. How All the Pieces Connect

```
FACEBOOK AD
    │
    │  Lead submits form
    ▼
POST /webhooks/meta
    │  Verify HMAC signature (META_APP_SECRET)
    │  Fetch lead details via Graph API (META_ACCESS_TOKEN)
    │  Create lead in Postgres
    │  Check call window (9am-8pm EST)
    ▼
Retell API → trigger AI phone call
    │  Uses RETELL_API_KEY + RETELL_AGENT_ID_EN
    │  Passes lead phone, name, metadata
    ▼
RETELL AI CALLS THE LEAD
    │  Conversation follows your agent prompt
    │  Asks 10 qualification questions
    │  Tries to book Calendly appointment
    ▼
POST /webhooks/retell  (Retell sends call_ended event)
    │
    ├─► openai_extract.py
    │       GPT-4o-mini reads transcript
    │       Extracts 30+ structured fields
    │       (budget, timeline, basement interest, pre-approval, etc.)
    │
    ├─► scoring.py
    │       8 signals → raw score → normalize to 0-100
    │       Assigns tier: hot/warm/early/cold
    │       Generates 14 tags
    │       Recommended action
    │
    ├─► repository.py → Postgres
    │       Saves score, tier, tags, buyer_profile to leads table
    │
    ├─► nurture_sequences.py
    │       If warm: enqueues 3 SMS messages (4h, 24h, 48h later)
    │       If early: enqueues 4 SMS messages (1d, 3d, 5d, 7d later)
    │       If cold: enqueues 2 SMS messages (7d, 14d later)
    │       If hot: skip — owner alerted immediately
    │
    └─► SMS owner alert (if hot)
            Twilio sends YOU an SMS:
            "HOT LEAD: John Singh, Score 87, pre-approved $900k,
             wants basement suite, tour within 7 days.
             CALL NOW: +16471234567"

MEANWHILE, AGENT USES DASHBOARD
    │
    ├─► GET /dashboard
    │       Dark mode dashboard
    │       All leads sorted by score
    │       Click lead → full profile modal
    │       Score, tier, tags, buyer profile, signals
    │
    ├─► POST /copilot/query
    │       Ask: "What are BRA requirements under TRESA?"
    │       Copilot: embed query → find relevant chunks → GPT answer
    │       Returns answer + risk level + sources
    │
    └─► POST /leads/{id}/home-fit-report
            Template mode: 5 dimensions with placeholders
            Listing mode: full auto-score vs MLS listing data
            Returns: overall score, grade (A+ to D), highlights, concerns

INBOUND SMS FROM LEAD
    │
POST /webhooks/twilio/sms
    │  STOP → unsubscribe (legal)
    │  START → resubscribe
    │  Any reply → log, notify owner
    ▼
    (future: route reply to AI conversation)
```

---

## 6. The 5 Agents — Roles and Status

### Agent 1: Harvey (You, the Licensed Agent)
**Role:** Handles trust, negotiation, offer signing, fiduciary duty. Anything that requires a registered RECO licensee.
**What's automated:** Alerts, dashboards, scoring tell you exactly when and how to act.
**What you do manually:** Call hot leads, sign offers, negotiate, show properties.

### Agent 2: Mike (The AI Analyst)
**This is the software system — all of it.**
**Role:** Everything else. Qualifies leads, scores them, nurtures them, answers compliance questions, generates reports.
**Status:** Core pipeline built. MLS integration pending credentials.

### Agent 3: Retell AI Phone Caller
**Role:** First-touch qualification call. Extracts 30+ data points from a natural conversation.
**Status:** Infrastructure built. You need to write the agent prompt in Retell dashboard.

### Agent 4: Knowledge Copilot
**Role:** On-demand compliance and market knowledge. Ask it anything about TRESA, RECO, Brampton market, offer strategy.
**Status:** Built. Seed content loaded. Add OREA PDFs for full coverage.

### Agent 5: Nurture Sequencer
**Role:** Keeps leads warm automatically. Right message at the right time based on buyer tier.
**Status:** Built. Warm/early/cold sequences done. Post-tour lifecycle not yet built.

---

## 7. What You Need to Complete (Your Action Items)

### HIGH PRIORITY — Needed before any lead can flow
| Task | Who | Time |
|------|-----|------|
| Create Render account + connect GitHub repo | You | 15 min |
| Set all env vars in Render dashboard | You | 20 min |
| Get OpenAI API key (platform.openai.com) | You | 5 min |
| Get Twilio account + phone number | You | 20 min |
| Get Retell account + create agent | You | 30 min |
| Write Retell agent prompt (use template in Section 4) | You | 30 min |
| Configure Meta webhook | You | 20 min |
| Configure Twilio inbound webhook | You | 10 min |
| Configure Retell post-call webhook | You | 5 min |
| Run smoke test on live URL | You | 5 min |
| Ingest knowledge base (one API call) | You | 2 min |

### MEDIUM PRIORITY — Unlocks more features
| Task | Who | Time |
|------|-----|------|
| Apply for TRREB DDF credentials | You | 30 min + wait |
| Add OREA PDFs to `knowledge-base/orea/` | You | 30 min |
| Import legacy leads CSV | You | `python scripts/import_legacy_leads.py` |

### LOW PRIORITY — Future builds (can be done later)
| Task | Notes |
|------|-------|
| Post-tour follow-up sequence | Add after first tours happen |
| Offer day SMS sequence | Add when making first offers |
| Post-closing sequence | Thank you + referral ask |
| Call initiation from dashboard | Connect dashboard "Call" button to Retell API |
| Lead status editing from dashboard | Currently read-only |
| Home Fit Report view in dashboard | Report generates via API, not shown in UI |
| Phase 2: agent recruitment portal | When deal volume exceeds your capacity |

---

## 8. End-to-End Test (After Deployment)

Once deployed and wired, test the full flow:

### Test A: Manual API test
```bash
# Simulate a Facebook lead coming in
curl -X POST https://your-app.onrender.com/webhooks/retell \
  -H "Content-Type: application/json" \
  -d '{
    "event": "call_ended",
    "call": {
      "call_id": "test_001",
      "from_number": "+16471110001",
      "call_status": "ended",
      "transcript": "Agent: Hi are you looking for a home in Brampton?\nUser: Yes, detached home around 900k. Need a basement suite. Pre-approved already. Looking in 2 months.",
      "metadata": {"lead_phone": "+16471110001", "lead_name": "Test Buyer"}
    }
  }'

# Check lead was scored
curl https://your-app.onrender.com/leads-scored | python -m json.tool

# Check dashboard
open https://your-app.onrender.com/dashboard
```

### Test B: Real Facebook lead test
1. Create a test lead via your Facebook Lead Ad form (or Meta test tool)
2. Watch Render logs for: `Meta lead received → Retell call triggered`
3. Answer your own test call
4. 30s after hangup: check dashboard for the scored lead
5. If hot: check your cell for owner alert SMS

### Test C: Copilot test
```bash
curl -X POST https://your-app.onrender.com/copilot/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are my BRA obligations before showing a buyer a property?"}'
```

---

## 9. Key Business Logic to Know

### Buyer Readiness Score (0-100)
| Signal | Points | What it means |
|--------|--------|---------------|
| Phone answered | 15 | They picked up |
| Tour within 7 days | 25 | Immediate intent |
| Specific property | 20 | Already found something |
| Pre-approved | 30 | Financing ready |
| Not represented | 20 | Available to sign BRA |
| Budget GTA-viable | 15 | Can actually afford market |
| Down payment confirmed | 10 | Funds real |
| Buying within 90 days | 15 | Timeline is real |
| **Max raw: 150 → normalized to 100** | | |

### Tier Actions
| Tier | Score | Your Action |
|------|-------|-------------|
| HOT | 80+ | Call within 30 min. You get SMS alert immediately. |
| WARM | 50-79 | Automated 3-SMS sequence. You call within 24h. |
| EARLY | 20-49 | Automated 4-SMS nurture over 7 days. |
| COLD | <20 | 2 check-ins over 14 days. Minimal effort. |

### TRESA / RECO Compliance Built In
- BRA required before sharing confidential strategies (copilot warns)
- Multiple representation requires written consent from all parties
- All material facts must be disclosed in writing
- Copilot risk-levels flag compliance-sensitive questions (high/critical = review before acting)

---

## 10. Quick Reference — Common Commands

```bash
# Start local server
uvicorn app.main:app --port 8000 --reload

# Run all tests
python -m pytest tests/ -q

# Run smoke test (server must be running)
python scripts/smoke_test.py --url http://localhost:8000

# Ingest knowledge base (server + OpenAI + DB needed)
curl -X POST http://localhost:8000/copilot/ingest-kb

# Dry-run knowledge base ingest (no credentials needed)
python scripts/ingest_knowledge_base.py --dry-run

# Import legacy leads
python scripts/import_legacy_leads.py --file "Old RE Leads for Reactivation.csv"

# Check git status
git log --oneline -10
git status
```

---

*Generated by AI build sessions. Code is in `main` branch on GitHub.*
*Tests: 250/250 passing. Version: 0.3.0.*
