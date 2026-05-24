"""
Tests for app/services/home_fit_report.py
"""
from __future__ import annotations

import pytest

from app.services.home_fit_report import (
    HomeFitReportGenerator,
    HomeFitReport,
    DimensionScore,
    DIMENSION_WEIGHTS,
)

BUYER_FULL = {
    "lead_id": "test-123",
    "lead_name": "Harpreet Singh",
    "basement_income_interest": True,
    "kitchen_priority": True,
    "parking_needed": 2,
    "parking_priority": True,
    "two_family_interest": True,
    "housepooling_interest": False,
    "budget_max": 750_000,
    "budget_min": 650_000,
    "down_payment_amount": 150_000,
    "first_time_buyer": True,
    "pre_approved": True,
}

BUYER_MINIMAL = {
    "lead_id": "test-456",
    "lead_name": "John Smith",
    "budget_max": 600_000,
}

LISTING_GOOD = {
    "address": "123 Heartlake Rd, Brampton ON",
    "mls_number": "W1234567",
    "price": 729_000,
    "bedrooms": 4,
    "bathrooms": 3,
    "parking_spaces": 3,
    "basement_separate_entrance": True,
    "basement_suite": True,
    "in_law_suite": False,
    "kitchen_score": 80,
    "kitchen_notes": "Updated 2022, quartz counters",
}

LISTING_POOR = {
    "address": "456 Some St, Brampton ON",
    "price": 900_000,
    "bedrooms": 2,
    "parking_spaces": 1,
    "basement_separate_entrance": False,
    "basement_suite": False,
    "kitchen_score": 40,
}


class TestTemplateModeBasic:
    def setup_method(self):
        self.gen = HomeFitReportGenerator()

    def test_returns_home_fit_report(self):
        report = self.gen.generate(BUYER_FULL)
        assert isinstance(report, HomeFitReport)

    def test_template_mode_true(self):
        report = self.gen.generate(BUYER_FULL)
        assert report.template_mode is True

    def test_five_dimensions(self):
        report = self.gen.generate(BUYER_FULL)
        assert len(report.dimensions) == 5

    def test_dimension_names(self):
        report = self.gen.generate(BUYER_FULL)
        names = {d.name for d in report.dimensions}
        assert "Kitchen Quality" in names
        assert "Basement Income Potential" in names
        assert "Parking / Garage" in names
        assert "Layout / Family Suitability" in names
        assert "Budget Fit" in names

    def test_template_scores_zero(self):
        report = self.gen.generate(BUYER_FULL)
        for d in report.dimensions:
            assert d.score == 0

    def test_fit_tier_pending_in_template(self):
        report = self.gen.generate(BUYER_FULL)
        assert report.fit_tier == "pending"

    def test_overall_score_zero_in_template(self):
        report = self.gen.generate(BUYER_FULL)
        assert report.overall_score == 0

    def test_buyer_signals_extracted(self):
        report = self.gen.generate(BUYER_FULL)
        assert "Wants basement income suite" in report.buyer_signals
        assert "Kitchen quality is key priority" in report.buyer_signals
        assert "Buying with extended family" in report.buyer_signals

    def test_agent_notes_present(self):
        report = self.gen.generate(BUYER_FULL)
        assert len(report.agent_notes) > 0

    def test_needs_review_flag_in_dimensions(self):
        report = self.gen.generate(BUYER_FULL)
        all_flags = [f for d in report.dimensions for f in d.flags]
        assert "needs_agent_review" in all_flags

    def test_lead_name_preserved(self):
        report = self.gen.generate(BUYER_FULL)
        assert report.lead_name == "Harpreet Singh"

    def test_minimal_buyer_no_crash(self):
        report = self.gen.generate(BUYER_MINIMAL)
        assert report.template_mode is True
        assert len(report.dimensions) == 5


