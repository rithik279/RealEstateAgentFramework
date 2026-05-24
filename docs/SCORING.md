# Buyer Readiness Scoring

## Purpose

Deterministic score (0-100) computed from AI-extracted call data.  
No LLM involved in scoring — pure logic. Fast, free, auditable.

Scored after every Retell AI call. Stored on the `leads` table.  
Drives all downstream routing: owner alerts, SMS content, follow-up sequences.

---

## Score Components

| Signal | Points | Logic |
|--------|--------|-------|
| Phone answered | +15 | `call_answered=True` (not no_answer/busy/failed) |
| Tour within 7 days | +25 | `timeline` contains urgency keyword OR `timeline_days` ≤ 7 |
| Specific property | +20 | `specific_property=True` OR `specific_property_address` is set |
| Pre-approved | +30 | `financing_status` contains "pre-approv/preapprov/approved" OR `pre_approval_status="approved"` |
| Not represented | +20 | `currently_represented` is not "yes/true/1" AND no `already_represented` tag |
| Budget GTA viable | +15 | `budget_max` OR `budget_min` ≥ $400,000 |
| Down payment confirmed | +10 | `down_payment_amount` is set OR `down_payment_confirmed=True` |
| Buying within 90 days | +15 | `timeline` contains 90-day keywords OR `timeline_days` ≤ 90 |
| **Total max** | **150** | Normalized to 100 |

**Normalization:** `score = round((raw / 150) * 100)`

---

## Tiers and Actions

| Tier | Score | Action |
|------|-------|--------|
| 🔴 Hot | 80-100 | Immediate owner SMS alert. Booking push SMS to lead with urgency message. |
| 🟡 Warm | 50-79 | Buyer consult sequence. Tailored booking SMS. |
| 🟢 Early | 20-49 | Nurture sequence. Affordability guide. Weekly top-10 list. |
| ⚪ Cold | < 20 | Automated drip only. No agent time needed yet. |

---

## Tier Logic Notes

**Hot buyer (80+):** Pre-approved + wants to see something fast + not working with anyone = call them now. These convert.

**Warm buyer (50-79):** Strong intent but missing one key signal (usually pre-approval or very tight timeline). Book a consult — they just need guidance to qualify.

**Early buyer (20-49):** Researching. Good for nurture sequences, market updates, affordability guides. Don't over-invest agent time.

**Cold (<20):** May be early-stage, just got a Facebook ad, not serious yet. Drip only. Revisit if they engage.

---

## Tags Applied

Tags are computed from the same `extracted_json` and stored in `leads.tags` (JSONB array).

| Tag | Applied When |
|-----|-------------|
| `pre_approved` | Financing status confirms pre-approval |
| `needs_mortgage_review` | No pre-approval detected |
| `already_represented` | Currently working with another agent |
| `family_agent_risk` | Buyer mentioned a family member who is an agent |
| `basement_income` | Interested in basement rental income |
| `kitchen_priority` | Kitchen quality/size is a key factor |
| `parking_priority` | Parking/garage is explicitly important |
| `two_family` | Buying with parents or extended family |
| `housepooling` | Two families pooling budget |
| `first_time_buyer` | First time purchasing |
| `move_up_seller` | Already owns, looking to upgrade |
| `investor_minded` | Mentioned investment/cashflow goals |
| `hot_buyer` | Score ≥ 80 (applied after scoring) |
| `warm_buyer` | Score 50-79 (applied after scoring) |

---

## Extraction Fields Required

These fields must be extracted from the call transcript by OpenAI for scoring to work:

```
timeline                — string ("ASAP", "3 months", "this year")
timeline_days           — integer (estimated days to purchase)
specific_property       — boolean
specific_property_address — string
financing_status        — string ("pre-approved", "working with broker")
pre_approval_status     — string ("approved", "in progress")
currently_represented   — string ("yes", "no")
budget_max              — number (CAD)
budget_min              — number (CAD)
down_payment_amount     — number (CAD)
down_payment_confirmed  — boolean

# For tags only:
basement_income_interest — boolean
kitchen_priority         — boolean
parking_needed           — integer
parking_priority         — boolean
two_family_interest      — boolean
housepooling_interest    — boolean
family_agent_risk        — boolean
first_time_buyer         — boolean
move_up_seller           — boolean
investor_minded          — boolean
```

---

## Code Location

- Scorer: `app/orchestrator/scoring.py`
- Called from: `app/orchestrator/worker.py` → `_process_retell_call()`
- Stored via: `app/orchestrator/repository.py` → `set_readiness()`
- Retrieved via: `GET /leads/{id}/profile`
