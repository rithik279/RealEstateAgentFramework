"""
Risk Level Classifier — assigns risk tier to knowledge chunks.

Risk levels:
  low      — general market info, listing descriptions, neighbourhood data
  medium   — standard process guidance, forms, procedures (agent should verify)
  high     — compliance rules, RECO obligations, TRESA requirements (review before using)
  critical — legal advice territory, dual agency conflicts, offer strategy with liability
             (ALWAYS requires licensed professional review before acting)

Classifier uses keyword heuristics first (fast, no API cost).
Falls back to OpenAI classification for ambiguous chunks.

Usage:
    classifier = RiskClassifier()
    level = classifier.classify(chunk_body, heading=heading)
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Keyword-based heuristic classifier (no API cost)
# ---------------------------------------------------------------------------

# Patterns that suggest critical risk — legal liability, unauthorized practice
CRITICAL_PATTERNS = [
    r"\blegal advice\b",
    r"\bliability\b",
    r"\bdual agency\b",
    r"\bmultiple representation\b",
    r"\bconflict of interest\b",
    r"\bbreach of fiduciary\b",
    r"\bdiscrimination\b",
    r"\bhuman rights\b",
    r"\bfraud\b",
    r"\bmortgage fraud\b",
    r"\bcriminal\b",
    r"\bunauthorized practice\b",
]

# High risk — compliance rules, regulatory obligations
HIGH_PATTERNS = [
    r"\bRECO\b",
    r"\bTRESA\b",
    r"\bregistration requirement\b",
    r"\bcompliance\b",
    r"\bmust disclose\b",
    r"\brequired by law\b",
    r"\bprohibited\b",
    r"\bprofessional conduct\b",
    r"\bdisciplinary\b",
    r"\bfines?\b",
    r"\bsuspension\b",
    r"\brevocation\b",
    r"\bFSRA\b",
    r"\bmortgage brokerage\b",
    r"\badvertising rules?\b",
    r"\brepresentation agreement\b",
    r"\bbuyer representation\b",
    r"\bseller representation\b",
    r"\bconsent requirement\b",
    r"\bcode of ethics\b",
]

# Medium risk — standard process, forms, procedures
MEDIUM_PATTERNS = [
    r"\bAPS\b",
    r"\bagreement of purchase\b",
    r"\boffer\b",
    r"\bconditions?\b",
    r"\bdeposit\b",
    r"\bclosing\b",
    r"\btitle search\b",
    r"\bhome inspection\b",
    r"\bfinancing condition\b",
    r"\bpre-approval\b",
    r"\bmortgage\b",
    r"\bLand Transfer Tax\b",
    r"\bHSTh?\b",
    r"\brebate\b",
    r"\bfirst-time buyer\b",
]


def classify_chunk(body: str, heading: str | None = None) -> str:
    """
    Classify a text chunk into a risk level using keyword heuristics.
    Returns: 'low' | 'medium' | 'high' | 'critical'
    """
    text = ((heading or "") + " " + body).lower()

    for pattern in CRITICAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "critical"

    for pattern in HIGH_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "high"

    for pattern in MEDIUM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "medium"

    return "low"


def requires_professional_review(risk_level: str) -> bool:
    """High and critical chunks should be reviewed by licensed professional before use."""
    return risk_level in ("high", "critical")


class RiskClassifier:
    """Stateless classifier — wraps heuristic functions for use in pipeline."""

    def classify(self, body: str, heading: str | None = None) -> str:
        return classify_chunk(body, heading)

    def requires_review(self, risk_level: str) -> bool:
        return requires_professional_review(risk_level)
