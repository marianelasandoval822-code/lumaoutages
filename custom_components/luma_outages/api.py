"""Clients and parsers for the outage and generation data sources.

* LUMA's own (undocumented) Mi LUMA regional endpoint.
* hayluzpr.com, a third-party site that republishes LUMA's generation and
  town-level outage data.

This module deliberately has no Home Assistant imports so the parsers can be
tested on their own.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

API_URL = (
    "https://api.miluma.lumapr.com/miluma-outage-api/outage/regionsWithoutService"
)
GENERATION_URL = "https://hayluzpr.com/api/luma-generation"
TOWNS_URL = "https://hayluzpr.com/api/luma-town-outages"

PR_TZ = ZoneInfo("America/Puerto_Rico")
TOTAL_KEY = "__total__"

# The LUMA endpoint only answers requests that look like they come from a phone
# or the Mi LUMA web app. These are the defaults; anything the user puts in the
# "custom headers" option is merged on top and wins. They are NOT sent to
# hayluzpr.com.
DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-PR,es;q=0.9,en;q=0.8",
    "Origin": "https://miluma.lumapr.com",
    "Referer": "https://miluma.lumapr.com/",
}

# hayluzpr.com needs no device emulation; identify ourselves plainly.
HAYLUZ_HEADERS: dict[str, str] = {
    "User-Agent": "HomeAssistant-luma_outages/0.2.0",
    "Accept": "application/json",
}


class LumaApiError(Exception):
    """Any failure talking to a data source."""


class LumaApiBlockedError(LumaApiError):
    """The server refused the request (HTTP 401/403/429 or a non-JSON challenge page)."""


class LumaApiFormatError(LumaApiError):
    """The response was JSON but not in the expected shape."""


def slugify(name: str) -> str:
    """'Mayagüez' -> 'mayaguez', 'San Juan' -> 'san_juan'."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "_".join(ascii_name.lower().replace("-", " ").split())


def parse_headers(text: str | None) -> dict[str, str]:
    """Parse the user's custom-headers JSON. Raises ValueError if it is invalid."""
    if not text or not text.strip():
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
    ):
        raise ValueError("headers must be a JSON object of string values")
    return parsed


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_FRACTION = re.compile(r"(\.\d{6})\d+")


