from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class MetaLeadDetails:
    meta_lead_id: str
    created_time: str | None
    form_id: str | None
    ad_id: str | None
    full_name: str | None
    email: str | None
    phone: str | None
    raw: dict


def _field_value(field_data: list[dict], key: str) -> str | None:
    for item in field_data:
        if item.get("name") != key:
            continue
        values = item.get("values")
        if isinstance(values, list) and values:
            value = values[0]
            if isinstance(value, str):
                return value
    return None


def fetch_meta_lead(access_token: str, lead_id: str, api_version: str = "v23.0") -> MetaLeadDetails:
    response = httpx.get(
        f"https://graph.facebook.com/{api_version}/{lead_id}",
        params={
            "access_token": access_token,
            "fields": "created_time,form_id,ad_id,field_data",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    field_data = payload.get("field_data") or []
    if not isinstance(field_data, list):
        field_data = []

    return MetaLeadDetails(
        meta_lead_id=lead_id,
        created_time=payload.get("created_time"),
        form_id=payload.get("form_id"),
        ad_id=payload.get("ad_id"),
        full_name=_field_value(field_data, "full_name") or _field_value(field_data, "name"),
        email=_field_value(field_data, "email"),
        phone=_field_value(field_data, "phone_number") or _field_value(field_data, "phone"),
        raw=payload,
    )

