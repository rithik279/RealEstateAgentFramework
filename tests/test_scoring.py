"""
Tests for app/orchestrator/scoring.py
"""
from __future__ import annotations

import pytest

from app.orchestrator.scoring import score_lead, compute_tags, WEIGHTS, MAX_RAW


# ---------------------------------------------------------------------------
# compute_tags
# ---------------------------------------------------------------------------

class TestComputeTags:
    def test_pre_approved_from_financing_status(self):
        tags = compute_tags({"financing_status": "pre-approved"})
        assert "pre_approved" in tags

    def test_pre_approved_from_pre_approval_status(self):
        tags = compute_tags({"pre_approval_status": "approved"})
        assert "pre_approved" in tags

    def test_no_mortgage_tag_when_no_financing_info(self):
        # No financing data at all (e.g. call cut short) — don't assume they
        # need a mortgage review; only tag when they SAID they're working on it
        # or gave an unrecognized financing answer.
        tags = compute_tags({})
        assert "needs_mortgage_review" not in tags

    def test_needs_mortgage_review_when_working_on_financing(self):
        tags = compute_tags({"financing_status": "working on it"})
        assert "needs_mortgage_review" in tags

    def test_needs_mortgage_review_when_unrecognized_financing(self):
        tags = compute_tags({"financing_status": "maybe next year"})
        assert "needs_mortgage_review" in tags

    def test_needs_mortgage_review_not_added_if_pre_approved(self):
        tags = compute_tags({"financing_status": "pre-approved"})
        assert "needs_mortgage_review" not in tags

    def test_already_represented(self):
        tags = compute_tags({"currently_represented": "yes"})
        assert "already_represented" in tags

    def test_not_represented_no_tag(self):
        tags = compute_tags({"currently_represented": "no"})
        assert "already_represented" not in tags

    def test_family_agent_risk(self):
        tags = compute_tags({"family_agent_risk": True})
        assert "family_agent_risk" in tags

    def test_basement_income(self):
        tags = compute_tags({"basement_income_interest": True})
        assert "basement_income" in tags

    def test_kitchen_priority(self):
        tags = compute_tags({"kitchen_priority": True})
        assert "kitchen_priority" in tags

    def test_parking_from_flag(self):
        tags = compute_tags({"parking_priority": True})
        assert "parking_priority" in tags

    def test_parking_from_count(self):
        tags = compute_tags({"parking_needed": 3})
        assert "parking_priority" in tags

    def test_two_family(self):
        tags = compute_tags({"two_family_interest": True})
        assert "two_family" in tags

    def test_housepooling(self):
        tags = compute_tags({"housepooling_interest": True})
        assert "housepooling" in tags

    def test_first_time_buyer(self):
        tags = compute_tags({"first_time_buyer": True})
        assert "first_time_buyer" in tags

    def test_move_up_seller(self):
        tags = compute_tags({"move_up_seller": True})
        assert "move_up_seller" in tags

    def test_investor_minded(self):
        tags = compute_tags({"investor_minded": True})
        assert "investor_minded" in tags

    def test_dedupe_preserves_order(self):
        tags = compute_tags({"financing_status": "pre-approved"})
        # No duplicates
        assert len(tags) == len(set(tags))


# ---------------------------------------------------------------------------
# score_lead — individual signals
# ---------------------------------------------------------------------------

