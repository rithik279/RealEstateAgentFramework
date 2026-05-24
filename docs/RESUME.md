# Session Resume Checkpoint

Last updated: Session 2 complete (May 2026).

## Current State

**Tests:** 250/250 passing  
**Version:** 0.3.0  
**Commits ahead of origin/main:** 5 (need to push — blocked by branch protection, do manually)

---

## What's Built (Complete)

### Core Pipeline
| Component | Status |
|-----------|--------|
| Meta webhook → lead intake | Done |
| Retell AI call trigger | Done |
| OpenAI transcript extraction (30+ fields) | Done |
| Buyer readiness scoring (8 signals, 0-100) | Done |
| 14 lead tags auto-applied | Done |
| Tier-aware nurture sequences (warm/early/cold) | Done |
| Owner SMS alert with tier/score | Done |
| Trust account / deposit tracking | Skeleton |

### Intelligence Layer
| Component | Status |
|-----------|--------|
| Knowledge Copilot (RAG — JSONB embeddings) | Done |
| Home Fit Report (template + listing mode) | Done |
| Listing Scorer (5 dimensions, grade A+-D) | Done |
| MLS client skeleton (TRREB DDF) | Skeleton — needs credentials |

### API Endpoints
| Endpoint | Status |
|----------|--------|
| `GET /` | Done |
| `GET /health` | Done |
| `GET /dashboard` | Done (dark mode UI) |
| `GET /leads` | Done |
| `GET /leads-scored` | Done (DB required) |
| `GET /leads/{id}/profile` | Done |
| `POST /leads/{id}/home-fit-report` | Done |
| `POST /copilot/query` | Done |
| `POST /copilot/ingest` | Done |
| `POST /copilot/ingest-pdf` | Done |
| `POST /copilot/ingest-kb` | Done (bulk walk knowledge-base/) |
| `POST /webhooks/meta` | Done |
| `POST /webhooks/retell` | Done |
| `POST /webhooks/twilio/sms` | Done |

### Knowledge Base (seed content in /knowledge-base)
| File | Contents |
|------|----------|
| `reco/reco-key-obligations.md` | TRESA, BRA, multiple rep, advertising rules |
| `brampton/market-overview.md` | Price ranges, neighbourhoods, ARU rules, basement income |
| `internal/buyer-consultation-script.md` | Full call script with Brampton probes |
| `internal/objection-handlers.md` | 20+ objection responses with RECO notes |
| `internal/offer-strategy-guide.md` | APS clauses, offer night strategy, red flags |

### Tests
| Suite | Tests | Status |
|-------|-------|--------|
| test_scoring.py | 44 | Pass |
| test_copilot.py | 35 | Pass |
| test_home_fit_report.py | 32 | Pass |
| test_nurture_sequences.py | 26 | Pass |
| test_pipeline_integration.py | 22 | Pass |
| test_listing_scorer.py | 38 | Pass |
| test_api.py | 53 | Pass |
| **Total** | **250** | **All pass** |

### Scripts
| Script | Purpose |
|--------|---------|
| `scripts/smoke_test.py` | Deployment smoke test — run after deploy |
| `scripts/ingest_knowledge_base.py` | CLI bulk knowledge base ingestion |
| `scripts/import_legacy_leads.py` | Import old lead CSV files |

---

## What You Need to Do (Deployment Checklist)

**Step 1: Push to GitHub**
```bash
git push origin main
```
(or create PR if you use branch protection)

**Step 2: Deploy on Render**
- Connect GitHub repo to Render
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Create Postgres DB (free tier) — upgrade to starter ($7/mo) for production

**Step 3: Set all env vars in Render dashboard**
```
DATABASE_URL          (auto-set by Render DB)
OPENAI_API_KEY        (required — GPT-4o-mini + embeddings)
OPENAI_MODEL          gpt-4o-mini
EMBEDDING_MODEL       text-embedding-3-small
TWILIO_ACCOUNT_SID    (from Twilio console)
TWILIO_AUTH_TOKEN
TWILIO_FROM_NUMBER    +1XXXXXXXXXX
OWNER_ALERT_PHONE     +1XXXXXXXXXX (your number)
RETELL_API_KEY        (from Retell dashboard)
RETELL_AGENT_ID_EN    (your Retell agent ID)
META_VERIFY_TOKEN     (set this, then use same value in Meta webhook config)
META_APP_SECRET       (from Meta App dashboard)
META_ACCESS_TOKEN     (from Meta Lead Ads)
CALENDLY_BOOKING_URL  https://calendly.com/yourlink
COMPANY_NAME          YourBrokerage Inc.
ADVISOR_NAME          Your Name
```

**Step 4: Configure webhooks**
- Meta Lead Ads → `https://yourapp.onrender.com/webhooks/meta`
- Twilio inbound SMS → `https://yourapp.onrender.com/webhooks/twilio/sms`
- Retell post-call → `https://yourapp.onrender.com/webhooks/retell`

**Step 5: Ingest knowledge base**
After deploy:
```bash
# Option A: API call
curl -X POST https://yourapp.onrender.com/copilot/ingest-kb

# Option B: CLI (from server)
python scripts/ingest_knowledge_base.py
```

**Step 6: Run smoke test**
```bash
python scripts/smoke_test.py --url https://yourapp.onrender.com
python scripts/smoke_test.py --url https://yourapp.onrender.com --full
```

**Step 7: Get TRREB DDF credentials**
- Apply at: https://www.trreb.ca/index.php/members-section/mls-rules-and-data
- Enter in Render env: `TRREB_DDF_USER` and `TRREB_DDF_PASSWORD`
- This unlocks Home Fit Report listing mode and auto-shortlist

---

## Pending / Future

| Item | Priority | Notes |
|------|----------|-------|
| Update Retell agent script | High | Add Brampton questions (basement, parking, timeline) |
| Post-tour follow-up sequence | Medium | Not built |
| Offer strategy report template | Medium | Not built |
| Closing tracker | Low | Future phase |
| Phase 2 agent recruitment portal | Low | When volume > capacity |
| pgvector upgrade | Low | For >10k knowledge chunks |

---

## Quick Test Commands

```bash
# All tests
python -m pytest tests/ -q

# Specific suite
python -m pytest tests/test_scoring.py -v
python -m pytest tests/test_listing_scorer.py -v

# Local smoke test
uvicorn app.main:app --port 8000 &
python scripts/smoke_test.py --url http://localhost:8000

# Full smoke with write tests (needs running server)
python scripts/smoke_test.py --url http://localhost:8000 --full

# Dry-run knowledge base ingestion
python scripts/ingest_knowledge_base.py --dry-run
```
