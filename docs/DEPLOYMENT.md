# Deployment Guide

_Last updated: June 2026_

This doc tracks what is live, what is configured, and what still needs doing.

---

## Current Production State

| Component | Status | Notes |
|-----------|--------|-------|
| Python backend | ✅ Live | https://realestateagentframework.onrender.com |
| Static site (29 pages) | ✅ Live | Served by Python backend via StaticFiles |
| anukabli.com domain | ✅ Live | GoDaddy CNAME → Python backend |
| Neon PostgreSQL | ✅ Live | No expiry. Set manually in Render env vars. |
| Twilio SMS | ✅ Configured | Inbound webhook set to /webhooks/twilio/sms |
| OpenAI | ✅ Configured | gpt-4o-mini + text-embedding-3-small |
| Retell AI | ✅ Configured | English buyer qualifier agent |
| Meta Lead Ads webhook | ✅ Configured | /webhooks/meta |
| SMS compliance (3-layer) | ✅ Built | Pending push (commit b52593f) |
| Admin SMS queue endpoints | ✅ Built | Pending push (commit b52593f) |
| campaign-db (Render) | ❌ Dead | Expired. Not in use. Data deletes ~June 2026. |

---

## CRITICAL: Unpushed Commit

Commit `b52593f` is built but NOT deployed:

```bash
git push origin main
```

This deploys:
- Any inbound SMS reply → cancels all queued campaign jobs immediately
- Soft opt-out detection (27 phrases beyond TCPA keywords)
- OpenAI async classification for ambiguous replies
- `GET /admin/sms-queue/diagnostics`
- `POST /admin/sms-queue/cancel-all`

**Push this before running any reactivation campaign.**

---

## Database

**Provider:** Neon free tier  
**Host:** `ep-empty-paper-ajn0deyx.c-3.us-east-2.aws.neon.tech`  
**Database name:** `neondb`  
**How it's connected:** `DATABASE_URL` env var set manually in Render dashboard → RealEstateAgentFramework → Environment

Migration runs automatically on every app startup. Safe to re-run (all `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN IF NOT EXISTS`).

To run migration manually:
```bash
DATABASE_URL="postgresql://..." python -c "
from app.config import settings
from app.db import create_database, migrate
db = create_database(settings.database_url)
migrate(db)
print('done')
"
```

---

## After Pushing the Commit — Restart Campaign

Once `b52593f` is deployed (~2 min after push):

```bash
# 1. Check current queue state
curl https://realestateagentframework.onrender.com/admin/sms-queue/diagnostics

# 2. Cancel all stale queued SMS jobs
curl -X POST https://realestateagentframework.onrender.com/admin/sms-queue/cancel-all

# 3. Seed fresh reactivation campaign (20/day, 4-8pm Toronto)
curl -X POST https://realestateagentframework.onrender.com/reactivation/jobs/seed \
  -H "Content-Type: application/json" \
  -d '{"daily_limit": 20}'
```

---

## Environment Variables

All set in Render dashboard → RealEstateAgentFramework → Environment:

```env
# App
APP_ENV=production
APP_DRY_RUN=false
APP_TIMEZONE=America/Toronto
CALL_WINDOW_START_HOUR=9
CALL_WINDOW_END_HOUR=20

# Database (Neon — set manually, do NOT use fromDatabase in render.yaml)
DATABASE_URL=postgresql://neondb_owner:...@ep-empty-paper-ajn0deyx.c-3.us-east-2.aws.neon.tech/neondb?sslmode=require

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

# Twilio (SMS)
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1XXXXXXXXXX
OWNER_ALERT_PHONE=+1XXXXXXXXXX    # Your phone — gets hot lead + interested reply alerts

# Retell AI (outbound calling)
RETELL_API_KEY=...
RETELL_AGENT_ID_EN=...

# Meta Lead Ads
META_VERIFY_TOKEN=...
META_APP_SECRET=...
META_ACCESS_TOKEN=...

# Booking
CALENDLY_BOOKING_URL=https://calendly.com/your-link

# Business
COMPANY_NAME=Anu Kabli Real Estate
ADVISOR_NAME=Anu Kabli

# Reactivation SMS campaign
REACTIVATION_SMS_DAILY_LIMIT=20
REACTIVATION_SMS_WINDOW_START=16   # 4 PM
REACTIVATION_SMS_WINDOW_END=20     # 8 PM

# Control center auth
ADMIN_PASSWORD_HASH=...            # bcrypt hash — python scripts/gen_admin_hash.py
SECRET_KEY=...                     # python -c "import secrets; print(secrets.token_hex(32))"
SESSION_TTL_HOURS=24

# PropTx MLS (not yet active)
PROPTX_BASE_URL=https://query.ampre.ca/odata
PROPTX_API_KEY=...
```