class TestListingMode:
    def setup_method(self):
        self.gen = HomeFitReportGenerator()

    def test_template_mode_false_with_listing(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_GOOD)
        assert report.template_mode is False

    def test_listing_address_populated(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_GOOD)
        assert report.listing_address == LISTING_GOOD["address"]

    def test_listing_price_populated(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_GOOD)
        assert report.listing_price == LISTING_GOOD["price"]

    def test_overall_score_nonzero(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_GOOD)
        assert report.overall_score > 0

    def test_fit_tier_assigned(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_GOOD)
        assert report.fit_tier in ("strong", "good", "moderate", "weak")

    def test_good_listing_scores_well(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_GOOD)
        assert report.fit_tier in ("strong", "good")
        assert report.overall_score >= 60

    def test_basement_high_score_with_entrance_and_suite(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_GOOD)
        basement = next(d for d in report.dimensions if "Basement" in d.name)
        assert basement.score >= 90  # sep entrance + suite = 95

    def test_parking_full_score_when_adequate(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_GOOD)
        parking = next(d for d in report.dimensions if "Parking" in d.name)
        assert parking.score == 100  # 3 available, 2 needed

    def test_budget_fit_within_range(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_GOOD)
        budget = next(d for d in report.dimensions if "Budget" in d.name)
        # 729k / 750k = 0.972 → within budget → 85
        assert budget.score >= 80

    def test_poor_listing_scores_low(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_POOR)
        # No basement, 1 parking (need 2), over budget ($900k > $750k)
        assert report.overall_score < 60

    def test_over_budget_flag(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_POOR)
        budget = next(d for d in report.dimensions if "Budget" in d.name)
        assert "over_budget" in budget.flags

    def test_parking_flag_when_short(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_POOR)
        parking = next(d for d in report.dimensions if "Parking" in d.name)
        # 1 space available, 2 needed → one_short_on_parking or insufficient_parking
        assert len(parking.flags) > 0
        assert any("parking" in f for f in parking.flags)

    def test_no_basement_income_flag(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_POOR)
        basement = next(d for d in report.dimensions if "Basement" in d.name)
        assert "no_basement_income_potential" in basement.flags

    def test_agent_notes_flag_issues(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_POOR)
        notes_text = " ".join(report.agent_notes).lower()
        assert any(word in notes_text for word in ("basement", "parking", "budget"))

    def test_two_family_layout_flag_when_no_inlaw(self):
        listing_no_inlaw = {**LISTING_GOOD, "in_law_suite": False, "dual_master": False, "bedrooms": 3}
        report = self.gen.generate(BUYER_FULL, listing=listing_no_inlaw)
        layout = next(d for d in report.dimensions if "Layout" in d.name)
        assert "may_not_suit_two_families" in layout.flags

    def test_score_in_valid_range(self):
        report = self.gen.generate(BUYER_FULL, listing=LISTING_GOOD)
        assert 0 <= report.overall_score <= 100
        for d in report.dimensions:
            assert 0 <= d.score <= 100


class TestWeightedScoring:
    def setup_method(self):
        self.gen = HomeFitReportGenerator()

    def test_weights_sum_to_100(self):
        assert sum(DIMENSION_WEIGHTS.values()) == 100

    def test_perfect_score_100(self):
        """All 100 dimensions → overall 100."""
        from app.services.home_fit_report import DimensionScore
        dims = [DimensionScore(name=k, score=100, weight=v) for k, v in DIMENSION_WEIGHTS.items()]
        assert self.gen._weighted_score(dims) == 100

    def test_zero_score_zero(self):
        from app.services.home_fit_report import DimensionScore
        dims = [DimensionScore(name=k, score=0, weight=v) for k, v in DIMENSION_WEIGHTS.items()]
        assert self.gen._weighted_score(dims) == 0

    def test_tier_strong(self):
        assert self.gen._tier(85) == "strong"

    def test_tier_good(self):
        assert self.gen._tier(65) == "good"

    def test_tier_moderate(self):
        assert self.gen._tier(50) == "moderate"

    def test_tier_weak(self):
        assert self.gen._tier(30) == "weak"
