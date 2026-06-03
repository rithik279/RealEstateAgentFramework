"""
POST /api/curate-homes
Lead magnet endpoint — receives buyer preferences from neighbourhood popup,
queries PropTX for matching listings, returns top 3, stores lead in DB.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, EmailStr

router = APIRouter()
log = logging.getLogger(__name__)


# ── Request / Response models ────────────────────────────────────────────────

class CurateRequest(BaseModel):
    neighbourhood: str
    city: str
    email: EmailStr
    first_name: str
    phone: Optional[str] = None
    beds: Optional[str] = None          # "3", "4", "5"
    type: Optional[str] = None          # detached, semi-detached, townhouse, condo
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    features: Optional[str] = None      # free-text "must-haves"
    timeline: Optional[str] = None      # asap, 1-3mo, 3-6mo, 6mo+


class ListingOut(BaseModel):
    address: str
    price: Optional[float] = None
    beds: Optional[int] = None
    baths: Optional[int] = None
    sqft: Optional[str] = None
    type: Optional[str] = None
    dom: Optional[int] = None
    highlight: Optional[str] = None


class CurateResponse(BaseModel):
    listings: list[ListingOut]
    message: str


# ── Neighbourhood → postal/city filter map ───────────────────────────────────

NEIGHBOURHOOD_CITY_MAP: dict[str, str] = {
    # Brampton
    "Northwood Park": "Brampton",
    "Castlemore": "Brampton",
    "Brampton East": "Brampton",
    "Mount Pleasant": "Brampton",
    "Rosedale Village": "Brampton",
    # Mississauga
    "Port Credit": "Mississauga",
    "Lorne Park": "Mississauga",
    "Erin Mills": "Mississauga",
    "Churchill Meadows": "Mississauga",
    # Oakville
    "Glen Abbey": "Oakville",
    "Bronte": "Oakville",
    # Vaughan
    "Woodbridge": "Vaughan",
    "Kleinburg": "Vaughan",
}

# For neighbourhoods that are districts within a city, we filter by the
# PublicRemarks or UnparsedAddress containing the neighbourhood name.
NEEDS_TEXT_FILTER = {
    "Northwood Park", "Castlemore", "Mount Pleasant", "Rosedale Village",
    "Brampton East", "Port Credit", "Lorne Park", "Glen Abbey",
    "Woodbridge", "Kleinburg",
}


# ── Route ────────────────────────────────────────────────────────────────────

@router.post("/api/curate-homes", response_model=CurateResponse)
async def curate_homes(req: CurateRequest, background_tasks: BackgroundTasks, request: Request):
    """
    1. Store lead in DB immediately (don't lose the contact).
    2. Query PropTX for matching listings.
    3. Return top 3 sorted by best match.
    4. Trigger follow-up SMS/email in background.
    """
    listings: list[ListingOut] = []

    # ── 1. Store lead ────────────────────────────────────────────────────────
    background_tasks.add_task(_store_lead, req, request)

    # ── 2. Query PropTX ──────────────────────────────────────────────────────
    try:
        from app.services.proptx import PropTXClient
        from app.config import settings
        import asyncio

        if not settings.proptx_token:
            raise ValueError("PROPTX_TOKEN not configured")

        city = NEIGHBOURHOOD_CITY_MAP.get(req.neighbourhood, req.city)

        # Parse beds
        beds_int: Optional[int] = None
        if req.beds and req.beds.rstrip("+").isdigit():
            beds_int = int(req.beds.rstrip("+"))

        # Map home type to PropTX PropertyType
        ptype_map = {
            "detached": "Residential Freehold",
            "semi-detached": "Residential Freehold",
            "townhouse": "Residential Freehold",
            "condo": "Residential Condo & Other",
        }
        property_types: Optional[list[str]] = None
        if req.type and req.type in ptype_map:
            property_types = [ptype_map[req.type]]

        client = PropTXClient(
            token=settings.proptx_token,
            base_url=settings.proptx_base_url,
        )

        # PropTXClient.search() is synchronous — run in threadpool
        raw = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.search(
                cities=[city],
                min_price=req.min_price,
                max_price=req.max_price,
                min_bedrooms=beds_int,
                property_types=property_types,
                transaction_type="For Sale",
                limit=20,
            )
        )

        # Filter by neighbourhood name in address if needed
        if req.neighbourhood in NEEDS_TEXT_FILTER:
            nbhd_lower = req.neighbourhood.lower()
            scored = []
            for l in raw:
                addr_lower = (l.address or "").lower()
                remarks_lower = (l.public_remarks or "").lower()
                score = 0
                if nbhd_lower in addr_lower:
                    score += 10
                if nbhd_lower in remarks_lower:
                    score += 5
                scored.append((score, l))
            # Sort: neighbourhood matches first, then all others
            scored.sort(key=lambda x: x[0], reverse=True)
            raw = [l for _, l in scored]

        # Take top 3
        for l in raw[:3]:
            highlight = _generate_highlight(l, req)
            listings.append(ListingOut(
                address=l.address or f"{req.neighbourhood}, {city}",
                price=l.list_price,
                beds=l.bedrooms,
                baths=l.bathrooms,
                sqft=l.living_area_range,
                type=l.property_sub_type,
                dom=l.days_on_market,
                highlight=highlight,
            ))

    except Exception as e:
        log.warning("PropTX query failed for curate-homes: %s", e)
        # Fall through — return empty listings, JS shows fallback message

    return CurateResponse(
        listings=listings,
        message=f"Found {len(listings)} homes matching your criteria in {req.neighbourhood}.",
    )


def _generate_highlight(listing, req: CurateRequest) -> str:
    """Generate a one-line buyer-focused highlight for the listing."""
    parts = []
    if listing.days_on_market is not None and listing.days_on_market <= 3:
        parts.append("New listing — just hit the market")
    elif listing.days_on_market is not None and listing.days_on_market >= 21:
        parts.append(f"Been listed {listing.days_on_market} days — motivated seller")
    if listing.bedrooms_below and listing.bedrooms_below > 0:
        parts.append(f"{listing.bedrooms_below}-bed basement suite")
    if listing.tax_annual:
        parts.append(f"Property tax ~${listing.tax_annual:,.0f}/yr")
    return " · ".join(parts) if parts else ""


async def _store_lead(req: CurateRequest, request: Request) -> None:
    """
    Persist lead to the database and trigger follow-up sequence.
    Runs in background so it doesn't delay the popup response.
    """
    try:
        from app.db import get_session
        from app.models import Lead
        from sqlalchemy import select
        from datetime import datetime, timezone

        source = f"lead-magnet:{req.neighbourhood.lower().replace(' ', '-')}"

        async with get_session() as session:
            # Check for existing lead by email
            result = await session.execute(
                select(Lead).where(Lead.email == req.email)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update preferences
                existing.phone = req.phone or existing.phone
                existing.name = req.first_name or existing.name
                existing.source = source
                existing.updated_at = datetime.now(timezone.utc)
                # Append neighbourhood preference to notes
                note = (
                    f"Lead magnet: {req.neighbourhood} | "
                    f"beds:{req.beds} type:{req.type} "
                    f"budget:{req.min_price}–{req.max_price} "
                    f"timeline:{req.timeline} features:{req.features}"
                )
                existing.notes = (existing.notes or "") + f"\n{note}"
                await session.commit()
                log.info("Updated existing lead %s from lead magnet", req.email)
            else:
                lead = Lead(
                    email=req.email,
                    name=req.first_name,
                    phone=req.phone or "",
                    source=source,
                    status="new",
                    notes=(
                        f"Lead magnet: {req.neighbourhood} | "
                        f"beds:{req.beds} type:{req.type} "
                        f"budget:{req.min_price}–{req.max_price} "
                        f"timeline:{req.timeline} features:{req.features}"
                    ),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(lead)
                await session.commit()
                log.info("New lead from lead magnet: %s (%s)", req.email, req.neighbourhood)

        # Trigger follow-up SMS/email (non-blocking, best-effort)
        await _send_followup(req)

    except Exception as e:
        log.error("Failed to store lead magnet lead: %s", e)


async def _send_followup(req: CurateRequest) -> None:
    """Send immediate follow-up to buyer (confirmation) and alert to Anu."""
    try:
        from app.services.channels import ChannelSender
        from app.config import settings

        sender = ChannelSender(settings)

        # Alert to Anu
        alert_msg = (
            f"🏡 New lead magnet submission!\n"
            f"Name: {req.first_name}\n"
            f"Email: {req.email}\n"
            f"Phone: {req.phone or 'not provided'}\n"
            f"Neighbourhood: {req.neighbourhood}\n"
            f"Budget: ${int(req.min_price or 0):,} – ${int(req.max_price or 0):,}\n"
            f"Beds: {req.beds or 'any'} | Type: {req.type or 'any'}\n"
            f"Timeline: {req.timeline or 'unknown'}\n"
            f"Features: {req.features or 'none'}"
        )
        owner_phone = getattr(settings, "owner_alert_phone", None)
        if owner_phone:
            await sender.send_sms(to=owner_phone, body=alert_msg)

    except Exception as e:
        log.warning("Lead magnet follow-up failed: %s", e)
