"""
Buyer Readiness Scorer
======================
Deterministic scoring from extracted call data.
No AI involved — pure logic so it's fast, free, and auditable.

Score components map directly to the plan in docs/SCORING.md.
Max raw score = 150, normalized to 100.

Tiers:
  hot    80+   → immediate owner alert + booking push
  warm   50-79 → book buyer consult sequence
  early  20-49 → nurture, send affordability guide
  cold   <20   → automated drip only
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Score weights
# ---------------------------------------------------------------------------
WEIGHTS: dict[str, int] = {
    "phone_answered":        15,   # they picked up = phone verified
    "tour_within_7_days":    25,   # high urgency signal
    "specific_property":     20,   # they have a home in mind
    "pre_approved":          30,   # strongest signal — they can buy
    "not_represented":       20,   # available to be represented
    "budget_gta_viable":     15,   # budget ≥ $400k (GTA minimum realistic)
    "down_payment_confirmed": 10,  # they know their down payment
    "buying_within_90_days": 15,   # near-term timeline
}

MAX_RAW = sum(WEIGHTS.values())  # 150


# ---------------------------------------------------------------------------
# Tag definitions — applied from extraction data
# ---------------------------------------------------------------------------
def compute_tags(extracted: dict[str, Any]) -> list[str]:
    """
    Return list of string tags from extracted call data.
    Tags are stored in leads.tags column.
    """
    tags: list[str] = []

    # Representation status
    rep = (extracted.get("currently_represented") or "").lower()
    if rep in {"yes", "true", "1"}:
        tags.append("already_represented")

    # Family agent risk
    if extracted.get("family_agent_risk"):
        tags.append("family_agent_risk")

    # Brampton-specific buyer signals
    if extracted.get("basement_income_interest"):
        tags.append("basement_income")

    if extracted.get("kitchen_priority"):
        tags.append("kitchen_priority")

    if extracted.get("parking_priority") or (extracted.get("parking_needed") or 0) >= 2:
        tags.append("parking_priority")

    if extracted.get("two_family_interest"):
        tags.append("two_family")

    if extracted.get("housepooling_interest"):
        tags.append("housepooling")

    # Financing
    financing = (extracted.get("financing_status") or "").lower()
    pre_approval_status = (extracted.get("pre_approval_status") or "").lower()
    if any(k in financing for k in ("pre-approv", "preapprov", "approved")):
        tags.append("pre_approved")
    elif any(k in pre_approval_status for k in ("approved",)):
        tags.append("pre_approved")
    elif any(k in financing for k in ("cash",)):
        pass  # Cash buyer — no mortgage needed
    elif any(k in financing for k in ("working", "in process", "talking to")):
        tags.append("needs_mortgage_review")
    elif not financing and not pre_approval_status:
        pass  # No financing info — don't assume
    else:
        tags.append("needs_mortgage_review")

    # Buyer type
    if extracted.get("first_time_buyer"):
        tags.append("first_time_buyer")

    if extracted.get("move_up_seller"):
        tags.append("move_up_seller")

    if extracted.get("investor_minded"):
        tags.append("investor_minded")

    return list(dict.fromkeys(tags))  # dedupe, preserve order


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------
@dataclass
class ScoreResult:
    score: int                            # 0-100 normalized
    tier: str                             # hot | warm | early | cold
    components: dict[str, int] = field(default_factory=dict)   # which signals fired
    tags: list[str] = field(default_factory=list)
    recommended_action: str = ""


def score_lead(extracted: dict[str, Any], call_answered: bool = True) -> ScoreResult:
    """
    Compute readiness score from extracted call data.

    Args:
        extracted:     dict from openai_extract.extract_qualification()
        call_answered: True if the call was picked up (phone_answered signal)

    Returns:
        ScoreResult with score, tier, components, tags, recommended_action
    """
    components: dict[str, int] = {}
    raw = 0

    def add(key: str, condition: bool) -> None:
        nonlocal raw
        if condition:
            pts = WEIGHTS[key]
            components[key] = pts
            raw += pts

    # --- Phone answered ---
    add("phone_answered", call_answered)

    # --- Tour urgency ---
    timeline = (extracted.get("timeline") or "").lower()
    timeline_days = extracted.get("timeline_days")
    urgency_keywords = ("asap", "immediately", "this week", "right away", "urgent")
    wants_soon = (
        any(k in timeline for k in urgency_keywords)
        or (isinstance(timeline_days, (int, float)) and 0 < timeline_days <= 7)
    )
    add("tour_within_7_days", wants_soon)

    # --- Specific property ---
    add("specific_property", bool(extracted.get("specific_property_address") or extracted.get("specific_property")))

    # --- Pre-approved ---
    financing = (extracted.get("financing_status") or "").lower()
    pre_status = (extracted.get("pre_approval_status") or "").lower()
    is_preapproved = any(k in financing for k in ("pre-approv", "preapprov", "approved")) or \
                     any(k in pre_status for k in ("approved",))
    add("pre_approved", is_preapproved)

    # --- Not currently represented ---
    rep = (extracted.get("currently_represented") or "").lower()
    not_rep = rep in {"no", "false", "0", "n/a", ""} or rep not in {"yes", "true", "1"}
    # edge: if key is missing, assume not represented (most leads aren't)
    add("not_represented", not_rep and "already_represented" not in compute_tags(extracted))

    # --- Budget GTA viable ---
    budget_max = extracted.get("budget_max")
    budget_min = extracted.get("budget_min")
    top_budget = budget_max or budget_min
    add("budget_gta_viable", isinstance(top_budget, (int, float)) and top_budget >= 400_000)

    # --- Down payment confirmed ---
    has_down_payment = bool(extracted.get("down_payment_amount") or extracted.get("down_payment_confirmed"))
    add("down_payment_confirmed", has_down_payment)

    # --- Buying within 90 days ---
    within_90 = (
        any(k in timeline for k in ("90 days", "3 months", "soon", "this year", "quarter")) or
        wants_soon or
        (isinstance(timeline_days, (int, float)) and 0 < timeline_days <= 90)
    )
    add("buying_within_90_days", within_90)

    # --- Normalize to 100 ---
    normalized = round((raw / MAX_RAW) * 100) if MAX_RAW > 0 else 0
    normalized = max(0, min(100, normalized))

    # --- Tier ---
    if normalized >= 80:
        tier = "hot"
        action = (
            "CALL NOW. Pre-approved, high urgency. "
            "Send booking link immediately after this alert."
        )
    elif normalized >= 50:
        tier = "warm"
        action = (
            "Book buyer consult within 24hrs. "
            "Send Home Fit Report teaser + booking SMS."
        )
    elif normalized >= 20:
        tier = "early"
        action = (
            "Add to nurture sequence. "
            "Send Brampton affordability guide + weekly Top 10 list."
        )
    else:
        tier = "cold"
        action = "Automated drip only. No agent time needed yet."

    tags = compute_tags(extracted)

    # Apply tier tag
    if tier == "hot":
        tags.append("hot_buyer")
    elif tier == "warm":
        tags.append("warm_buyer")

    return ScoreResult(
        score=normalized,
        tier=tier,
        components=components,
        tags=list(dict.fromkeys(tags)),
        recommended_action=action,
    )
