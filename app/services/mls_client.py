"""
PropTx / TRREB RESO Web API Client
====================================
Fetches and normalizes MLS listing data from TRREB's RESO Web API (OData).

Status: READY — awaiting PropTx RESO credentials.

To activate:
  1. Contact PropTx: support@proptx.ca / 416-443-8199
  2. Request RESO Web API access (need IDX/VOW/DLA agreements)
  3. Get: PROPTX_API_KEY or PROPTX_USER + PROPTX_PASSWORD
  4. Set env vars, restart app — all MLS features auto-activate

Architecture note:
  AI NEVER calls MLS API directly.
  AI calls listing_scorer.py / home_fit_report.py
  Those call this module's normalized internal functions.
  This module is the only place that touches PropTx.

RESO field reference: https://ddwiki.reso.org/display/DDW17/RESO+Data+Dictionary+1.7
PropTx RESO endpoint: https://query.ampre.ca/odata (typical for TRREB)
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode
import urllib.request
import urllib.error
import json

logger = logging.getLogger(__name__)

ListingDict = dict[str, Any]

# ---------------------------------------------------------------------------
# RESO field → internal field mappings
# TRREB/PropTx uses standard RESO Data Dictionary 1.7 field names.
# Reference: https://ddwiki.reso.org/display/DDW17/
# ---------------------------------------------------------------------------

RESO_FIELD_MAP = {
    # Identity
    "ListingKey":           "mls_number",
    "ListingId":            "mls_number_alt",
    "MlsStatus":            "status",

    # Price
    "ListPrice":            "list_price",
    "ClosePrice":           "sold_price",
    "OriginalListPrice":    "original_list_price",

    # Address
    "StreetNumber":         "_street_number",
    "StreetName":           "_street_name",
    "StreetSuffix":         "_street_suffix",
    "UnitNumber":           "_unit_number",
    "City":                 "city",
    "StateOrProvince":      "province",
    "PostalCode":           "postal_code",
    "CountyOrParish":       "county",

    # Property details
    "PropertyType":         "property_type",
    "PropertySubType":      "property_subtype",
    "BedroomsTotal":        "bedrooms",
    "BathroomsTotal":       "bathrooms",
    "BathroomsFullInteger": "bathrooms_full",
    "BathroomsHalfInteger": "bathrooms_half",
    "ParkingTotal":         "parking_spaces",
    "GarageSpaces":         "garage_spaces",
    "GarageYN":             "has_garage",
    "LivingArea":           "square_feet",
    "LotSizeArea":          "lot_size_sqft",
    "LotSizeUnits":         "_lot_size_units",
    "YearBuilt":            "year_built",
    "StoriesTotal":         "stories",

    # Interior
    "InteriorFeatures":     "interior_features",
    "BasementYN":           "has_basement",
    "Basement":             "_basement_raw",   # comma-sep features string
    "KitchenFeatures":      "kitchen_features",
    "Appliances":           "appliances",

    # Exterior / lot
    "ExteriorFeatures":     "exterior_features",
    "PoolFeatures":         "pool_features",
    "View":                 "view",

    # Community / location
    "CommunityFeatures":    "community_features",
    "SubdivisionName":      "neighbourhood",
    "ElementarySchool":     "elementary_school",
    "MiddleOrJuniorSchool": "middle_school",
    "HighSchool":           "high_school",

    # Dates
    "ListingContractDate":  "listed_date",
    "CloseDate":            "sold_date",
    "ExpirationDate":       "expiry_date",
    "PriceChangeTimestamp": "price_changed_date",

    # Agent/office
    "ListAgentFullName":    "list_agent_name",
    "ListOfficeName":       "list_office",

    # Media
    "Media":                "_media",

    # Taxes / fees
    "TaxAnnualAmount":      "property_tax_annual",
    "AssociationFee":       "condo_fee_monthly",
    "AssociationFeeFrequency": "_condo_fee_freq",
}

# Basement features that indicate separate entrance
BASEMENT_SEP_ENTRANCE_KEYWORDS = {
    "separate entrance", "sep entrance", "walk-out", "walkout",
    "walk out", "side entrance", "private entrance",
}

# Basement features that indicate a finished suite
BASEMENT_SUITE_KEYWORDS = {
    "apartment", "suite", "finished", "in-law", "inlaw", "in law",
    "second unit", "2nd unit", "accessory unit", "aru", "legal",
}

# Basement features that suggest legal permit
BASEMENT_LEGAL_KEYWORDS = {
    "legal", "permitted", "city approved", "registered",
}

# Kitchen condition keywords
KITCHEN_MODERN_KEYWORDS = {
    "renovated", "updated", "modern", "new", "gourmet", "chef",
    "stainless", "quartz", "granite", "custom cabinetry",
}
KITCHEN_DATED_KEYWORDS = {
    "original", "dated", "older", "functional", "basic",
}


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(float(str(v).replace(",", "").replace("$", "")))
    except (ValueError, TypeError):
        return None


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return None


def _keywords_match(text: str, keywords: set[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def _build_address(raw: dict) -> str:
    parts = [
        raw.get("_street_number", ""),
        raw.get("_street_name", ""),
        raw.get("_street_suffix", ""),
    ]
    street = " ".join(p for p in parts if p).strip()
    unit = raw.get("_unit_number", "")
    city = raw.get("city", "")
    prov = raw.get("province", "ON")
    postal = raw.get("postal_code", "")

    addr = street
    if unit:
        addr = f"{unit}-{addr}"
    if city:
        addr += f", {city}"
    if prov:
        addr += f", {prov}"
    if postal:
        addr += f" {postal}"
    return addr.strip(", ")


def _analyze_basement(basement_raw: str) -> dict[str, Any]:
    """Parse RESO Basement field string into structured flags."""
    if not basement_raw:
        return {
            "basement_separate_entrance": False,
            "basement_suite": False,
            "basement_legal": False,
            "basement_finished": False,
            "basement_type": "",
            "basement_notes": "",
        }
    text = basement_raw.lower()
    return {
        "basement_separate_entrance": _keywords_match(text, BASEMENT_SEP_ENTRANCE_KEYWORDS),
        "basement_suite": _keywords_match(text, BASEMENT_SUITE_KEYWORDS),
        "basement_legal": _keywords_match(text, BASEMENT_LEGAL_KEYWORDS),
        "basement_finished": "finished" in text or "completed" in text,
        "basement_type": basement_raw,
        "basement_notes": basement_raw,
    }


def _analyze_kitchen(kitchen_raw: str, description: str = "") -> dict[str, Any]:
    """Infer kitchen condition from RESO kitchen features + public remarks."""
    combined = f"{kitchen_raw} {description}".lower()
    if _keywords_match(combined, KITCHEN_MODERN_KEYWORDS):
        condition = "renovated"
    elif _keywords_match(combined, KITCHEN_DATED_KEYWORDS):
        condition = "dated"
    else:
        condition = "unknown"

    open_concept = any(k in combined for k in (
        "open concept", "open-concept", "great room", "open plan"
    ))

    return {
        "kitchen_condition": condition,
        "open_concept": open_concept,
        "kitchen_features": kitchen_raw,
    }


def normalize_reso_listing(raw: dict[str, Any]) -> ListingDict:
    """
    Convert raw RESO API response to internal ListingDict.
    Applies field mapping, basement analysis, kitchen inference.
    Preserves raw payload for debugging / compliance audit.
    """
    # Step 1: map RESO fields to internal names
    mapped: dict[str, Any] = {}
    for reso_field, internal_field in RESO_FIELD_MAP.items():
        if reso_field in raw:
            mapped[internal_field] = raw[reso_field]

    # Step 2: also pass through unmapped fields (don't lose data)
    for k, v in raw.items():
        if k not in RESO_FIELD_MAP and not k.startswith("@"):
            mapped.setdefault(f"raw_{k}", v)

    # Step 3: build structured address
    mapped["address"] = _build_address(mapped)

    # Step 4: parse types
    for int_field in ("list_price", "sold_price", "original_list_price",
                      "bedrooms", "bathrooms", "parking_spaces", "garage_spaces",
                      "square_feet", "year_built", "stories"):
        if int_field in mapped:
            mapped[int_field] = _to_int(mapped[int_field])

    for float_field in ("lot_size_sqft", "property_tax_annual", "condo_fee_monthly"):
        if float_field in mapped:
            mapped[float_field] = _to_float(mapped[float_field])

    # Step 5: normalize condo fee (if reported annually, convert to monthly)
    if mapped.get("condo_fee_monthly") and mapped.get("_condo_fee_freq", "").lower() == "annually":
        mapped["condo_fee_monthly"] = round(mapped["condo_fee_monthly"] / 12, 2)

    # Step 6: basement analysis
    basement_raw = mapped.get("_basement_raw", "")
    mapped.update(_analyze_basement(basement_raw))

    # Step 7: kitchen analysis
    kitchen_raw = mapped.get("kitchen_features", "")
    description = raw.get("PublicRemarks", "") or raw.get("Remarks", "")
    mapped.update(_analyze_kitchen(kitchen_raw, description))

    # Step 8: garage
    mapped["has_garage"] = bool(mapped.get("garage_spaces") or mapped.get("has_garage"))

    # Step 9: listing age (days on market)
    listed_date = mapped.get("listed_date", "")
    if listed_date:
        try:
            from datetime import date
            listed = date.fromisoformat(str(listed_date)[:10])
            mapped["days_on_market"] = (date.today() - listed).days
        except Exception:
            pass

    # Step 10: preserve raw for compliance audit
    mapped["_raw"] = raw

    return mapped


# ---------------------------------------------------------------------------
# PropTx RESO Web API client
# ---------------------------------------------------------------------------

@dataclass
class ResoClient:
    """
    PropTx / TRREB RESO Web API client.

    Supports two auth modes:
      - API key:  PROPTX_API_KEY
      - Basic:    PROPTX_USER + PROPTX_PASSWORD

    PropTx RESO base URL (typical): https://query.ampre.ca/odata
    Confirm exact URL from PropTx credentials email.
    """
    base_url: str
    api_key: str = ""
    user: str = ""
    password: str = ""
    timeout: int = 30
    _session_headers: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.api_key:
            self._session_headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.user and self.password:
            import base64
            creds = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
            self._session_headers["Authorization"] = f"Basic {creds}"
        self._session_headers["Accept"] = "application/json"
        self._session_headers["OData-Version"] = "4.0"

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        if params:
            url += "?" + urlencode(params)
        req = urllib.request.Request(url, headers=self._session_headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            raise RuntimeError(f"RESO API HTTP {e.code}: {body[:300]}") from e
        except Exception as e:
            raise RuntimeError(f"RESO API error: {e}") from e

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_listing(self, listing_key: str) -> ListingDict | None:
        """Fetch single listing by ListingKey (MLS number)."""
        try:
            data = self._get(f"Property('{listing_key}')")
            return normalize_reso_listing(data)
        except RuntimeError as e:
            if "404" in str(e):
                return None
            raise

    def search_listings(
        self,
        *,
        city: str = "Brampton",
        price_min: int | None = None,
        price_max: int | None = None,
        bedrooms_min: int | None = None,
        property_type: str | None = None,
        status: str = "Active",
        limit: int = 50,
        select_fields: list[str] | None = None,
    ) -> list[ListingDict]:
        """
        Search active listings with OData $filter.
        Returns list of normalized ListingDicts.
        """
        filters = [f"MlsStatus eq '{status}'"]
        if city:
            filters.append(f"City eq '{city}'")
        if price_min:
            filters.append(f"ListPrice ge {price_min}")
        if price_max:
            filters.append(f"ListPrice le {price_max}")
        if bedrooms_min:
            filters.append(f"BedroomsTotal ge {bedrooms_min}")
        if property_type:
            filters.append(f"PropertySubType eq '{property_type}'")

        params: dict[str, Any] = {
            "$filter": " and ".join(filters),
            "$top": min(limit, 200),  # RESO servers typically cap at 200
            "$orderby": "ListingContractDate desc",
        }
        if select_fields:
            params["$select"] = ",".join(select_fields)

        try:
            response = self._get("Property", params)
            raw_listings = response.get("value", [])
            return [normalize_reso_listing(r) for r in raw_listings]
        except RuntimeError as e:
            logger.error("search_listings failed: %s", e)
            return []

    def get_media(self, listing_key: str) -> list[dict]:
        """Fetch photo URLs for a listing."""
        try:
            params = {
                "$filter": f"ResourceRecordKey eq '{listing_key}'",
                "$select": "MediaURL,Order,MediaCategory",
                "$orderby": "Order asc",
            }
            response = self._get("Media", params)
            return response.get("value", [])
        except RuntimeError as e:
            logger.warning("get_media failed for %s: %s", listing_key, e)
            return []

    def get_metadata(self) -> dict:
        """Fetch RESO metadata — useful for field discovery."""
        return self._get("$metadata")


# ---------------------------------------------------------------------------
# Ingestion / sync pipeline
# ---------------------------------------------------------------------------

class ListingIngester:
    """
    Pulls listings from RESO API → normalizes → stores to Postgres.
    Designed for scheduled sync (delta updates every 15-30 min).
    """

    def __init__(self, client: ResoClient, db):
        self.client = client
        self.db = db  # asyncpg or psycopg2 connection pool

    def sync_active_listings(
        self,
        city: str = "Brampton",
        price_min: int = 500_000,
        price_max: int = 2_000_000,
    ) -> dict[str, int]:
        """
        Full sync of active listings for target area.
        Returns: {inserted, updated, skipped, errors}
        """
        logger.info("Starting listing sync: %s $%d-$%d", city, price_min, price_max)
        listings = self.client.search_listings(
            city=city,
            price_min=price_min,
            price_max=price_max,
            limit=200,
        )
        inserted = updated = skipped = errors = 0
        for listing in listings:
            try:
                result = self._upsert_listing(listing)
                if result == "inserted":
                    inserted += 1
                elif result == "updated":
                    updated += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error("Failed to upsert listing %s: %s",
                             listing.get("mls_number"), e)
                errors += 1

        logger.info("Sync complete: %d inserted, %d updated, %d skipped, %d errors",
                    inserted, updated, skipped, errors)
        return {"inserted": inserted, "updated": updated,
                "skipped": skipped, "errors": errors}

    def _upsert_listing(self, listing: ListingDict) -> str:
        """
        Upsert one listing to the `listings` table.
        Returns 'inserted' | 'updated' | 'skipped'.
        NOTE: DB write not wired yet — logs the listing for now.
        Wire to self.db when DB schema is ready (see db.py TODO).
        """
        mls_number = listing.get("mls_number")
        if not mls_number:
            return "skipped"

        # TODO: wire to DB when listings table created
        # For now: log what we'd store
        logger.debug("Would upsert: %s %s $%s",
                     mls_number,
                     listing.get("address", ""),
                     listing.get("list_price", ""))
        return "inserted"

    def sync_delta(self, since_timestamp: str) -> dict[str, int]:
        """
        Fetch only listings modified since timestamp.
        Use for 15-minute incremental sync after initial full sync.
        RESO timestamp format: '2024-01-15T14:30:00Z'
        """
        # TODO: implement delta sync using ModificationTimestamp filter
        # params["$filter"] += f" and ModificationTimestamp gt {since_timestamp}"
        logger.info("Delta sync from %s — not yet implemented", since_timestamp)
        return {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

    def remove_stale_listings(self, max_days_on_market: int = 120) -> int:
        """
        Mark listings as stale if they've been on market too long.
        RESO best practice: don't delete, just mark inactive.
        """
        # TODO: wire to DB
        logger.info("Stale listing check — not yet implemented")
        return 0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class MLSNotConfiguredError(Exception):
    """Raised when PropTx RESO credentials are not set."""


def create_reso_client() -> ResoClient:
    """
    Create RESO client from env vars.
    Raises MLSNotConfiguredError if credentials missing.

    Env vars (set in Render dashboard):
      PROPTX_BASE_URL      https://query.ampre.ca/odata  (confirm from PropTx)
      PROPTX_API_KEY       preferred auth method
      PROPTX_USER          fallback basic auth
      PROPTX_PASSWORD      fallback basic auth
    """
    base_url = os.getenv("PROPTX_BASE_URL", "")
    api_key = os.getenv("PROPTX_API_KEY", "")
    user = os.getenv("PROPTX_USER", "")
    password = os.getenv("PROPTX_PASSWORD", "")

    if not base_url:
        raise MLSNotConfiguredError(
            "Set PROPTX_BASE_URL env var. "
            "Contact PropTx (support@proptx.ca / 416-443-8199) for RESO API access. "
            "Typical URL: https://query.ampre.ca/odata"
        )
    if not api_key and not (user and password):
        raise MLSNotConfiguredError(
            "Set PROPTX_API_KEY or both PROPTX_USER + PROPTX_PASSWORD. "
            "Credentials provided after PropTx agreement approval."
        )
    return ResoClient(base_url=base_url, api_key=api_key, user=user, password=password)


# Backward-compatible alias (old code used create_mls_client)
create_mls_client = create_reso_client
MLSClient = ResoClient
