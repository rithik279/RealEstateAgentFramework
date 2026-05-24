# Home Fit Report

## Purpose

A structured buyer-property match report generated for each listing shown to a buyer.  
Scored on 5 Brampton-specific dimensions. Gives agent a data-backed conversation starter.

Two modes:
1. **Template mode** (no MLS data): Agent fills in scores after seeing the property
2. **Listing mode** (with MLS data): Auto-scored when TRREB DDF API is connected

---

## 5 Scoring Dimensions (Brampton Market)

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Kitchen Quality | 20% | Size, finishes, layout — critical for South Asian buyers |
| Basement Income Potential | 25% | Separate entrance, existing suite, conversion potential |
| Parking / Garage | 15% | Number of spots, covered parking, EV capability |
| Layout / Family Suitability | 20% | In-law suite, dual master, bedrooms for extended family |
| Budget Fit | 20% | List price vs. pre-approval + buffer for closing costs |

**Overall fit score** = weighted average of 5 dimensions (0-100)

---

## Fit Tiers

| Tier | Score | Meaning |
|------|-------|---------|
| Strong | 80-100 | Show this one. Hits all buyer priorities. |
| Good | 60-79 | Worth seeing. Minor misses. Discuss tradeoffs. |
| Moderate | 40-59 | Consider if nothing better available. |
| Weak | < 40 | Not a match. Don't waste showing time unless buyer insists. |

---

## Basement Income Scoring Detail

The highest-weight dimension because it's the #1 buyer priority in Brampton.

| Scenario | Score |
|----------|-------|
| Separate entrance + existing legal suite | 95 |
| Separate entrance only (suite potential) | 75 |
| Existing suite, no separate entrance | 65 |
| Finished basement, no entrance | 40 |
| Unfinished / not applicable | 20 |

---

## Budget Fit Scoring Detail

| List Price vs. Buyer Budget Max | Score |
|--------------------------------|-------|
| 10%+ under budget | 100 |
| At or under budget | 85 |
| 1-5% over budget | 60 — discuss offer strategy |
| 5%+ over budget | 20 — filter this listing |

Note: Budget includes closing costs (~1.5-2% of purchase price for first-time buyers after LTT rebate).

---

## Template Mode (No MLS Data)

When called without listing data, the report generates a template with agent prompts:

```
Kitchen Quality [AGENT TO SCORE 0-100]
  → Buyer flagged kitchen as priority — assess counter space, appliances, layout.

Basement Income Potential [AGENT TO SCORE 0-100]
  → Buyer interested in basement income — confirm separate entrance, suite potential.

Parking / Garage [AGENT TO SCORE 0-100]
  → Buyer needs 2+ parking spots.

Layout / Family Suitability [AGENT TO SCORE 0-100]
  → Two-family layout required — need in-law suite or dual master.

Budget Fit [AGENT TO SCORE 0-100]
  → Buyer budget up to $750,000. Confirm list price + closing costs fit.
```

---

## Usage

### Template mode (current — no MLS)

```python
from app.services.home_fit_report import HomeFitReportGenerator

generator = HomeFitReportGenerator()

# buyer_profile = extracted_json from call + tags
buyer_profile = {
    "lead_id": "abc123",
    "lead_name": "Harpreet Singh",
    "basement_income_interest": True,
    "kitchen_priority": True,
    "parking_needed": 2,
    "two_family_interest": False,
    "budget_max": 750_000,
    "down_payment_amount": 150_000,
}

report = generator.generate(buyer_profile)
# report.template_mode = True
# report.dimensions = [...] with [AGENT TO SCORE] notes
# report.agent_notes = ["Score each dimension 0-100 based on your property assessment."]
```

### Listing mode (when MLS connected)

```python
listing = {
    "address": "123 Heartlake Rd, Brampton ON",
    "mls_number": "W1234567",
    "price": 729_000,
    "bedrooms": 4,
    "bathrooms": 3,
    "parking_spaces": 3,
    "basement_separate_entrance": True,
    "basement_suite": True,
    "in_law_suite": False,
    "kitchen_score": 75,
    "kitchen_notes": "Updated 2022, quartz counters, island",
}

report = generator.generate(buyer_profile, listing=listing)
# report.overall_score = 84
# report.fit_tier = "strong"
# report.dimensions[0].score = 75  (kitchen)
# report.dimensions[1].score = 95  (basement — sep entrance + suite)
```

---

## Next Steps for MLS Integration

1. Get TRREB DDF API credentials (see DEPLOYMENT.md Step 9)
2. Build `app/services/mls_client.py` — fetch listing by MLS# or criteria
3. Map DDF listing fields to `LISTING_SCHEMA` in `home_fit_report.py`
4. Wire into agent workflow: buyer consult → run report on shortlisted properties → send to buyer

The `LISTING_SCHEMA` in `app/services/home_fit_report.py` documents all expected fields.

---

## Code Location

`app/services/home_fit_report.py`
- `HomeFitReportGenerator` — main class
- `HomeFitReport` — output dataclass
- `DimensionScore` — per-dimension result
- `LISTING_SCHEMA` — expected MLS fields for listing mode
