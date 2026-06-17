"""
PropTX / Amplify Syndication MLS client.

RESO Web API (OData) against https://query.ampre.ca/odata

Key resources: Property
Key fields used: ListingKey, StandardStatus, ContractStatus, ListPrice,
  UnparsedAddress, City, PostalCode, PropertyType, PropertySubType,
  BedroomsTotal, BathroomsTotalInteger, ParkingTotal, LivingAreaRange,
  Basement, PublicRemarks, ModificationTimestamp, PhotosChangeTimestamp,
  Latitude, Longitude, GeoLocation
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field
from typing import Any

import httpx


PROPTX_BASE = "https://query.ampre.ca/odata"

# Fields we always select — minimal payload
_SELECT = ",".join([
    "ListingKey", "StandardStatus", "ContractStatus", "MlsStatus",
    "ListPrice", "UnparsedAddress", "StreetNumber", "StreetName",
    "StreetSuffix", "City", "StateOrProvince", "PostalCode",
    "PropertyType", "PropertySubType",
    "BedroomsTotal", "BedroomsAboveGrade", "BedroomsBelowGrade",
    "BathroomsTotalInteger",
    "ParkingTotal", "GarageType", "GarageYN",
    "LivingAreaRange", "LotSizeArea", "LotWidth", "LotDepth",
    "Basement", "KitchensTotal", "KitchensAboveGrade",
    "PublicRemarks", "TransactionType",
    "ModificationTimestamp", "OriginalEntryTimestamp",
    "Latitude", "Longitude",
    "PhotosChangeTimestamp", "DaysOnMarket",
    "AssociationFee", "TaxAnnualAmount",
    "ListAgentFullName", "ListOfficeName",
])


@dataclass
class PropTXListing:
    """Normalized listing — maps raw OData fields to app schema."""
    listing_key: str
    address: str
    city: str
    postal_code: str | None
    province: str | None
    property_type: str | None
    property_sub_type: str | None
    transaction_type: str | None       # For Sale / For Lease
    status: str | None                 # StandardStatus
    contract_status: str | None
    list_price: float | None
    bedrooms: int | None
    bedrooms_above: int | None
    bedrooms_below: int | None
    bathrooms: int | None
    parking_total: float | None
    garage: bool
    living_area_range: str | None
    lot_width: float | None
    lot_depth: float | None
    basement: list[str]
    kitchens: int | None
    public_remarks: str | None
    days_on_market: int | None
    association_fee: float | None
    tax_annual: float | None
    lat: float | None
    lng: float | None
    modification_ts: str | None
    agent_name: str | None
    office_name: str | None
    # Derived for HomeFitReport
    parking_spaces: int = 0
    basement_separate_entrance: bool = False
    basement_suite: bool = False

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "PropTXListing":
        basement_list: list[str] = raw.get("Basement") or []
        sep_entrance = any("sep" in b.lower() or "walk" in b.lower() or "entrance" in b.lower()
                           for b in basement_list if isinstance(b, str))
        suite = any("suite" in b.lower() or "apartment" in b.lower() or "finished" in b.lower()
                    for b in basement_list if isinstance(b, str))
        parking = raw.get("ParkingTotal") or 0
        try:
            parking_int = int(float(parking))
        except (TypeError, ValueError):
            parking_int = 0

        addr_parts = [
            raw.get("StreetNumber") or "",
            raw.get("StreetName") or "",
            raw.get("StreetSuffix") or "",
        ]
        address = raw.get("UnparsedAddress") or " ".join(p for p in addr_parts if p).strip()

        return cls(
            listing_key=raw.get("ListingKey", ""),
            address=address,
            city=raw.get("City") or "",
            postal_code=raw.get("PostalCode"),
            province=raw.get("StateOrProvince"),
            property_type=raw.get("PropertyType"),
            property_sub_type=raw.get("PropertySubType"),
            transaction_type=raw.get("TransactionType"),
            status=raw.get("StandardStatus") or raw.get("MlsStatus"),
            contract_status=raw.get("ContractStatus"),
            list_price=raw.get("ListPrice"),
            bedrooms=raw.get("BedroomsTotal"),
            bedrooms_above=raw.get("BedroomsAboveGrade"),
            bedrooms_below=raw.get("BedroomsBelowGrade"),
            bathrooms=raw.get("BathroomsTotalInteger"),
            parking_total=raw.get("ParkingTotal"),
            garage=bool(raw.get("GarageYN")),
            living_area_range=raw.get("LivingAreaRange"),
            lot_width=raw.get("LotWidth"),
            lot_depth=raw.get("LotDepth"),
            basement=basement_list,
            kitchens=raw.get("KitchensTotal") or raw.get("KitchensAboveGrade"),
            public_remarks=raw.get("PublicRemarks"),
            days_on_market=raw.get("DaysOnMarket"),
            association_fee=raw.get("AssociationFee"),
            tax_annual=raw.get("TaxAnnualAmount"),
            lat=raw.get("Latitude"),
            lng=raw.get("Longitude"),
            modification_ts=raw.get("ModificationTimestamp"),
            agent_name=raw.get("ListAgentFullName"),
            office_name=raw.get("ListOfficeName"),
            parking_spaces=parking_int,
            basement_separate_entrance=sep_entrance,
            basement_suite=suite,
        )

    def to_home_fit_dict(self) -> dict[str, Any]:
        """Convert to HomeFitReportGenerator listing schema."""
        return {
            "address": self.address,
            "mls_number": self.listing_key,
            "price": int(self.list_price) if self.list_price else None,
            "bedrooms": self.bedrooms,
            "bathrooms": self.bathrooms,
            "parking_spaces": self.parking_spaces,
            "basement_separate_entrance": self.basement_separate_entrance,
            "basement_suite": self.basement_suite,
            "in_law_suite": self.basement_separate_entrance and self.basement_suite,
            "dual_master": False,   # not in MLS data — agent must verify
            "kitchen_score": None,  # agent to assess
            "kitchen_notes": f"{self.kitchens or 1} kitchen(s)" if self.kitchens else "",
            "basement_notes": ", ".join(self.basement) if self.basement else "No basement info",
            "layout_notes": f"{self.bedrooms or '?'} bed / {self.bathrooms or '?'} bath — {self.living_area_range or 'sqft unknown'}",
            "sqft": None,
            "lot_size": f"{self.lot_width}x{self.lot_depth}" if self.lot_width and self.lot_depth else None,
            "property_type": self.property_sub_type or self.property_type,
            "neighbourhood": self.city,
            "days_on_market": self.days_on_market,
            "transaction_type": self.transaction_type,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_key": self.listing_key,
            "address": self.address,
            "city": self.city,
            "postal_code": self.postal_code,
            "property_type": self.property_sub_type or self.property_type,
            "transaction_type": self.transaction_type,
            "status": self.status,
            "list_price": self.list_price,
            "bedrooms": self.bedrooms,
            "bathrooms": self.bathrooms,
            "parking_total": self.parking_spaces,
            "garage": self.garage,
            "living_area_range": self.living_area_range,
            "basement": self.basement,
            "basement_separate_entrance": self.basement_separate_entrance,
            "basement_suite": self.basement_suite,
            "days_on_market": self.days_on_market,
            "association_fee": self.association_fee,
            "lat": self.lat,
            "lng": self.lng,
            "public_remarks": (self.public_remarks or "")[:500],
            "agent_name": self.agent_name,
            "modification_ts": self.modification_ts,
        }


class PropTXClient:
    def __init__(self, token: str, base_url: str = PROPTX_BASE, timeout: float = 20.0):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        base_url = f"{self.base_url}{path}"
        # OData requires literal $select, $filter etc — httpx would encode $ to %24
        # Build raw query string manually
        if params:
            _safe = "(),/:@!$'*+"
            qs = "&".join(f"{k}={urllib.parse.quote(v, safe=_safe)}" for k, v in params.items())
            url = f"{base_url}?{qs}"
        else:
            url = base_url
        resp = httpx.get(url, headers=self._headers(), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_listing(self, listing_key: str) -> PropTXListing | None:
        """Fetch single listing by ListingKey."""
        try:
            data = self._get(f"/Property('{listing_key}')", {"$select": _SELECT})
            return PropTXListing.from_raw(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def search(
        self,
        *,
        # Location
        cities: list[str] | None = None,
        postal_code: str | None = None,
        # Price
        min_price: float | None = None,
        max_price: float | None = None,
        # Bedrooms / bathrooms / parking
        min_bedrooms: int | None = None,
        min_bedrooms_above_grade: int | None = None,
        min_bathrooms: int | None = None,
        min_parking: int | None = None,
        garage: bool | None = None,
        # Property classification
        property_types: list[str] | None = None,
        property_sub_types: list[str] | None = None,
        transaction_type: str | None = None,   # "For Sale" | "For Lease"
        exclude_business_sale: bool = False,
        # Listing age / fees
        max_days_on_market: int | None = None,
        max_association_fee: float | None = None,
        min_association_fee: float | None = None,
        listed_after: str | None = None,       # ISO date "YYYY-MM-DD"
        # Status / pagination
        status: str = "Active",
        limit: int = 10,
        offset: int = 0,
    ) -> list[PropTXListing]:
        """Search active listings matching buyer criteria."""
        filters: list[str] = []

        # Status
        if status == "Active":
            filters.append("(ContractStatus eq 'Available' or StandardStatus eq 'Active')")
        elif status:
            filters.append(f"StandardStatus eq '{status}'")

        # Transaction type
        if transaction_type:
            filters.append(f"TransactionType eq '{transaction_type}'")

        # City filter — Toronto uses district codes (Toronto E05, Toronto W01, etc.)
        # Use startswith() for Toronto; eq for all other cities
        if cities:
            city_clauses = []
            for c in cities:
                if c.lower() == "toronto":
                    city_clauses.append("startswith(City,'Toronto')")
                else:
                    city_clauses.append(f"City eq '{c}'")
            filters.append(f"({' or '.join(city_clauses)})")

        if postal_code:
            filters.append(f"PostalCode eq '{postal_code}'")

        # Price range
        if min_price is not None:
            filters.append(f"ListPrice ge {min_price}")
        if max_price is not None:
            filters.append(f"ListPrice le {max_price}")

        # Bedrooms
        if min_bedrooms is not None:
            filters.append(f"BedroomsTotal ge {min_bedrooms}")
        if min_bedrooms_above_grade is not None:
            filters.append(f"BedroomsAboveGrade ge {min_bedrooms_above_grade}")

        # Bathrooms
        if min_bathrooms is not None:
            filters.append(f"BathroomsTotalInteger ge {min_bathrooms}")

        # Parking
        if min_parking is not None:
            filters.append(f"ParkingTotal ge {min_parking}")
        if garage is True:
            filters.append("GarageYN eq true")

        # Property type
        if property_types:
            type_clauses = " or ".join(f"PropertyType eq '{t}'" for t in property_types)
            filters.append(f"({type_clauses})")

        # Property sub-type — use startswith() to handle PropTx trailing spaces
        if property_sub_types:
            sub_clauses = " or ".join(f"startswith(PropertySubType,'{t}')" for t in property_sub_types)
            filters.append(f"({sub_clauses})")

        # Exclude "Sale Of Business" — startswith for trailing space safety
        if exclude_business_sale:
            filters.append("not startswith(PropertySubType,'Sale Of Business')")

        # Days on market
        if max_days_on_market is not None:
            filters.append(f"DaysOnMarket le {max_days_on_market}")

        # Association / condo fee
        if max_association_fee is not None:
            filters.append(f"AssociationFee le {max_association_fee}")
        if min_association_fee is not None:
            filters.append(f"AssociationFee ge {min_association_fee}")

        # Listing date
        if listed_after:
            filters.append(f"OriginalEntryTimestamp ge {listed_after}T00:00:00Z")

        filter_str = " and ".join(filters) if filters else "StandardStatus eq 'Active'"

        params = {
            "$select": _SELECT,
            "$filter": filter_str,
            "$orderby": "ModificationTimestamp desc,ListingKey desc",
            "$top": str(limit),
        }
        if offset:
            params["$skip"] = str(offset)

        try:
            data = self._get("/Property", params)
        except Exception as exc:
            raise RuntimeError(f"PropTx query failed. Filter: {filter_str} | Error: {exc}") from exc
        self._last_filter = filter_str
        # PropTx may include @odata.count in the response body (OData v4 standard)
        raw_count = data.get("@odata.count")
        self._last_total_count = int(raw_count) if raw_count is not None else None
        return [PropTXListing.from_raw(r) for r in data.get("value", [])]

    def count_results(self, filter_str: str) -> int | None:
        """Total count of results via /Property/$count — returns plain integer."""
        import urllib.parse as _up
        safe = "(),/:@!$'*+"
        qs = f"$filter={_up.quote(filter_str, safe=safe)}"
        url = f"{self.base_url}/Property/$count?{qs}"
        try:
            resp = httpx.get(url, headers=self._headers(), timeout=10.0)
            if resp.status_code == 200:
                return int(resp.text.strip())
        except Exception:
            pass
        return None

    def get_media(self, listing_key: str, limit: int = 3) -> list[dict[str, Any]]:
        """Fetch photo URLs for a listing from RESO Media resource."""
        params = {
            "$filter": f"ResourceRecordKey eq '{listing_key}'",
            "$select": "MediaURL,Order,MediaCategory",
            "$orderby": "Order asc",
            "$top": str(limit),
        }
        try:
            data = self._get("/Media", params)
            return data.get("value", [])
        except Exception:
            return []

    def search_for_buyer(self, buyer_profile: dict[str, Any], limit: int = 10) -> list[PropTXListing]:
        """Smart search using buyer profile from extracted_json."""
        # Derive search params from buyer profile
        budget_max = buyer_profile.get("budget_max") or buyer_profile.get("budget_min")
        budget_min = buyer_profile.get("budget_min")
        min_beds = buyer_profile.get("min_bedrooms") or buyer_profile.get("bedrooms_needed")

        # Area → cities mapping
        areas = buyer_profile.get("preferred_areas") or []
        area_str = buyer_profile.get("area") or ""
        cities = _areas_to_cities(areas, area_str)

        # Property type preference
        prop_types: list[str] | None = None
        if buyer_profile.get("property_type"):
            prop_types = [buyer_profile["property_type"]]

        return self.search(
            cities=cities or None,
            min_price=float(budget_min) * 0.8 if isinstance(budget_min, (int, float)) else None,
            max_price=float(budget_max) * 1.05 if isinstance(budget_max, (int, float)) else None,
            min_bedrooms=int(min_beds) if isinstance(min_beds, (int, float)) else None,
            property_types=prop_types,
            transaction_type="For Sale",
            limit=limit,
        )


def _areas_to_cities(areas: list[str], area_label: str) -> list[str]:
    """Map area labels / free-text areas to city names for OData filter."""
    gta_core = ["Toronto"]
    gta_suburbs = ["Mississauga", "Brampton", "Vaughan", "Markham", "Richmond Hill",
                   "Oakville", "Burlington", "Ajax", "Whitby", "Oshawa"]
    sw_ontario = ["Kitchener", "Waterloo", "Cambridge", "London", "Guelph"]

    cities: set[str] = set()

    # Try known area labels
    if "gta_core" in area_label:
        cities.update(gta_core)
    elif "gta_suburbs" in area_label:
        cities.update(gta_suburbs)
    elif "sw_ontario" in area_label:
        cities.update(sw_ontario)

    # Try free-text areas list
    for a in areas:
        if not isinstance(a, str):
            continue
        al = a.lower()
        if any(c.lower() in al for c in gta_core + gta_suburbs + sw_ontario):
            # Find closest match
            for c in gta_core + gta_suburbs + sw_ontario:
                if c.lower() in al or al in c.lower():
                    cities.add(c)

    return list(cities)
