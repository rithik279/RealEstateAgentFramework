"""
Tests for app/services/nurture_sequences.py
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.services.nurture_sequences import (
    get_sequence,
    build_warm_sequence,
    build_early_sequence,
    build_cold_sequence,
    _first_name,
)

EXTRACTED_FULL = {
    "budget_max": 750_000,
    "preferred_areas": ["Brampton", "Mississauga"],
    "basement_income_interest": True,
    "first_time_buyer": True,
    "timeline": "3 months",
}

EXTRACTED_MINIMAL = {}

BOOKING_URL = "https://calendly.com/test-agent"


class TestFirstName:
    def test_extracts_first_name(self):
        assert _first_name("Harpreet Singh") == "Harpreet"

    def test_single_name(self):
        assert _first_name("John") == "John"

    def test_none_returns_there(self):
        assert _first_name(None) == "there"

    def test_empty_returns_there(self):
        assert _first_name("") == "there"

    def test_extra_whitespace(self):
        assert _first_name("  Jane  Doe  ") == "Jane"


class TestWarmSequence:
    def test_returns_three_messages(self):
        msgs = build_warm_sequence("lead-1", "Harpreet", EXTRACTED_FULL, BOOKING_URL)
        assert len(msgs) == 3

    def test_each_message_has_delay_and_body(self):
        msgs = build_warm_sequence("lead-1", "Harpreet", EXTRACTED_FULL, BOOKING_URL)
        for msg in msgs:
            assert "delay" in msg
            assert "body" in msg
            assert isinstance(msg["delay"], timedelta)
            assert len(msg["body"]) > 20

    def test_booking_url_in_last_message(self):
        msgs = build_warm_sequence("lead-1", "Harpreet", EXTRACTED_FULL, BOOKING_URL)
        assert BOOKING_URL in msgs[-1]["body"]

    def test_messages_have_increasing_delays(self):
        msgs = build_warm_sequence("lead-1", "Harpreet", EXTRACTED_FULL, BOOKING_URL)
        delays = [m["delay"].total_seconds() for m in msgs]
        assert delays == sorted(delays)

    def test_basement_mention_when_flagged(self):
        msgs = build_warm_sequence("lead-1", "Harpreet", EXTRACTED_FULL, BOOKING_URL)
        all_text = " ".join(m["body"] for m in msgs).lower()
        assert "income" in all_text or "suite" in all_text or "basement" in all_text

    def test_personalized_with_name(self):
        msgs = build_warm_sequence("lead-1", "Harpreet", EXTRACTED_FULL, BOOKING_URL)
        assert "Harpreet" in msgs[0]["body"]

    def test_stop_instruction_present(self):
        msgs = build_warm_sequence("lead-1", "Harpreet", EXTRACTED_FULL, BOOKING_URL)
        stop_in_any = any("STOP" in m["body"] for m in msgs)
        assert stop_in_any

    def test_works_with_minimal_extracted(self):
        msgs = build_warm_sequence("lead-1", None, EXTRACTED_MINIMAL, BOOKING_URL)
        assert len(msgs) == 3
        for msg in msgs:
            assert len(msg["body"]) > 10


class TestEarlySequence:
    def test_returns_four_messages(self):
        msgs = build_early_sequence("lead-1", "John", EXTRACTED_FULL, BOOKING_URL)
        assert len(msgs) == 4

    def test_delays_span_seven_days(self):
        msgs = build_early_sequence("lead-1", "John", EXTRACTED_FULL, BOOKING_URL)
        max_delay = max(m["delay"].total_seconds() for m in msgs)
        assert max_delay == timedelta(days=7).total_seconds()

    def test_first_time_buyer_mention(self):
        msgs = build_early_sequence("lead-1", "John", EXTRACTED_FULL, BOOKING_URL)
        all_text = " ".join(m["body"] for m in msgs)
        assert "first-time" in all_text.lower() or "LTT" in all_text or "rebate" in all_text

    def test_booking_url_present(self):
        msgs = build_early_sequence("lead-1", "John", EXTRACTED_FULL, BOOKING_URL)
        assert any(BOOKING_URL in m["body"] for m in msgs)

    def test_works_with_no_first_time_buyer(self):
        extracted = {**EXTRACTED_FULL, "first_time_buyer": False}
        msgs = build_early_sequence("lead-1", "John", extracted, BOOKING_URL)
        assert len(msgs) == 4


class TestColdSequence:
    def test_returns_two_messages(self):
        msgs = build_cold_sequence("lead-1", "Jane", {}, BOOKING_URL)
        assert len(msgs) == 2

    def test_delays_are_weekly(self):
        msgs = build_cold_sequence("lead-1", "Jane", {}, BOOKING_URL)
        assert msgs[0]["delay"] == timedelta(days=7)
        assert msgs[1]["delay"] == timedelta(days=14)

    def test_stop_present(self):
        msgs = build_cold_sequence("lead-1", "Jane", {}, BOOKING_URL)
        all_text = " ".join(m["body"] for m in msgs)
        assert "STOP" in all_text


class TestGetSequence:
    def test_warm_returns_three(self):
        msgs = get_sequence("warm", "lead-1", "Test", EXTRACTED_FULL, BOOKING_URL)
        assert len(msgs) == 3

    def test_early_returns_four(self):
        msgs = get_sequence("early", "lead-1", "Test", EXTRACTED_FULL, BOOKING_URL)
        assert len(msgs) == 4

    def test_cold_returns_two(self):
        msgs = get_sequence("cold", "lead-1", "Test", {}, BOOKING_URL)
        assert len(msgs) == 2

    def test_hot_returns_empty(self):
        # Hot buyers are handled immediately — no drip sequence
        msgs = get_sequence("hot", "lead-1", "Test", EXTRACTED_FULL, BOOKING_URL)
        assert msgs == []

    def test_unknown_tier_returns_empty(self):
        msgs = get_sequence("unknown", "lead-1", "Test", {}, BOOKING_URL)
        assert msgs == []
