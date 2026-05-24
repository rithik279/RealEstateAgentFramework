"""Tests for app.services.listing_scorer"""

import pytest
from app.services.listing_scorer import (
    ListingScorer,
    _score_budget,
    _score_basement,
    _score_parking,
    _score_kitchen,
    _score_layout,
    _grade,
)

scorer = ListingScorer()


# ---------------------------------------------------------------------------
# Grade thresholds
# ---------------------------------------------------------------------------

def test_grade_a_plus():
    assert _grade(95) == "A+"

def test_grade_a():
    assert _grade(88) == "A"

def test_grade_b_plus():
    assert _grade(80) == "B+"

def test_grade_b():
    assert _grade(72) == "B"

def test_grade_c_plus():
    assert _grade(62) == "C+"

def test_grade_c():
    assert _grade(52) == "C"

def test_grade_d():
    assert _grade(45) == "D"


# ---------------------------------------------------------------------------
# Budget scoring
# ---------------------------------------------------------------------------

def test_budget_well_under():
    buyer = {"budget_max": 900_000}
    listing = {"list_price": 800_000}
    score, h, c = _score_budget(buyer, listing)
    assert score == 100.0
    assert any("under" in x.lower() for x in h)

def test_budget_within():
    buyer = {"budget_max": 900_000}
    listing = {"list_price": 890_000}
    score, h, c = _score_budget(buyer, listing)
    assert score == 85.0

def test_budget_slightly_over():
    buyer = {"budget_max": 900_000}
    listing = {"list_price": 930_000}
    score, h, c = _score_budget(buyer, listing)
    assert score == 60.0
    assert any("over" in x.lower() for x in c)

def test_budget_way_over():
    buyer = {"budget_max": 900_000}
    listing = {"list_price": 1_100_000}
    score, h, c = _score_budget(buyer, listing)
    assert score == 10.0

def test_budget_unknown():
    buyer = {}
    listing = {}
    score, h, c = _score_budget(buyer, listing)
    assert score == 50.0  # neutral when unknown


# ---------------------------------------------------------------------------
# Basement scoring
# ---------------------------------------------------------------------------

def test_basement_legal_suite_buyer_wants_income():
    buyer = {"basement_income_interest": True}
    listing = {"basement_separate_entrance": True, "basement_suite": True, "basement_legal": True}
    score, h, c = _score_basement(buyer, listing)
    assert score == 100.0
    assert any("legal" in x.lower() for x in h)

def test_basement_sep_entrance_no_suite_buyer_wants_income():
    buyer = {"basement_income_interest": True}
    listing = {"basement_separate_entrance": True, "basement_suite": False}
    score, h, c = _score_basement(buyer, listing)
    assert score == 60.0
    assert any("convert" in x.lower() or "entrance" in x.lower() for x in h)

def test_basement_no_entrance_buyer_wants_income():
    buyer = {"basement_income_interest": True}
    listing = {"basement_separate_entrance": False, "basement_suite": False}
    score, h, c = _score_basement(buyer, listing)
    assert score == 10.0
    assert len(c) > 0

def test_basement_buyer_doesnt_care_with_suite():
    buyer = {}
    listing = {"basement_separate_entrance": True, "basement_suite": True}
    score, h, c = _score_basement(buyer, listing)
    assert score == 85.0  # bonus but not required

def test_basement_buyer_doesnt_care_no_suite():
    buyer = {}
    listing = {}
    score, h, c = _score_basement(buyer, listing)
    assert score == 70.0


# ---------------------------------------------------------------------------
# Parking scoring
# ---------------------------------------------------------------------------

def test_parking_exceeds_need():
    buyer = {"parking_needed": 2}
    listing = {"parking_spaces": 4}
    score, h, c = _score_parking(buyer, listing)
    assert score == 100.0

def test_parking_exactly_meets():
    buyer = {"parking_needed": 2}
    listing = {"parking_spaces": 2}
    score, h, c = _score_parking(buyer, listing)
    assert score == 90.0

def test_parking_one_short():
    buyer = {"parking_needed": 2}
    listing = {"parking_spaces": 1}
    score, h, c = _score_parking(buyer, listing)
    assert score == 55.0
    assert any("short" in x.lower() or "parking" in x.lower() for x in c)

def test_parking_priority_penalty():
    buyer = {"parking_needed": 2, "parking_priority": True}
    listing = {"parking_spaces": 1}
    score, h, c = _score_parking(buyer, listing)
    assert score < 55.0  # extra penalty for priority

def test_parking_none_available():
    buyer = {"parking_needed": 2}
    listing = {"parking_spaces": 0}
    score, h, c = _score_parking(buyer, listing)
    assert score == 10.0

def test_parking_default_need_two():
    buyer = {}
    listing = {"parking_spaces": 2}
    score, h, c = _score_parking(buyer, listing)
    assert score == 90.0  # default need = 2, listing has 2


# ---------------------------------------------------------------------------
# Kitchen scoring
# ---------------------------------------------------------------------------

def test_kitchen_renovated():
    buyer = {}
    listing = {"kitchen_condition": "renovated"}
    score, h, c = _score_kitchen(buyer, listing)
    assert score >= 90.0