def _parse_iso(value: Any) -> datetime | None:
    """Parse '2026-10-15T21:23:16.2035996+00:00' (7 fractional digits)."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(_FRACTION.sub(r"\1", value))
    except ValueError:
        return None


# ---------------------------------------------------------------- LUMA regions


@dataclass(frozen=True, slots=True)
class RegionData:
    """Outage numbers for one LUMA region (or the island-wide total)."""

    key: str
    name: str
    total_clients: int
    without_service: int
    with_service: int
    planned_outage: int
    load_shed: int
    percent_without: float
    percent_with: float

    @property
    def unplanned_outage(self) -> int:
        """Customers out for reasons other than planned work or load shed.

        Assumes planned-outage and load-shed customers are counted inside
        ``without_service`` (consistent with LUMA's portal).
        """
        return max(0, self.without_service - self.planned_outage - self.load_shed)


@dataclass(frozen=True, slots=True)
class LumaData:
    """One parsed snapshot of the regional endpoint."""

    regions: dict[str, RegionData]
    total: RegionData
    reported_at: datetime | None

    def get(self, key: str) -> RegionData | None:
        if key == TOTAL_KEY:
            return self.total
        return self.regions.get(key)


def _percent(value: Any, count: int, total: int) -> float:
    number = _num(value)
    if number is not None:
        return number
    return round(100 * count / total, 2) if total else 0.0


def _build(
    key: str, name: str, data: dict[str, Any], pct_without_key: str, pct_with_key: str
) -> RegionData:
    total = _int(data.get("totalClients"))
    without = _int(data.get("totalClientsWithoutService"))
    with_service = _int(data.get("totalClientsWithService", total - without))
    return RegionData(
        key=key,
        name=name,
        total_clients=total,
        without_service=without,
        with_service=with_service,
        planned_outage=_int(data.get("totalClientsAffectedByPlannedOutage")),
        load_shed=_int(data.get("totalClientsAffectedByLoadShed")),
        percent_without=_percent(data.get(pct_without_key), without, total),
        percent_with=_percent(data.get(pct_with_key), with_service, total),
    )


def parse_response(payload: Any) -> LumaData:
    """Turn the regionsWithoutService JSON into typed data."""
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("regions"), list)
        or not isinstance(payload.get("totals"), dict)
    ):
        raise LumaApiFormatError("Unexpected response shape from LUMA")

    regions: dict[str, RegionData] = {}
    for raw in payload["regions"]:
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        key = slugify(str(raw["name"]))
        regions[key] = _build(
            key,
            str(raw["name"]),
            raw,
            "percentageClientsWithoutService",
            "percentageClientsWithService",
        )
    if not regions:
        raise LumaApiFormatError("LUMA returned no regions")

    total = _build(
        TOTAL_KEY,
        "Puerto Rico",
        payload["totals"],
        "totalPercentageWithoutService",
        "totalPercentageWithService",
    )

    reported_at: datetime | None = None
    stamp = payload.get("timestamp")
    if isinstance(stamp, str):
        try:
            reported_at = datetime.strptime(stamp, "%m/%d/%Y %I:%M %p").replace(
                tzinfo=PR_TZ
            )
        except ValueError:
            reported_at = None

    return LumaData(regions=regions, total=total, reported_at=reported_at)


# ------------------------------------------------------------------ generation


@dataclass(frozen=True, slots=True)
class PlantData:
    """Output of one generation plant."""

    key: str
    label: str
    current_mw: float
    max_mw: float

    @property
    def percent_of_max(self) -> float:
        return round(100 * self.current_mw / self.max_mw, 1) if self.max_mw else 0.0


@dataclass(frozen=True, slots=True)
class GenerationData:
    """One parsed snapshot of the generation endpoint."""

    plants: dict[str, PlantData]
    total_current_mw: float
    total_max_mw: float
    fetched_at: datetime | None

    @property
    def total_percent_of_max(self) -> float:
        if not self.total_max_mw:
            return 0.0
        return round(100 * self.total_current_mw / self.total_max_mw, 1)


def parse_generation(payload: Any) -> GenerationData:
    """Parse hayluzpr.com/api/luma-generation."""
    if not isinstance(payload, dict) or not isinstance(payload.get("plants"), list):
        raise LumaApiFormatError("Unexpected generation response shape")

    plants: dict[str, PlantData] = {}
    for raw in payload["plants"]:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        key = str(raw["id"])
        plants[key] = PlantData(
            key=key,
            label=str(raw.get("label") or key),
            current_mw=_num(raw.get("currentMw")) or 0.0,
            max_mw=_num(raw.get("maxMw")) or 0.0,
        )
    if not plants:
        raise LumaApiFormatError("Generation response listed no plants")

    total_current = _num(payload.get("totalCurrentMw"))
    total_max = _num(payload.get("totalMaxMw"))
    return GenerationData(
        plants=plants,
        total_current_mw=(
            total_current
            if total_current is not None
            else sum(p.current_mw for p in plants.values())
        ),
        total_max_mw=(
            total_max
            if total_max is not None
            else sum(p.max_mw for p in plants.values())
        ),
        fetched_at=_parse_iso(payload.get("fetchedAt")),
    )


# ---------------------------------------------------------------------- towns


@dataclass(frozen=True, slots=True)
class TownOutage:
    """Zones in one town that LUMA lists as without service."""

    key: str
    name: str
    zones: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TownsData:
    """One parsed snapshot of the town-outage endpoint."""

    affected: dict[str, TownOutage]
    fetched_at: datetime | None

    @property
    def count(self) -> int:
        return len(self.affected)


def parse_towns(payload: Any) -> TownsData:
    """Parse hayluzpr.com/api/luma-town-outages."""
    if not isinstance(payload, dict) or not isinstance(payload.get("affected"), dict):
        raise LumaApiFormatError("Unexpected town-outage response shape")

    names: dict[str, str] = {}
    zones_by_town: dict[str, list[str]] = {}
    for town, zones in payload["affected"].items():
        if not isinstance(zones, list):
            continue
        key = slugify(str(town))
        bucket = zones_by_town.setdefault(key, [])
        names.setdefault(key, str(town))
        for zone in zones:
            text = str(zone).strip()
            if text and text not in bucket:
                bucket.append(text)

    affected = {
        key: TownOutage(key=key, name=names[key], zones=tuple(zones))
        for key, zones in zones_by_town.items()
        if zones
    }
    return TownsData(affected=affected, fetched_at=_parse_iso(payload.get("fetchedAt")))


# --------------------------------------------------------------------- clients


async def _get_json(
    session: aiohttp.ClientSession, url: str, headers: dict[str, str]
) -> Any:
    try:
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status in (401, 403, 429):
                raise LumaApiBlockedError(f"HTTP {resp.status}")
            if resp.status != 200:
                raise LumaApiError(f"HTTP {resp.status}")
            try:
                return await resp.json(content_type=None)
            except (ValueError, aiohttp.ClientError) as err:
                raise LumaApiBlockedError(
                    "non-JSON response (probably a bot-protection page)"
                ) from err
    except (aiohttp.ClientError, TimeoutError) as err:
        raise LumaApiError(f"Could not reach {url}: {err}") from err


class LumaClient:
    """Thin async client around LUMA's regional endpoint."""

    def __init__(
        self, session: aiohttp.ClientSession, extra_headers: dict[str, str] | None = None
    ) -> None:
        self._session = session
        self._headers = {**DEFAULT_HEADERS, **(extra_headers or {})}

    async def async_fetch(self) -> LumaData:
        return parse_response(await _get_json(self._session, API_URL, self._headers))


class HayluzClient:
    """Client for the hayluzpr.com generation and town-outage endpoints."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_fetch_generation(self) -> GenerationData:
        return parse_generation(
            await _get_json(self._session, GENERATION_URL, HAYLUZ_HEADERS)
        )

    async def async_fetch_towns(self) -> TownsData:
        return parse_towns(await _get_json(self._session, TOWNS_URL, HAYLUZ_HEADERS))
