"""Parse NGED power cut records and work out which ones matter to a home.

The feed's times are naive UK local times, so they are read as Europe/London.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")

_POSTCODE = re.compile(r"^([A-Z]{1,2}[0-9][A-Z0-9]?)([0-9][A-Z]{2})$")
_FINISHED = {"restored", "completed", "cancelled", "closed"}


def normalise_postcode(value: str | None) -> str | None:
    """Return a UK postcode in the standard "AB1 2CD" form, or None."""
    if not value:
        return None
    compact = re.sub(r"\s+", "", str(value)).upper()
    match = _POSTCODE.match(compact)
    return f"{match[1]} {match[2]}" if match else None


def parse_nged_time(value: Any) -> datetime | None:
    """Read a naive UK local time from the feed as an aware UTC datetime."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UK)
    return parsed.astimezone(UTC)


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except TypeError, ValueError:
        return None
    return result if math.isfinite(result) else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass(frozen=True, slots=True)
class PowerCut:
    """One power cut, planned or not, as NGED reports it."""

    id: str
    area: str | None
    status: str | None
    category: str | None
    planned: bool
    postcodes: frozenset[str]
    latitude: float | None
    longitude: float | None
    reported: datetime | None
    estimated_restoration: datetime | None
    restored: datetime | None
    planned_start: datetime | None
    planned_end: datetime | None
    planned_reason: str | None
    psr_customers: int | None
    customers_off: int | None
    last_updated: datetime | None
    raw: dict[str, Any] = field(compare=False, repr=False, hash=False)

    @property
    def active(self) -> bool:
        """Not yet restored or completed."""
        if self.restored is not None:
            return False
        return (self.status or "").strip().lower() not in _FINISHED

    def started(self, now: datetime) -> bool:
        """Whether the power is off now (planned work counts from its start)."""
        if not self.active:
            return False
        if self.planned and self.planned_start is not None:
            return self.planned_start <= now
        return True

    def finished_by(self, now: datetime) -> bool:
        """Whether planned work is over by its own planned end."""
        return self.planned_end is not None and self.planned_end <= now

    def distance_km(self, latitude: float, longitude: float) -> float | None:
        """Great-circle distance from a point to where NGED places the cut."""
        if self.latitude is None or self.longitude is None:
            return None
        lat1, lon1, lat2, lon2 = map(
            math.radians, (latitude, longitude, self.latitude, self.longitude)
        )
        a = (
            math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        )
        return 6371.0 * 2 * math.asin(math.sqrt(a))

    @property
    def signature(self) -> tuple:
        """The fields whose change is worth telling someone about."""
        return (
            self.status,
            self.category,
            self.estimated_restoration,
            self.restored,
            self.planned_start,
            self.planned_end,
            self.postcodes,
        )

    def as_dict(self, distance_km: float | None = None) -> dict[str, Any]:
        """A JSON-friendly summary for attributes, events and diagnostics."""
        info: dict[str, Any] = {
            "id": self.id,
            "area": self.area,
            "status": self.status,
            "category": self.category,
            "planned": self.planned,
            "reported": _iso(self.reported),
            "estimated_restoration": _iso(self.estimated_restoration),
            "planned_start": _iso(self.planned_start),
            "planned_end": _iso(self.planned_end),
            "psr_customers": self.psr_customers,
            "customers_off": self.customers_off,
            "postcodes": sorted(self.postcodes),
        }
        if distance_km is not None:
            info["distance_km"] = round(distance_km, 1)
        return info


def _parse_record(record: Any) -> PowerCut | None:
    if not isinstance(record, dict):
        return None
    fault_id = str(record.get("fault_id") or "").strip()
    if not fault_id:
        return None

    category = (record.get("category") or "").strip() or None
    planned_start = parse_nged_time(record.get("planned_outage_start_date"))
    planned = (
        str(record.get("planned", "")).strip().lower() == "true"
        or "PLANNED" in (category or "").upper()
        or planned_start is not None
    )
    postcodes = frozenset(
        pc
        for part in str(record.get("postcode") or "").split(",")
        if (pc := normalise_postcode(part))
    )
    return PowerCut(
        id=fault_id,
        area=record.get("licence_area") or None,
        status=record.get("status") or None,
        category=category,
        planned=planned,
        postcodes=postcodes,
        latitude=_float(record.get("location_latitude")),
        longitude=_float(record.get("location_longitude")),
        reported=parse_nged_time(record.get("date_of_reported_fault")),
        estimated_restoration=parse_nged_time(record.get("etr")),
        restored=parse_nged_time(record.get("date_of_restoration")),
        planned_start=planned_start,
        planned_end=parse_nged_time(record.get("planned_outage_end_date")),
        planned_reason=record.get("planned_outage_reason") or None,
        psr_customers=_int(record.get("number_of_psr_customers")),
        customers_off=_int(
            record.get("planned_outage_off" if planned else "confirmed_off")
        ),
        last_updated=parse_nged_time(record.get("last_updated")),
        raw=record,
    )


def parse_power_cuts(records: Iterable[Any]) -> list[PowerCut]:
    """Parse feed records, skipping anything without a fault ID."""
    return [cut for r in records if (cut := _parse_record(r)) is not None]


@dataclass(frozen=True, slots=True)
class PowerCutSummary:
    """What the feed means for one home."""

    yours: list[PowerCut]
    nearby: list[tuple[PowerCut, float]]
    planned: list[PowerCut]
    total: int

    @property
    def relevant(self) -> list[PowerCut]:
        """Every cut affecting the home or near it, planned or not."""
        seen: dict[str, PowerCut] = {}
        for cut in [*self.yours, *(c for c, _ in self.nearby), *self.planned]:
            seen.setdefault(cut.id, cut)
        return list(seen.values())


def summarise(
    cuts: Iterable[PowerCut],
    postcode: str,
    latitude: float,
    longitude: float,
    radius_km: float,
    now: datetime,
) -> PowerCutSummary:
    """Split the feed into your cuts, nearby cuts and planned work."""
    cuts = list(cuts)
    yours: list[PowerCut] = []
    nearby: list[tuple[PowerCut, float]] = []
    planned: list[PowerCut] = []

    for cut in cuts:
        if not cut.active:
            continue
        affects_you = postcode in cut.postcodes
        distance = cut.distance_km(latitude, longitude)
        close = distance is not None and distance <= radius_km

        # Planned work that overruns stays a power cut until NGED restores it.
        if cut.started(now):
            if affects_you:
                yours.append(cut)
            if close:
                nearby.append((cut, distance))
        if cut.planned and (affects_you or close) and not cut.finished_by(now):
            planned.append(cut)

    nearby.sort(key=lambda item: item[1])
    planned.sort(key=lambda c: c.planned_start or now)
    return PowerCutSummary(yours=yours, nearby=nearby, planned=planned, total=len(cuts))


def diff_cuts(
    before: dict[str, PowerCut], after: dict[str, PowerCut]
) -> list[tuple[str, PowerCut]]:
    """What changed between two polls: new, updated or restored cuts."""
    changes: list[tuple[str, PowerCut]] = []
    for cut_id, cut in after.items():
        old = before.get(cut_id)
        if old is None:
            changes.append(("new", cut))
        elif old.signature != cut.signature:
            changes.append(("updated", cut))
    changes.extend(
        ("restored", old) for cut_id, old in before.items() if cut_id not in after
    )
    return changes