def test_kitchen_updated_year():
    buyer = {}
    listing = {"kitchen_year_updated": 2021}
    score, h, c = _score_kitchen(buyer, listing)
    assert score >= 85.0

def test_kitchen_dated_no_priority():
    buyer = {"kitchen_priority": False}
    listing = {"kitchen_condition": "dated"}
    score, h, c = _score_kitchen(buyer, listing)
    assert score == 50.0

def test_kitchen_dated_with_priority():
    buyer = {"kitchen_priority": True}
    listing = {"kitchen_condition": "dated"}
    score, h, c = _score_kitchen(buyer, listing)
    assert score < 50.0  # penalty when kitchen is priority

def test_kitchen_open_concept_bonus():
    buyer = {}
    listing = {"open_concept": True}
    score, h, c = _score_kitchen(buyer, listing)
    # 70 base + 10 open concept = 80
    assert score >= 78.0

def test_kitchen_closed_buyer_wants_open():
    buyer = {"open_concept_preferred": True}
    listing = {"open_concept": False}
    score, h, c = _score_kitchen(buyer, listing)
    assert any("closed" in x.lower() or "concept" in x.lower() for x in c)


# ---------------------------------------------------------------------------
# Layout scoring
# ---------------------------------------------------------------------------

def test_layout_exceeds_bedrooms():
    buyer = {"bedrooms_needed": 3, "family_size": 4}
    listing = {"bedrooms": 5, "square_feet": 2200}
    score, h, c = _score_layout(buyer, listing)
    assert score >= 90.0

def test_layout_matches_bedrooms():
    buyer = {"bedrooms_needed": 4}
    listing = {"bedrooms": 4}
    score, h, c = _score_layout(buyer, listing)
    assert score == 85.0

def test_layout_one_short():
    buyer = {"bedrooms_needed": 4}
    listing = {"bedrooms": 3}
    score, h, c = _score_layout(buyer, listing)
    assert score == 55.0

def test_layout_too_small_sqft():
    buyer = {"bedrooms_needed": 4, "family_size": 6}
    listing = {"bedrooms": 4, "square_feet": 1000}
    score, h, c = _score_layout(buyer, listing)
    # sqft_per_person = 1000/6 = 166 < 250 → penalty
    assert any("tight" in x.lower() for x in c)


# ---------------------------------------------------------------------------
# Full score integration
# ---------------------------------------------------------------------------

def test_perfect_match():
    buyer = {
        "budget_max": 900_000,
        "basement_income_interest": True,
        "parking_needed": 2,
        "kitchen_priority": False,
        "bedrooms_needed": 4,
        "family_size": 4,
    }
    listing = {
        "mls_number": "W12345",
        "address": "123 Test St, Brampton",
        "list_price": 850_000,
        "basement_separate_entrance": True,
        "basement_suite": True,
        "basement_legal": True,
        "parking_spaces": 3,
        "kitchen_condition": "renovated",
        "bedrooms": 5,
        "square_feet": 2400,
    }
    result = scorer.score(buyer, listing)
    assert result.total_score >= 90.0
    assert result.grade in ("A+", "A")

def test_poor_match():
    buyer = {
        "budget_max": 700_000,
        "basement_income_interest": True,
        "parking_needed": 3,
        "kitchen_priority": True,
        "bedrooms_needed": 4,
    }
    listing = {
        "mls_number": "W99999",
        "address": "999 Bad Fit Rd, Brampton",
        "list_price": 1_000_000,
        "basement_separate_entrance": False,
        "basement_suite": False,
        "parking_spaces": 1,
        "kitchen_condition": "original",
        "bedrooms": 2,
    }
    result = scorer.score(buyer, listing)
    assert result.total_score < 40.0
    assert result.grade == "D"

def test_rank_order():
    buyer = {"budget_max": 850_000, "basement_income_interest": True, "parking_needed": 2}
    listings = [
        {
            "mls_number": "A1",
            "list_price": 900_000,
            "basement_separate_entrance": False,
            "parking_spaces": 1,
        },
        {
            "mls_number": "A2",
            "list_price": 820_000,
            "basement_separate_entrance": True,
            "basement_suite": True,
            "basement_legal": True,
            "parking_spaces": 2,
        },
    ]
    ranked = scorer.rank(buyer, listings)
    assert ranked[0].mls_number == "A2"

def test_shortlist_filters_below_min():
    buyer = {"budget_max": 700_000}
    listings = [
        {"mls_number": "X1", "list_price": 1_200_000},
        {"mls_number": "X2", "list_price": 690_000},
    ]
    shortlist = scorer.shortlist(buyer, listings, min_score=60.0)
    mlses = [s.mls_number for s in shortlist]
    assert "X2" in mlses
    assert "X1" not in mlses

def test_as_dict_structure():
    buyer = {"budget_max": 850_000}
    listing = {"mls_number": "T1", "list_price": 800_000, "address": "1 Test"}
    result = scorer.score(buyer, listing)
    d = result.as_dict()
    assert "total_score" in d
    assert "grade" in d
    assert "dimensions" in d
    assert set(d["dimensions"].keys()) == {"budget", "basement", "parking", "kitchen", "layout"}