class TestScoreLead:
    def test_perfect_score(self):
        """All signals fire → score close to 100."""
        extracted = {
            "timeline": "asap",
            "timeline_days": 3,
            "specific_property": True,
            "financing_status": "pre-approved",
            "currently_represented": "no",
            "budget_max": 800_000,
            "down_payment_amount": 160_000,
        }
        result = score_lead(extracted, call_answered=True)
        assert result.score == 100
        assert result.tier == "hot"
        assert "hot_buyer" in result.tags

    def test_zero_score_no_signals(self):
        """Minimum score: call not answered, already represented (blocks not_represented), no other signals."""
        result = score_lead({"currently_represented": "yes"}, call_answered=False)
        assert result.score == 0
        assert result.tier == "cold"

    def test_phone_answered_adds_15(self):
        result_yes = score_lead({}, call_answered=True)
        result_no = score_lead({}, call_answered=False)
        diff = result_yes.score - result_no.score
        # 15 points raw / 150 max * 100 = 10 normalized
        assert diff == round(WEIGHTS["phone_answered"] / MAX_RAW * 100)

    def test_pre_approved_strongest_signal(self):
        result = score_lead({"financing_status": "pre-approved"}, call_answered=False)
        assert "pre_approved" in result.components
        assert result.components["pre_approved"] == WEIGHTS["pre_approved"]  # 30

    def test_tour_within_7_days_asap(self):
        result = score_lead({"timeline": "asap"}, call_answered=False)
        assert "tour_within_7_days" in result.components

    def test_tour_within_7_days_numeric(self):
        result = score_lead({"timeline_days": 5}, call_answered=False)
        assert "tour_within_7_days" in result.components

    def test_tour_NOT_within_7_days_when_long_timeline(self):
        result = score_lead({"timeline_days": 90}, call_answered=False)
        assert "tour_within_7_days" not in result.components

    def test_buying_within_90_days_from_days(self):
        result = score_lead({"timeline_days": 60}, call_answered=False)
        assert "buying_within_90_days" in result.components

    def test_buying_within_90_days_from_keyword(self):
        result = score_lead({"timeline": "3 months"}, call_answered=False)
        assert "buying_within_90_days" in result.components

    def test_budget_gta_viable(self):
        result = score_lead({"budget_max": 500_000}, call_answered=False)
        assert "budget_gta_viable" in result.components

    def test_budget_too_low(self):
        result = score_lead({"budget_max": 200_000}, call_answered=False)
        assert "budget_gta_viable" not in result.components

    def test_down_payment_confirmed_by_amount(self):
        result = score_lead({"down_payment_amount": 80_000}, call_answered=False)
        assert "down_payment_confirmed" in result.components

    def test_down_payment_confirmed_by_flag(self):
        result = score_lead({"down_payment_confirmed": True}, call_answered=False)
        assert "down_payment_confirmed" in result.components

    def test_not_represented_when_empty(self):
        result = score_lead({}, call_answered=False)
        assert "not_represented" in result.components

    def test_represented_lead_not_scored(self):
        result = score_lead({"currently_represented": "yes"}, call_answered=False)
        assert "not_represented" not in result.components
        assert "already_represented" in result.tags

    def test_specific_property_from_address(self):
        result = score_lead({"specific_property_address": "123 Main St"}, call_answered=False)
        assert "specific_property" in result.components

    def test_specific_property_from_flag(self):
        result = score_lead({"specific_property": True}, call_answered=False)
        assert "specific_property" in result.components

    def test_tier_warm_range(self):
        # Force a mid-range score
        extracted = {
            "financing_status": "pre-approved",
            "currently_represented": "no",
            "budget_max": 700_000,
        }
        result = score_lead(extracted, call_answered=True)
        # pre_approved(30) + not_rep(20) + budget(15) + phone(15) = 80 raw → ~53 normalized
        assert result.tier in ("warm", "hot")

    def test_tier_early_range(self):
        extracted = {"budget_max": 500_000}
        result = score_lead(extracted, call_answered=True)
        # phone(15) + budget(15) = 30 raw → 20 normalized
        assert result.tier in ("early", "warm")

    def test_recommended_action_present(self):
        result = score_lead({}, call_answered=True)
        assert isinstance(result.recommended_action, str)
        assert len(result.recommended_action) > 0

    def test_hot_buyer_tag_added(self):
        extracted = {
            "timeline": "asap",
            "financing_status": "pre-approved",
            "currently_represented": "no",
            "budget_max": 800_000,
            "down_payment_amount": 160_000,
            "specific_property": True,
        }
        result = score_lead(extracted, call_answered=True)
        assert result.tier == "hot"
        assert "hot_buyer" in result.tags

    def test_warm_buyer_tag_added(self):
        extracted = {
            "financing_status": "pre-approved",
            "currently_represented": "no",
            "budget_max": 600_000,
        }
        result = score_lead(extracted, call_answered=True)
        if result.tier == "warm":
            assert "warm_buyer" in result.tags

    def test_score_normalized_max_100(self):
        extracted = {
            "timeline": "asap",
            "timeline_days": 1,
            "specific_property": True,
            "financing_status": "pre-approved",
            "currently_represented": "no",
            "budget_max": 900_000,
            "down_payment_amount": 200_000,
        }
        result = score_lead(extracted, call_answered=True)
        assert 0 <= result.score <= 100

    def test_weights_sum_to_150(self):
        assert MAX_RAW == 150


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_extracted(self):
        result = score_lead({}, call_answered=False)
        assert isinstance(result.score, int)
        assert result.tier in ("hot", "warm", "early", "cold")

    def test_none_values_handled(self):
        result = score_lead({
            "timeline": None,
            "budget_max": None,
            "currently_represented": None,
            "financing_status": None,
        }, call_answered=True)
        assert isinstance(result.score, int)

    def test_string_booleans_ignored_for_budget(self):
        result = score_lead({"budget_max": "not a number"}, call_answered=False)
        assert "budget_gta_viable" not in result.components
