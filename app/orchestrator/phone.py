from __future__ import annotations

import re


def normalize_na_phone_to_e164(raw: str | None) -> str | None:
    if not raw:
        return None

    value = raw.strip()
    if not value:
        return None

    if value.startswith("+") and re.fullmatch(r"\+\d{10,15}", value):
        return value

    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    return None


def normalize_stop_intent(body: str) -> str:
    cleaned = re.sub(r"\s+", " ", (body or "").strip().upper())
    return cleaned


def is_stop_message(body: str) -> bool:
    text = normalize_stop_intent(body)
    return text in {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}


def is_start_message(body: str) -> bool:
    text = normalize_stop_intent(body)
    return text in {"START", "YES", "UNSTOP"}

