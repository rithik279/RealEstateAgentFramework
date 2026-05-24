"""
TRREB DDF (Data Distribution Facility) MLS Client
==================================================
Fetches listing data from TRREB's DDF API for GTA/Brampton properties.

Status: SKELETON — awaiting TRREB DDF API credentials from human.

To activate:
  1. Log in to TRREB Member Portal: https://trreb.ca
  2. Apply for DDF access (free for members)
  3. Set TRREB_DDF_USER and TRREB_DDF_PASSWORD in .env
  4. Uncomment the real API calls below

DDF API documentation: http://ddfapi.rea.ca/
Standard: RETS (Real Estate Transaction Standard) or DDF REST v2

This client maps DDF fields to the listing dict format
expected by HomeFitReportGenerator (see LISTING_SCHEMA in home_fit_report.py).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


# Expected listing dict shape (matches HomeFitReportGenerator.LISTING_SCHEMA)
ListingDict = dict[str, Any]


@dataclass
class MLSClient:
    """
    TRREB DDF listing client.

    Set TRREB_DDF_USER and TRREB_DDF_PASSWORD env vars to activate.
    Raises MLSNotConfiguredError if credentials missing.
    """
    user: str
    password: str
    base_url: str = "http://ddfapi.rea.ca/rets/v1"

    def get_listing_by_mls(self, mls_number: str) -> ListingDict | None:
        """
        Fetch single listing by MLS number.
        Returns normalized dict or None if not found.
        """
        raise MLSNotConfiguredError(
            "TRREB DDF credentials not yet configured. "
            "See docs/DEPLOYMENT.md Step 9 for setup instructions."
        )

    def search_listings(
        self,
        *,
        price_min: int | None = None,
        price_max: int | None = None,
        bedrooms_min: int | None = None,
        city: str = "Brampton",
        property_type: str | None = None,
        limit: int = 20,
    ) -> list[ListingDict]:
        """
        Search listings by criteria.
        Returns list of normalized listing dicts.
        """
        raise MLSNotConfiguredError(
            "TRREB DDF credentials not yet configured. "
            "See docs/DEPLOYMENT.md Step 9 for setup instructions."
        )

    def _normalize_listing(self, raw: dict[str, Any]) -> ListingDict:
        """
        Map DDF/RETS field names to our internal listing dict format.

        DDF field reference (common fields):
          ListingKey / MLS_NUM → mls_number
          ListPrice → price
          BedroomsTotal → bedrooms
          BathroomsTotal → bathrooms
          ParkingTotal → parking_spaces
          StreetAddress + City + Province → address
          PropertySubType → property_type
          LivingArea → sqft
          YearBuilt → year_built
          CommunityFeatures → neighbourhood
          Basement → basement info
        """
        address_parts = [
            raw.get("StreetAddress", ""),
            raw.get("City", ""),
            raw.get("Province", "ON"),
        ]
        address = ", ".join(p for p in address_parts if p)

        # Basement analysis — DDF returns comma-separated feature strings
        basement_raw = (raw.get("Basement") or "").lower()
        basement_sep = any(k in basement_raw for k in (
            "separate entrance", "sep entrance", "walk-out", "walkout", "walk out"
        ))
        basement_suite = any(k in basement_raw for k in (
            "apartment", "suite", "finished", "in-law", "inlaw"
        ))

        return {
            "address": address,
            "mls_number": raw.get("ListingKey") or raw.get("MLS_NUM") or raw.get("MlsNum"),
            "price": _to_int(raw.get("ListPrice")),
            "bedrooms": _to_int(raw.get("BedroomsTotal") or raw.get("Bedrooms")),
            "bathrooms": _to_int(raw.get("BathroomsTotal") or raw.get("Bathrooms")),
            "parking_spaces": _to_int(raw.get("ParkingTotal") or raw.get("Parking")),
            "sqft": _to_int(raw.get("LivingArea") or raw.get("ApproxSquareFootage")),
            "year_built": _to_int(raw.get("YearBuilt")),
            "property_type": raw.get("PropertySubType") or raw.get("PropertyType"),
            "neighbourhood": raw.get("CommunityName") or raw.get("Community"),
            "basement_separate_entrance": basement_sep,
            "basement_suite": basement_suite,
            "in_law_suite": "in-law" in basement_raw or "inlaw" in basement_raw,
            "dual_master": False,  # DDF doesn't have this field; agent must assess
            "kitchen_score": None,  # Not in DDF; agent or AI assessment
            "kitchen_notes": raw.get("KitchenFeatures") or "",
            "basement_notes": raw.get("Basement") or "",
            "layout_notes": raw.get("InteriorFeatures") or "",
            "raw_ddf": raw,  # preserve original for debugging
        }


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return None


class MLSNotConfiguredError(Exception):
    """Raised when TRREB DDF credentials are not set."""


def create_mls_client() -> MLSClient:
    """
    Create MLS client from env vars.
    Raises MLSNotConfiguredError if credentials missing.
    """
    user = os.getenv("TRREB_DDF_USER", "")
    password = os.getenv("TRREB_DDF_PASSWORD", "")
    if not user or not password:
        raise MLSNotConfiguredError(
            "Set TRREB_DDF_USER and TRREB_DDF_PASSWORD environment variables. "
            "Apply for DDF access at https://trreb.ca (free for TRREB members)."
        )
    return MLSClient(user=user, password=password)
