from __future__ import annotations

from app.config import Settings
from app.models import Channel, Lead


def _area_text(lead: Lead) -> str:
    if lead.neighborhoods:
        return ", ".join(lead.neighborhoods)
    return lead.city


def _budget_text(lead: Lead) -> str:
    if lead.price_min and lead.price_max:
        return f"${lead.price_min:,}-${lead.price_max:,}"
    if lead.price_max:
        return f"up to ${lead.price_max:,}"
    if lead.price_min:
        return f"from ${lead.price_min:,}"
    return "your budget"


def render_sequence_message(
    lead: Lead,
    channel: Channel,
    step: int,
    settings: Settings,
) -> tuple[str | None, str]:
    area = _area_text(lead)
    budget = _budget_text(lead)
    property_type = lead.property_type or "home"

    if step == 0:
        subject = "Quick follow-up on your home search" if channel == Channel.email else None
        body = (
            f"Hi {lead.full_name}, this is {settings.advisor_name} from {settings.company_name}. "
            f"I help buyers find the right {property_type} in {area}, uncover savings opportunities, "
            f"and handle the full process from mortgage to movers. "
            f"You can book a quick call here: {settings.booking_link}"
        )
        return subject, body

    if step == 1:
        subject = "We can send 3 personalized homes in 1 day" if channel == Channel.email else None
        body = (
            f"Hi {lead.full_name}, if you're still looking in {area} around {budget}, "
            "we can send you 3 personalized homes within 1 day based on your goals, budget, and family needs. "
            f"Book here: {settings.booking_link}"
        )
        return subject, body

    if step == 2:
        subject = "Savings + full-service support" if channel == Channel.email else None
        body = (
            "Along with curated homes, we help clients identify exact savings opportunities, often in the "
            "$20k-$50k range depending on the deal, and coordinate the full ecosystem like mortgage, inspectors, "
            f"builders, and movers. If you want help, grab a time here: {settings.booking_link}"
        )
        return subject, body

    if step == 3:
        subject = "Last follow-up for now" if channel == Channel.email else None
        body = (
            f"Last quick follow-up, {lead.full_name}. If you'd like us to send personalized listings or help you "
            f"book a showing in {area}, reply here or use this link: {settings.booking_link}"
        )
        return subject, body

    return None, ""