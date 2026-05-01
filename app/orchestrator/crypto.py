from __future__ import annotations

import hmac
import math
import re
import time
from hashlib import sha256


def safe_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def verify_meta_signature(raw_body: bytes, app_secret: str, signature_header: str | None) -> bool:
    if not app_secret or not signature_header:
        return False

    signature_header = signature_header.strip()
    if not signature_header.startswith("sha256="):
        return False

    expected = signature_header.split("=", 1)[1]
    digest = hmac.new(app_secret.encode("utf-8"), raw_body, sha256).hexdigest()
    return safe_equals(digest, expected)


_RETELL_SIG_RE = re.compile(r"v=(\d+),d=(.*)")


def verify_retell_signature(raw_body_text: str, api_key: str, signature_header: str | None) -> bool:
    if not api_key or not signature_header:
        return False

    match = _RETELL_SIG_RE.fullmatch(signature_header.strip())
    if not match:
        return False

    timestamp_ms_str, digest_hex = match.group(1), match.group(2)
    try:
        timestamp_ms = int(timestamp_ms_str)
    except ValueError:
        return False

    now_ms = int(time.time() * 1000)
    if math.fabs(now_ms - timestamp_ms) > 5 * 60 * 1000:
        return False

    mac = hmac.new(api_key.encode("utf-8"), digestmod=sha256)
    mac.update((raw_body_text + timestamp_ms_str).encode("utf-8"))
    expected_hex = mac.hexdigest()
    return safe_equals(expected_hex, digest_hex)

