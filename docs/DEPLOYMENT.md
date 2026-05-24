# Deployment Guide
## What You Need To Do When You're Back

This doc is the complete human handoff. Everything the AI built is ready. Your job is to configure credentials, deploy, and test with a real lead.

---

## Prerequisites Checklist

| Item | Status | Notes |
|------|--------|-------|
| PostgreSQL database (Neon, Railway, Render Postgres) | ⬜ Need URL | Free tier works |
| Twilio account (SMS) | ⬜ Need credentials | Account SID + Auth Token + From number |
| OpenAI API key | ⬜ Need key | GPT-4o-mini + text-embedding-3-small |
| Retell AI account | ⬜ Need API key + agent ID | For outbound AI calling |
| Meta/Facebook Business Manager | ⬜ Need access token | For lead ad webhook |
| Calendly (or any booking link) | ⬜ Need URL | Goes in follow-up SMS |
| Python 3.11+ installed | ⬜ Local | For running tests |
| Render account | ⬜ Existing | For deployment |

---

## Step 1 — Environment Variables

Copy `.env.example` to `.env` and fill in all values:

```env
# App
APP_ENV=production
APP_DRY_RUN=false
APP_BASE_URL=https://your-app.onrender.com

# Database (Postgres)
DATABASE_URL=postgresql://user:password@host:5432/dbname

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small

# Twilio (SMS)
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1XXXXXXXXXX
OWNER_ALERT_PHONE=+1XXXXXXXXXX    # Your phone — gets hot lead SMS alerts

# Retell AI (outbound calling)
RETELL_API_KEY=...
RETELL_AGENT_ID_EN=...            # Your English buyer qualifier agent ID

# Meta Lead Ads
META_VERIFY_TOKEN=...             # You create this random string
META_APP_SECRET=...               # From Meta app settings
META_ACCESS_TOKEN=...             # Page access token (long-lived)

# Booking
CALENDLY_BOOKING_URL=https://calendly.com/your-link

# Business
COMPANY_NAME=Your Brokerage Name
ADVISOR_NAME=Your Name

# Knowledge Copilot
KNOWLEDGE_BASE_PATH=/path/to/knowledge-base  # Relative to project root
COPILOT_TOP_K=5
```

---

## Step 2 — Install Dependencies

```bash
pip install -r requirements.txt
pip install pypdf   # For PDF ingestion into Knowledge Copilot
```

---

## Step 3 — Run Database Migration

Migration runs automatically on startup. To run manually:

```bash
python -c "
from app.config import settings
from app.db import create_database, migrate
db = create_database(settings.database_url)
migrate(db)
print('Migration complete.')
"
```

Tables created:
- `leads` — with scoring columns (tags, readiness_score, readiness_tier, buyer_profile, scores)
- `events` — audit log
- `calls` — Retell call records + transcripts
- `messages` — SMS/email records
- `jobs` — background job queue
- `knowledge_chunks` — Knowledge Copilot RAG store

---

## Step 4 — Deploy to Render

1. Push to GitHub (this repo)
2. Go to Render → New Web Service → Connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add all environment variables from Step 1
6. Deploy

**Important:** Render free tier sleeps after 15 min inactivity. For a lead intake system, use the paid Starter plan ($7/mo) or set up a cron ping to keep it alive.

---

## Step 5 — Configure Retell AI Agent

Your Retell AI agent needs to ask Brampton-specific qualifying questions. Update your agent script to capture:

**Required questions:**
1. What's your timeline for purchasing?
2. Have you been pre-approved for a mortgage? For how much?
3. Are you currently working with another agent?
4. What's your budget range?
5. Do you have your down payment ready? Roughly how much?
6. Are you looking for a specific property or area?
7. How many parking spots do you need?
8. Is a basement income suite important to you?
9. Will anyone else be buying with you (parents, family)?
10. Is this your first home purchase?

**Why these matter:** The extraction prompt is trained on these exact topics. Missing them = lower scoring accuracy.

---

## Step 6 — Configure Meta Lead Ads Webhook

1. Go to Meta Business Manager → Lead Ads → Webhook Settings
2. Set Webhook URL: `https://your-app.onrender.com/webhooks/meta`
3. Set Verify Token: same value as `META_VERIFY_TOKEN` in your `.env`
4. Subscribe to: `leadgen` events

**Test with Meta's lead ads testing tool** before launching your first ad.

---

## Step 7 — Configure Twilio Inbound SMS Webhook

For STOP/START handling (opt-out compliance):

1. Go to Twilio Console → Phone Numbers → Your number → Messaging
2. Set "A message comes in" webhook to: `https://your-app.onrender.com/webhooks/twilio/sms`
3. Method: POST

---

