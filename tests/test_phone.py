import pytest
from app.orchestrator.phone import (
    normalize_na_phone_to_e164,
    is_stop_message,
    is_start_message,
)


class TestNormalizePhone:
    def test_already_e164(self):
        assert normalize_na_phone_to_e164("+16475551234") == "+16475551234"

    def test_e164_11_digits(self):
        assert normalize_na_phone_to_e164("16475551234") == "+16475551234"

    def test_e164_10_digits(self):
        assert normalize_na_phone_to_e164("6475551234") == "+16475551234"

    def test_with_country_code_1(self):
        assert normalize_na_phone_to_e164("+1 647 555 1234") == "+16475551234"

    def test_with_dashes(self):
        assert normalize_na_phone_to_e164("647-555-1234") == "+16475551234"

    def test_with_brackets(self):
        assert normalize_na_phone_to_e164("(647) 555-1234") == "+16475551234"

    def test_none_input(self):
        assert normalize_na_phone_to_e164(None) is None

    def test_empty_input(self):
        assert normalize_na_phone_to_e164("") is None

    def test_invalid_too_short(self):
        assert normalize_na_phone_to_e164("12345") is None


class TestStopStart:
    def test_stop_uppercase(self):
        assert is_stop_message("STOP") is True

    def test_stop_lowercase(self):
        assert is_stop_message("stop") is True

    def test_stop_all(self):
        assert is_stop_message("STOPALL") is True

    def test_unsubscribe(self):
        assert is_stop_message("UNSUBSCRIBE") is True

    def test_cancel(self):
        assert is_stop_message("CANCEL") is True

    def test_quit(self):
        assert is_stop_message("QUIT") is True

    def test_end(self):
        assert is_stop_message("END") is True

    def test_stop_with_whitespace(self):
        assert is_stop_message("  STOP  ") is True

    def test_start_uppercase(self):
        assert is_start_message("START") is True

    def test_yes(self):
        assert is_start_message("YES") is True

    def test_unstop(self):
        assert is_start_message("UNSTOP") is True

    def test_not_stop(self):
        assert is_stop_message("HELLO") is False

    def test_not_start(self):
        assert is_start_message("MAYBE") is False