---

## Twilio Webhook Configuration

Inbound SMS must route to the Python backend for STOP/reply handling:

- Twilio Console → Phone Numbers → Your number → Messaging
- "A message comes in" → `https://realestateagentframework.onrender.com/webhooks/twilio/sms`
- Method: POST

---

## Meta Lead Ads Webhook

- Meta Business Manager → Lead Ads → Webhook Settings
- Webhook URL: `https://realestateagentframework.onrender.com/webhooks/meta`
- Verify Token: matches `META_VERIFY_TOKEN` in Render env vars
- Subscribed to: `leadgen` events

---

## Site Pages

29 static HTML pages in `site/` folder. Served by Python backend at root (`/`).

All paths registered in `render.yaml` as rewrites (for the `anukabli-site` static fallback service), but the primary domain `anukabli.com` uses the Python backend, which handles these via `StaticFiles(directory="site/", html=True)`.

Key pages:
- `/` → `site/index.html`
- `/brampton-homes-for-sale`
- `/hamilton-homes-for-sale`
- `/ontario-land-transfer-tax-calculator`
- (+ 25 more neighbourhood pages)

---

## Admin Endpoints (after b52593f is deployed)

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/admin/sms-queue/diagnostics` | GET | Required | Count queued jobs, orphaned jobs, eligible leads |
| `/admin/sms-queue/cancel-all` | POST | Required | Cancel all queued SMS jobs (not calls) |
| `/reactivation/jobs/seed` | POST | Required | Seed fresh campaign (daily_limit param) |
| `/reactivation/queue` | GET | Required | View current SMS queue with lead names |

---

## Key API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check (no auth) |
| `/leads/{id}/profile` | GET | Get lead with scoring data |
| `/copilot/query` | POST | Query Knowledge Copilot |
| `/copilot/ingest` | POST | Ingest text into knowledge base |
| `/copilot/ingest-pdf` | POST | Ingest PDF into knowledge base |
| `/webhooks/meta` | GET/POST | Meta Lead Ads webhook |
| `/webhooks/retell` | POST | Retell call completion webhook |
| `/webhooks/twilio/sms` | POST | Twilio inbound SMS (STOP/START/replies) |

---

## Common Issues

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| DB connection fails on startup | Wrong DATABASE_URL | Must use `postgresql://` not `postgres://`, must have `?sslmode=require` for Neon |
| Lead replies still getting SMS | b52593f not deployed | Push commit |
| "Unknown" names in SMS queue | Job `lead_id` not matching any lead (orphaned jobs) | Run cancel-all, then reseed |
| Score is 0 | Call not answered / extraction failed | Check OpenAI key, transcript not empty |
| Cold start slow (50s+) | Render free tier sleeps | Upgrade to Render Starter $7/mo or add UptimeRobot ping |
| campaign-db connection refused | It's expired | Don't use it. DATABASE_URL points to Neon. |

---

## PropTx MLS (Not Yet Active)

MLS listing data for Home Fit Reports requires PropTx RESO API:
1. Contact support@proptx.ca for API key after agreement approval
2. Add `PROPTX_API_KEY` and `PROPTX_BASE_URL=https://query.ampre.ca/odata` to Render env vars
3. `listings` table already exists in Neon — just needs population

---

## Knowledge Copilot Setup (Optional)

Drop PDFs into `knowledge-base/` subfolders, then ingest:

```bash
# Text/markdown
curl -X POST https://realestateagentframework.onrender.com/copilot/ingest \
  -H "Content-Type: application/json" \
  -d '{"text": "...", "doc_id": "brampton-aru-rules", "source_path": "brampton/aru-rules.md", "topic": "zoning"}'

# PDF
curl -X POST https://realestateagentframework.onrender.com/copilot/ingest-pdf \
  -H "Content-Type: application/json" \
  -d '{"pdf_path": "/path/to/file.pdf", "doc_id": "reco-info-guide-2024", "topic": "registration"}'

# Query
curl -X POST https://realestateagentframework.onrender.com/copilot/query \
  -H "Content-Type: application/json" \
  -d '{"query": "RECO disclosure requirements for dual agency in Ontario?"}'
```