## Step 8 — Ingest Knowledge Base (Optional but Recommended)

Drop your PDF documents into `knowledge-base/` subfolders:
```
knowledge-base/
├── reco/           → RECO Information Guide, registration bulletins
├── fsra/           → Mortgage advertising rules (relevant for referrals)
├── orea/           → Purchased textbook chapters (you own these)
├── brampton/       → Zoning, ARU rules, permit process documents
└── internal/       → Your SOPs, scripts, objection handlers
```

**Ingest each document:**
```bash
# Option 1: Via API (PDF)
curl -X POST https://your-app.onrender.com/copilot/ingest-pdf \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_path": "/path/to/knowledge-base/reco/info-guide.pdf",
    "doc_id": "reco-info-guide-2024",
    "topic": "registration",
    "jurisdiction": "ontario",
    "audience": "agent"
  }'

# Option 2: Via API (text/markdown)
curl -X POST https://your-app.onrender.com/copilot/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "text": "...your document text...",
    "doc_id": "brampton-aru-rules",
    "source_path": "brampton/aru-rules.md",
    "topic": "zoning",
    "jurisdiction": "ontario",
    "audience": "agent"
  }'
```

**Query the copilot:**
```bash
curl -X POST https://your-app.onrender.com/copilot/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the RECO disclosure requirements for dual agency in Ontario?"}'
```

---

## Step 9 — Get TRREB DDF API Access

MLS listing data is needed for the Home Fit Report listing mode. Until you have API access, the report runs in template mode (agent fills in scores manually).

**Steps:**
1. Log in to TRREB Member Portal
2. Apply for DDF (Data Distribution Facility) access — it's free for members
3. Once approved, get your API credentials
4. Add `TRREB_API_KEY` and `TRREB_API_URL` to your `.env`
5. Build the MLS listing fetcher (next phase — not built yet)

---

## Step 10 — Run Tests

```bash
# All tests
pytest tests/ -v

# Just scoring (no external dependencies)
pytest tests/test_scoring.py -v

# Just copilot logic (no DB/API needed)
pytest tests/test_copilot.py -v
```

Expected: All tests pass. If any fail, check that imports resolve correctly.

---

## Step 11 — End-to-End Test

**Manual test flow:**
1. Use Meta Lead Ads testing tool to send a test lead
2. Check Render logs — should see: lead created → job queued → call initiated
3. Answer the Retell call (or let it hit voicemail to test retry logic)
4. Check DB: `SELECT * FROM leads ORDER BY created_at DESC LIMIT 1;`
5. Should have: `readiness_score`, `readiness_tier`, `tags` populated
6. Check `events` table for full audit trail
7. Should receive owner SMS alert on your phone
8. Lead should receive follow-up SMS with booking link

**Expected timeline:**
- Lead arrives via webhook → within 30 seconds
- AI call attempt → within 5 minutes
- SMS follow-up → 3-15 seconds after call ends
- Owner alert → immediately after call ends

---

## Common Issues

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| DB migration fails | Wrong DATABASE_URL format | Use `postgresql://` not `postgres://` |
| Retell call not made | Missing `RETELL_AGENT_ID_EN` | Check Retell dashboard for agent ID |
| Meta webhook 403 | Wrong `META_VERIFY_TOKEN` | Must match exactly in Meta and `.env` |
| Owner SMS not sent | Missing `OWNER_ALERT_PHONE` | Add to `.env` with country code |
| Score is 0 | Call not answered / extraction failed | Check OpenAI key, transcript not empty |
| Copilot returns "no info" | Knowledge base not ingested | Run ingest on your documents first |

---

## Key API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/config-status` | GET | Verify all config is set |
| `/leads/{id}/profile` | GET | Get lead with scoring data |
| `/copilot/query` | POST | Query Knowledge Copilot |
| `/copilot/ingest` | POST | Ingest text into knowledge base |
| `/copilot/ingest-pdf` | POST | Ingest PDF into knowledge base |
| `/webhooks/meta` | GET/POST | Meta Lead Ads webhook |
| `/webhooks/retell` | POST | Retell call completion webhook |
| `/webhooks/twilio/sms` | POST | Twilio inbound SMS (STOP/START) |

---

## Phase 2 — When Ready to Scale

When lead volume exceeds your capacity (~20+ qualified/month):
1. Recruit agents under brokerage umbrella
2. Expose `/leads/{id}/profile` in an agent dashboard
3. Route warm/early leads to recruited agents
4. System becomes the brokerage offer — AI infrastructure as the value prop
5. Revenue model shifts: agent split on closed deals vs. commission-only

The infrastructure is already built for this. You just need to add:
- Agent auth/login
- Lead assignment by tier
- Agent performance tracking
