"""
Deterministic area labeling from E.164 phone number.

Rules are hard-coded from CRTC area code assignments.
NO AI inference — area is null if area code is unrecognized.

Area labels:
  gta_core     — Toronto (416/647/437)
  gta_suburbs  — GTA suburbs: Brampton, Mississauga, Vaughan, Markham, Hamilton (905/289/365)
  sw_ontario   — Kitchener, London, Windsor, Woodstock (519/226/548)
  eastern_ont  — Ottawa, Kingston (613/343)
  central_ont  — Barrie, Peterborough, Sudbury (705/249)
  northern_ont — Thunder Bay, Sault Ste. Marie (807)
  out_of_province — non-Ontario Canadian area codes
  unknown      — unrecognized or non-Canadian number
"""
from __future__ import annotations

# Maps area code (str, 3 digits) -> area label
_AREA_CODE_MAP: dict[str, str] = {
    # GTA Core — Toronto
    "416": "gta_core",
    "647": "gta_core",
    "437": "gta_core",
    # GTA Suburbs — Brampton, Mississauga, Vaughan, Markham, Oakville, Hamilton, Oshawa
    "905": "gta_suburbs",
    "289": "gta_suburbs",
    "365": "gta_suburbs",
    # Southwestern Ontario — Kitchener, London, Windsor, Woodstock, Guelph, Cambridge
    "519": "sw_ontario",
    "226": "sw_ontario",
    "548": "sw_ontario",
    # Eastern Ontario — Ottawa, Kingston, Belleville
    "613": "eastern_ont",
    "343": "eastern_ont",
    # Central Ontario — Barrie, Peterborough, Sudbury, North Bay
    "705": "central_ont",
    "249": "central_ont",
    # Northern Ontario — Thunder Bay, Sault Ste. Marie, Timmins
    "807": "northern_ont",
    # Out of province — major Canadian area codes (non-Ontario)
    # BC
    "604": "out_of_province",
    "778": "out_of_province",
    "250": "out_of_province",
    "236": "out_of_province",
    "672": "out_of_province",
    # Alberta
    "403": "out_of_province",
    "587": "out_of_province",
    "780": "out_of_province",
    "825": "out_of_province",
    # Saskatchewan
    "306": "out_of_province",
    "639": "out_of_province",
    # Manitoba
    "204": "out_of_province",
    "431": "out_of_province",
    # Quebec
    "514": "out_of_province",
    "438": "out_of_province",
    "450": "out_of_province",
    "579": "out_of_province",
    "418": "out_of_province",
    "581": "out_of_province",
    "367": "out_of_province",
    "819": "out_of_province",
    "873": "out_of_province",
    # Nova Scotia / NB / PEI / NL
    "902": "out_of_province",
    "782": "out_of_province",
    "506": "out_of_province",
    "709": "out_of_province",
    # Northwest / Yukon / Nunavut
    "867": "out_of_province",
}

# Human-readable labels for messaging
AREA_LABELS: dict[str, str] = {
    "gta_core": "the GTA",
    "gta_suburbs": "the GTA",
    "sw_ontario": "the GTA or surrounding area",
    "eastern_ont": "Ontario",
    "central_ont": "Ontario",
    "northern_ont": "Ontario",
    "out_of_province": "the area",
    "unknown": "the area",
}


def label_from_e164(phone_e164: str | None) -> str | None:
    """
    Returns area label string or None if phone is null/unrecognized.
    Input must be E.164 format: +1XXXXXXXXXX for North America.
    """
    if not phone_e164:
        return None
    # Strip leading +1 for North American numbers
    digits = phone_e164.lstrip("+")
    if digits.startswith("1") and len(digits) == 11:
        area_code = digits[1:4]
        return _AREA_CODE_MAP.get(area_code, "unknown")
    # Non-NA number
    return "unknown"


def messaging_area(area: str | None) -> str:
    """Returns the human-readable area string for SMS/call scripts."""
    return AREA_LABELS.get(area or "unknown", "the area")
