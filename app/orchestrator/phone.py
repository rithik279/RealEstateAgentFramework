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


# Soft opt-out phrases — not TCPA keywords but clear "don't contact me" intent
_SOFT_OPTOUT_FRAGMENTS = [
    "LEAVE ME ALONE",
    "DON'T TEXT ME", "DONT TEXT ME",
    "DON'T CONTACT", "DONT CONTACT", "DO NOT CONTACT",
    "NOT INTERESTED",
    "NO THANK YOU", "NO THANKS",
    "REMOVE ME",
    "PLEASE STOP",
    "STOP TEXTING", "STOP CALLING", "STOP MESSAGING",
    "FOUND A HOME", "FOUND A HOUSE", "ALREADY FOUND",
    "ALREADY BOUGHT", "ALREADY PURCHASED",
    "NOT LOOKING",
    "GO AWAY",
    "LEAVE ME",
    "DON'T WANT", "DONT WANT",
    "PLEASE DON'T", "PLEASE DONT",
    "DON'T NEED", "DONT NEED",
]


def is_soft_optout(body: str) -> bool:
    text = normalize_stop_intent(body)
    return any(fragment in text for fragment in _SOFT_OPTOUT_FRAGMENTS)

