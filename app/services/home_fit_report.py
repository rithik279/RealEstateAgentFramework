"""
Home Fit Report Generator
=========================
Generates structured buyer-property match reports for Brampton/GTA market.

Usage:
    from app.services.home_fit_report import HomeFitReportGenerator
    generator = HomeFitReportGenerator()
    report = generator.generate(buyer_profile, listing=None)  # template mode
    report = generator.generate(buyer_profile, listing=listing_dict)  # with MLS data

Output:
    HomeFitReport dataclass — JSON-serializable, ready to send to agent or format as PDF.

Two modes:
  1. Template mode (no MLS data): returns report with placeholders for agent to fill.
  2. Listing mode (with MLS data): scores each dimension and generates full report.

Scoring dimensions (Brampton-specific):
  - Kitchen quality/size match    (weight: 20)
  - Basement income potential     (weight: 25)
  - Parking / garage              (weight: 15)
  - Two-family layout suitability (weight: 20)
  - Budget fit                    (weight: 20)

Max dimension score = 100 per dimension.
Overall fit score = weighted average of scored dimensions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Dimension scoring
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    name: str
    score: int          # 0-100
    weight: int         # relative weight
    notes: str = ""
    flags: list[str] = field(default_factory=list)


@dataclass
class HomeFitReport:
    lead_id: str
    lead_name: str | None
    listing_address: str | None     # None = template mode
    listing_price: int | None
    overall_score: int              # 0-100 weighted
    fit_tier: str                   # strong | good | moderate | weak
    dimensions: list[DimensionScore]
    buyer_signals: list[str]        # tags from buyer profile relevant to this report
    agent_notes: list[str]          # action items for agent review
    template_mode: bool = False     # True = placeholders only, no MLS data
    mls_number: str | None = None


# ---------------------------------------------------------------------------
# Dimension weights
# ---------------------------------------------------------------------------
DIMENSION_WEIGHTS: dict[str, int] = {
    "kitchen":   20,
    "basement":  25,
    "parking":   15,
    "layout":    20,
    "budget":    20,
}
# Total = 100 (normalized)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------
class HomeFitReportGenerator:

    def generate(
        self,
        buyer_profile: dict[str, Any],
        *,
        listing: dict[str, Any] | None = None,
    ) -> HomeFitReport:
        """
        Args:
            buyer_profile: extracted_json from calls + scoring tags
            listing: MLS listing dict (see LISTING_SCHEMA below) or None for template mode

        Returns:
            HomeFitReport
        """
        template_mode = listing is None
        lead_id = str(buyer_profile.get("lead_id") or "")
        lead_name = buyer_profile.get("lead_name") or buyer_profile.get("name")

        dimensions = self._score_dimensions(buyer_profile, listing, template_mode)
        overall = self._weighted_score(dimensions) if not template_mode else 0
        fit_tier = self._tier(overall) if not template_mode else "pending"
        buyer_signals = self._extract_buyer_signals(buyer_profile)
        agent_notes = self._agent_notes(buyer_profile, dimensions, template_mode)

        return HomeFitReport(
            lead_id=lead_id,
            lead_name=lead_name,
            listing_address=listing.get("address") if listing else None,
            listing_price=listing.get("price") if listing else None,
            mls_number=listing.get("mls_number") if listing else None,
            overall_score=overall,
            fit_tier=fit_tier,
            dimensions=dimensions,
            buyer_signals=buyer_signals,
            agent_notes=agent_notes,
            template_mode=template_mode,
        )

    def _score_dimensions(
        self,
        buyer: dict[str, Any],
        listing: dict[str, Any] | None,
        template_mode: bool,
    ) -> list[DimensionScore]:
        if template_mode:
            return self._template_dimensions(buyer)
        return self._score_against_listing(buyer, listing or {})

    def _template_dimensions(self, buyer: dict[str, Any]) -> list[DimensionScore]:
        """Return placeholder dimensions — agent fills in scores after reviewing listing."""
        dims: list[DimensionScore] = []

        kitchen_note = "Buyer flagged kitchen as priority — assess counter space, appliances, layout." \
            if buyer.get("kitchen_priority") else "Standard kitchen assessment."
        dims.append(DimensionScore(
            name="Kitchen Quality", score=0, weight=DIMENSION_WEIGHTS["kitchen"],
            notes=f"[AGENT TO SCORE 0-100] {kitchen_note}",
            flags=["needs_agent_review"],
        ))

        basement_note = "Buyer interested in basement income — confirm separate entrance, suite potential." \
            if buyer.get("basement_income_interest") else "No basement income requirement noted."
        dims.append(DimensionScore(
            name="Basement Income Potential", score=0, weight=DIMENSION_WEIGHTS["basement"],
            notes=f"[AGENT TO SCORE 0-100] {basement_note}",
            flags=["needs_agent_review"],
        ))

        parking_needed = buyer.get("parking_needed") or (2 if buyer.get("parking_priority") else 1)
        dims.append(DimensionScore(
            name="Parking / Garage", score=0, weight=DIMENSION_WEIGHTS["parking"],
            notes=f"[AGENT TO SCORE 0-100] Buyer needs {parking_needed}+ parking spots.",
            flags=["needs_agent_review"],
        ))

        layout_note = "Two-family layout required — need in-law suite or dual master." \
            if buyer.get("two_family_interest") or buyer.get("housepooling_interest") \
            else "Standard family layout."
        dims.append(DimensionScore(
            name="Layout / Family Suitability", score=0, weight=DIMENSION_WEIGHTS["layout"],
            notes=f"[AGENT TO SCORE 0-100] {layout_note}",
            flags=["needs_agent_review"],
        ))

        budget_max = buyer.get("budget_max") or buyer.get("budget_min")
        budget_note = f"Buyer budget up to ${int(budget_max):,}. Confirm list price + closing costs fit." \
            if isinstance(budget_max, (int, float)) else "Budget not confirmed — verify pre-approval amount."
        dims.append(DimensionScore(
            name="Budget Fit", score=0, weight=DIMENSION_WEIGHTS["budget"],
            notes=f"[AGENT TO SCORE 0-100] {budget_note}",
            flags=["needs_agent_review"],
        ))

        return dims

    def _score_against_listing(
        self, buyer: dict[str, Any], listing: dict[str, Any]
    ) -> list[DimensionScore]:
        """Score dimensions when MLS listing data is available."""
        dims: list[DimensionScore] = []

        # --- Kitchen ---
        kitchen_score = 50  # default neutral
        kitchen_flags: list[str] = []
        if buyer.get("kitchen_priority"):
            ks = listing.get("kitchen_score")  # 0-100 from MLS enrichment
            if isinstance(ks, (int, float)):
                kitchen_score = int(ks)
                if kitchen_score < 60:
                    kitchen_flags.append("kitchen_below_expectation")
            else:
                kitchen_score = 50
                kitchen_flags.append("kitchen_data_missing")
        dims.append(DimensionScore(
            name="Kitchen Quality",
            score=kitchen_score,
            weight=DIMENSION_WEIGHTS["kitchen"],
            notes=listing.get("kitchen_notes") or "",
            flags=kitchen_flags,
        ))

        # --- Basement ---
        basement_score = 50
        basement_flags: list[str] = []
        if buyer.get("basement_income_interest"):
            has_sep_entrance = listing.get("basement_separate_entrance", False)
            has_suite = listing.get("basement_suite", False)
            if has_sep_entrance and has_suite:
                basement_score = 95
            elif has_sep_entrance:
                basement_score = 75
                basement_flags.append("no_suite_but_entrance_exists")
            elif has_suite:
                basement_score = 65
                basement_flags.append("suite_no_separate_entrance")
            else:
                basement_score = 20
                basement_flags.append("no_basement_income_potential")
        dims.append(DimensionScore(
            name="Basement Income Potential",
            score=basement_score,
            weight=DIMENSION_WEIGHTS["basement"],
            notes=listing.get("basement_notes") or "",
            flags=basement_flags,
        ))

        # --- Parking ---
        parking_needed = buyer.get("parking_needed") or (2 if buyer.get("parking_priority") else 1)
        parking_available = listing.get("parking_spaces") or listing.get("parking") or 0
        if isinstance(parking_available, str):
            try:
                parking_available = int(parking_available)
            except ValueError:
                parking_available = 0
        parking_flags: list[str] = []
        if parking_available >= parking_needed:
            parking_score = 100
        elif parking_available == parking_needed - 1:
            parking_score = 60
            parking_flags.append("one_short_on_parking")
        else:
            parking_score = 20
            parking_flags.append("insufficient_parking")
        dims.append(DimensionScore(
            name="Parking / Garage",
            score=parking_score,
            weight=DIMENSION_WEIGHTS["parking"],
            notes=f"{parking_available} spots available, {parking_needed} needed.",
            flags=parking_flags,
        ))

        # --- Layout ---
        layout_score = 70
        layout_flags: list[str] = []
        if buyer.get("two_family_interest") or buyer.get("housepooling_interest"):
            has_inlaw = listing.get("in_law_suite", False)
            has_dual = listing.get("dual_master", False)
            bedrooms = listing.get("bedrooms") or 0
            if has_inlaw or has_dual:
                layout_score = 90
            elif isinstance(bedrooms, int) and bedrooms >= 5:
                layout_score = 75
                layout_flags.append("large_enough_for_two_families")
            else:
                layout_score = 35
                layout_flags.append("may_not_suit_two_families")
        dims.append(DimensionScore(
            name="Layout / Family Suitability",
            score=layout_score,
            weight=DIMENSION_WEIGHTS["layout"],
            notes=listing.get("layout_notes") or "",
            flags=layout_flags,
        ))

        # --- Budget ---
        budget_flags: list[str] = []
        budget_max = buyer.get("budget_max") or buyer.get("budget_min")
        listing_price = listing.get("price") or listing.get("list_price")
        if isinstance(budget_max, (int, float)) and isinstance(listing_price, (int, float)):
            ratio = listing_price / budget_max
            if ratio <= 0.90:
                budget_score = 100  # well under budget
            elif ratio <= 1.0:
                budget_score = 85   # within budget
            elif ratio <= 1.05:
                budget_score = 60   # slightly over
                budget_flags.append("slightly_over_budget")
            else:
                budget_score = 20   # materially over
                budget_flags.append("over_budget")
        else:
            budget_score = 50
            budget_flags.append("budget_or_price_missing")
        dims.append(DimensionScore(
            name="Budget Fit",
            score=budget_score,
            weight=DIMENSION_WEIGHTS["budget"],
            notes=f"List: ${int(listing_price):,} / Buyer max: ${int(budget_max):,}" \
                if isinstance(listing_price, (int, float)) and isinstance(budget_max, (int, float)) else "",
            flags=budget_flags,
        ))

        return dims

    def _weighted_score(self, dimensions: list[DimensionScore]) -> int:
        total_weight = sum(d.weight for d in dimensions)
        if total_weight == 0:
            return 0
        weighted_sum = sum(d.score * d.weight for d in dimensions)
        return round(weighted_sum / total_weight)

    def _tier(self, score: int) -> str:
        if score >= 80:
            return "strong"
        elif score >= 60:
            return "good"
        elif score >= 40:
            return "moderate"
        return "weak"

    def _extract_buyer_signals(self, buyer: dict[str, Any]) -> list[str]:
        signals: list[str] = []
        signal_map = {
            "basement_income_interest": "Wants basement income suite",
            "kitchen_priority": "Kitchen quality is key priority",
            "two_family_interest": "Buying with extended family",
            "housepooling_interest": "Two families pooling budget",
            "parking_priority": "Parking/garage is priority",
            "first_time_buyer": "First-time buyer",
            "move_up_seller": "Move-up seller (existing owner)",
            "investor_minded": "Investment/cashflow focused",
            "pre_approved": "Pre-approved for financing",
        }
        for key, label in signal_map.items():
            val = buyer.get(key)
            if val and val not in (False, "no", "false", "0"):
                signals.append(label)
        return signals

    def _agent_notes(
        self,
        buyer: dict[str, Any],
        dimensions: list[DimensionScore],
        template_mode: bool,
    ) -> list[str]:
        notes: list[str] = []
        if template_mode:
            notes.append("Score each dimension 0-100 based on your property assessment.")
            notes.append("Focus on dimensions flagged [needs_agent_review].")
        all_flags = [f for d in dimensions for f in d.flags]
        if "kitchen_below_expectation" in all_flags:
            notes.append("Kitchen scores below buyer expectation — discuss renovation potential or alternatives.")
        if "no_basement_income_potential" in all_flags:
            notes.append("No basement income suite — significant miss for this buyer. Reconsider fit.")
        if "insufficient_parking" in all_flags:
            notes.append("Parking shortfall — confirm street parking situation or deal-breaker risk.")
        if "may_not_suit_two_families" in all_flags:
            notes.append("Layout may not work for two-family purchase — verify in person.")
        if "over_budget" in all_flags:
            notes.append("Price over buyer budget — discuss offer strategy or filter this out.")
        if buyer.get("family_agent_risk"):
            notes.append("Family agent risk: buyer mentioned a family member who is an agent. Proceed with transparency.")
        if not notes:
            notes.append("No major flags. Proceed with showing.")
        return notes


# ---------------------------------------------------------------------------
# Listing schema reference (for MLS integration)
# ---------------------------------------------------------------------------
LISTING_SCHEMA = {
    "address": "str",
    "mls_number": "str",
    "price": "int",
    "bedrooms": "int",
    "bathrooms": "int",
    "parking_spaces": "int",
    "basement_separate_entrance": "bool",
    "basement_suite": "bool",
    "in_law_suite": "bool",
    "dual_master": "bool",
    "kitchen_score": "int (0-100, from MLS enrichment or agent assessment)",
    "kitchen_notes": "str",
    "basement_notes": "str",
    "layout_notes": "str",
    "sqft": "int",
    "lot_size": "str",
    "year_built": "int",
    "property_type": "str",
    "neighbourhood": "str",
}
