"""
Listing scorer — evaluates how well a specific MLS listing matches a buyer profile.

Produces dimension-level scores and an overall fit score (0-100).
Works standalone (no OpenAI required) — pure rule-based logic.

Used by:
  - Home Fit Report (listing mode)
  - Auto-shortlist generation when MLS client is connected
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ListingFitScore:
    """Result of scoring one listing against one buyer profile."""

    mls_number: str
    address: str
    list_price: int
    total_score: float          # 0–100
    grade: str                  # A+ / A / B+ / B / C+ / C / D

    # Dimension scores (0–100 each)
    budget_score: float
    basement_score: float
    parking_score: float
    kitchen_score: float
    layout_score: float

    # Flags (human-readable issues or highlights)
    highlights: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)

    # Raw listing data preserved for display
    listing: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "mls_number": self.mls_number,
            "address": self.address,
            "list_price": self.list_price,
            "total_score": round(self.total_score, 1),
            "grade": self.grade,
            "dimensions": {
                "budget": round(self.budget_score, 1),
                "basement": round(self.basement_score, 1),
                "parking": round(self.parking_score, 1),
                "kitchen": round(self.kitchen_score, 1),
                "layout": round(self.layout_score, 1),
            },
            "highlights": self.highlights,
            "concerns": self.concerns,
        }


# ---------------------------------------------------------------------------
# Weights (must sum to 100)
# ---------------------------------------------------------------------------

WEIGHTS = {
    "budget": 20,
    "basement": 25,
    "parking": 15,
    "kitchen": 20,
    "layout": 20,
}

assert sum(WEIGHTS.values()) == 100


# ---------------------------------------------------------------------------
# Grade thresholds
# ---------------------------------------------------------------------------

def _grade(score: float) -> str:
    if score >= 93:
        return "A+"
    if score >= 85:
        return "A"
    if score >= 78:
        return "B+"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C+"
    if score >= 50:
        return "C"
    return "D"


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------


def _score_budget(buyer: dict, listing: dict) -> tuple[float, list[str], list[str]]:
    """
    How well does the listing price fit the buyer's budget?
    Returns (score, highlights, concerns).
    """
    highlights, concerns = [], []
    budget_max = buyer.get("budget_max") or 0
    list_price = listing.get("list_price") or listing.get("price") or 0

    if not budget_max or not list_price:
        return 50.0, highlights, concerns  # Unknown — neutral

    ratio = list_price / budget_max  # <1 = under budget, >1 = over

    if ratio <= 0.90:
        highlights.append(f"Priced ${int(budget_max - list_price):,} under max budget")
        score = 100.0
    elif ratio <= 1.00:
        score = 85.0
        pct_used = int(ratio * 100)
        highlights.append(f"Within budget ({pct_used}% of max)")
    elif ratio <= 1.05:
        score = 60.0
        concerns.append(f"${int(list_price - budget_max):,} over stated budget")
    elif ratio <= 1.10:
        score = 35.0
        concerns.append(f"${int(list_price - budget_max):,} over stated budget — stretch")
    else:
        score = 10.0
        concerns.append(f"${int(list_price - budget_max):,} over stated budget — exceeds range")

    return score, highlights, concerns


def _score_basement(buyer: dict, listing: dict) -> tuple[float, list[str], list[str]]:
    """
    Does the basement match buyer's income suite / family needs?
    """
    highlights, concerns = [], []
    wants_income = buyer.get("basement_income_interest", False)
    wants_in_law = buyer.get("two_family_interest", False)

    has_sep_entrance = listing.get("basement_separate_entrance", False)
    has_suite = listing.get("basement_suite", False)       # finished legal suite
    is_legal = listing.get("basement_legal", False)         # has permits
    basement_type = (listing.get("basement_type") or "").lower()

    # If buyer doesn't care about basement — neutral score
    if not wants_income and not wants_in_law:
        if has_sep_entrance and has_suite:
            highlights.append("Legal basement suite — bonus income potential")
            return 85.0, highlights, concerns
        return 70.0, highlights, concerns  # Neither needed nor present

    # Buyer wants basement suite
    if has_sep_entrance and (has_suite or is_legal):
        if is_legal:
            highlights.append("Legal basement suite with separate entrance")
            score = 100.0
        else:
            highlights.append("Separate entrance + finished suite (verify permits)")
            concerns.append("Confirm building permit and Residential Rental Unit permit")
            score = 85.0
    elif has_sep_entrance and not has_suite:
        highlights.append("Separate entrance — suite conversion possible")
        concerns.append("Unfinished basement — cost to convert to legal suite: ~$30-60k")
        score = 60.0
    elif has_suite and not has_sep_entrance:
        concerns.append("Finished suite but no separate entrance — not ideal for rental income")
        score = 40.0
    elif "finished" in basement_type:
        concerns.append("Finished basement — no separate entrance for rental")
        score = 30.0
    else:
        concerns.append("No basement suite or separate entrance")
        score = 10.0 if wants_income else 30.0

    return score, highlights, concerns


def _score_parking(buyer: dict, listing: dict) -> tuple[float, list[str], list[str]]:
    """
    Does parking match buyer's needs?
    """
    highlights, concerns = [], []
    needed = buyer.get("parking_needed") or 2  # default 2 cars
    available = listing.get("parking_spaces") or listing.get("parking_total") or 0
    has_garage = listing.get("garage") or listing.get("garage_spaces", 0) > 0

    if available >= needed + 1:
        highlights.append(f"{available} parking spaces — exceeds requirement")
        score = 100.0
    elif available >= needed:
        score = 90.0
        if has_garage:
            highlights.append(f"Garage + {available} total parking")
    elif available == needed - 1:
        concerns.append(f"1 short on parking: {available} available, {needed} needed")
        score = 55.0
    elif available == 0:
        concerns.append("No parking available")
        score = 10.0
    else:
        concerns.append(f"{needed - available} short on parking")
        score = 30.0

    if buyer.get("parking_priority") and available < needed:
        score = max(score - 15, 5.0)  # penalty if parking is a priority

    return score, highlights, concerns


def _score_kitchen(buyer: dict, listing: dict) -> tuple[float, list[str], list[str]]:
    """
    Kitchen quality vs. buyer expectations.
    """
    highlights, concerns = [], []
    wants_updated = buyer.get("kitchen_priority", False)
    wants_open = buyer.get("open_concept_preferred", False)

    kitchen_condition = (listing.get("kitchen_condition") or "").lower()
    is_open_concept = listing.get("open_concept", False)
    year_updated = listing.get("kitchen_year_updated")

    score = 70.0  # baseline

    if kitchen_condition in ("renovated", "updated", "modern", "new"):
        highlights.append("Updated kitchen")
        score = 90.0
    elif kitchen_condition in ("original", "dated", "older"):
        if wants_updated:
            concerns.append("Original kitchen — may need $20-40k renovation")
        score = 50.0

    if year_updated and year_updated >= 2018:
        highlights.append(f"Kitchen updated {year_updated}")
        score = max(score, 85.0)
    elif year_updated and year_updated >= 2010:
        score = max(score, 70.0)

    if is_open_concept:
        highlights.append("Open concept layout")
        score = min(score + 10, 100.0)
    elif wants_open and not is_open_concept:
        concerns.append("Closed-concept kitchen — may feel dated for family use")
        score = max(score - 10, 10.0)

    if wants_updated and score < 70:
        score = max(score - 10, 10.0)  # extra penalty if kitchen is priority

    return score, highlights, concerns


def _score_layout(buyer: dict, listing: dict) -> tuple[float, list[str], list[str]]:
    """
    Layout fit: bedrooms, family size, accessibility.
    """
    highlights, concerns = [], []
    needed_beds = buyer.get("bedrooms_needed") or 3
    family_size = buyer.get("family_size") or 3
    needs_in_law = buyer.get("two_family_interest", False)

    available_beds = listing.get("bedrooms") or listing.get("bedrooms_above_grade") or 0
    sq_ft = listing.get("square_feet") or listing.get("sqft") or 0

    score = 70.0

    if available_beds >= needed_beds + 1:
        highlights.append(f"{available_beds} bedrooms — room to grow")
        score = 95.0
    elif available_beds >= needed_beds:
        score = 85.0
        highlights.append(f"{available_beds} bedrooms matches requirement")
    elif available_beds == needed_beds - 1:
        concerns.append(f"1 bedroom short: {available_beds} available, {needed_beds} needed")
        score = 55.0
    elif available_beds > 0:
        concerns.append(f"Only {available_beds} bedrooms — {needed_beds} needed")
        score = 25.0

    if sq_ft:
        sqft_per_person = sq_ft / max(family_size, 1)
        if sqft_per_person >= 400:
            highlights.append(f"{sq_ft:,} sq ft — spacious for family of {family_size}")
        elif sqft_per_person < 250:
            concerns.append(f"{sq_ft:,} sq ft may feel tight for family of {family_size}")
            score = max(score - 15, 10.0)

    if needs_in_law:
        main_beds = listing.get("bedrooms_above_grade") or available_beds
        if main_beds < 3:
            concerns.append("Fewer than 3 beds above grade — limited if sharing with in-laws")
            score = max(score - 10, 10.0)

    return score, highlights, concerns


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------


class ListingScorer:
    """
    Score a listing against a buyer profile.
    Returns ListingFitScore.
    """

    def score(self, buyer_profile: dict, listing: dict) -> ListingFitScore:
        all_highlights, all_concerns = [], []

        budget_s, bh, bc = _score_budget(buyer_profile, listing)
        basement_s, bsh, bsc = _score_basement(buyer_profile, listing)
        parking_s, ph, pc = _score_parking(buyer_profile, listing)
        kitchen_s, kh, kc = _score_kitchen(buyer_profile, listing)
        layout_s, lh, lc = _score_layout(buyer_profile, listing)

        all_highlights.extend(bh + bsh + ph + kh + lh)
        all_concerns.extend(bc + bsc + pc + kc + lc)

        total = (
            budget_s * WEIGHTS["budget"] / 100
            + basement_s * WEIGHTS["basement"] / 100
            + parking_s * WEIGHTS["parking"] / 100
            + kitchen_s * WEIGHTS["kitchen"] / 100
            + layout_s * WEIGHTS["layout"] / 100
        )

        list_price = listing.get("list_price") or listing.get("price") or 0
        address = listing.get("address") or listing.get("street_address") or "Unknown address"
        mls_number = listing.get("mls_number") or listing.get("listing_id") or "N/A"

        return ListingFitScore(
            mls_number=mls_number,
            address=address,
            list_price=list_price,
            total_score=round(total, 1),
            grade=_grade(total),
            budget_score=budget_s,
            basement_score=basement_s,
            parking_score=parking_s,
            kitchen_score=kitchen_s,
            layout_score=layout_s,
            highlights=all_highlights,
            concerns=all_concerns,
            listing=listing,
        )

    def rank(self, buyer_profile: dict, listings: list[dict]) -> list[ListingFitScore]:
        """Score and rank multiple listings, best first."""
        scored = [self.score(buyer_profile, l) for l in listings]
        return sorted(scored, key=lambda s: s.total_score, reverse=True)

    def shortlist(
        self,
        buyer_profile: dict,
        listings: list[dict],
        *,
        top_n: int = 5,
        min_score: float = 60.0,
    ) -> list[ListingFitScore]:
        """Return top N listings above min_score threshold."""
        ranked = self.rank(buyer_profile, listings)
        return [s for s in ranked if s.total_score >= min_score][:top_n]
