"""Calendar of planned power cuts at or near home."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import NGEDPowerCutsConfigEntry
from .entity import NGEDPowerCutsEntity
from .models import PowerCut

# Planned work with no end time is shown as lasting this long.
_DEFAULT_LENGTH = timedelta(hours=8)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NGEDPowerCutsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [PlannedPowerCutsCalendar(entry.runtime_data, "planned_power_cuts")]
    )


class PlannedPowerCutsCalendar(NGEDPowerCutsEntity, CalendarEntity):
    """Planned work at your postcode or within the chosen radius."""

    @property
    def event(self) -> CalendarEvent | None:
        """The planned cut happening now, or the next one."""
        now = dt_util.utcnow()
        events = sorted(self._events(), key=lambda e: e.start)
        return next((e for e in events if e.end > now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [e for e in self._events() if e.start < end_date and e.end > start_date]

    def _events(self) -> list[CalendarEvent]:
        return [
            event
            for cut in self.coordinator.data.planned
            if (event := self._event(cut)) is not None
        ]

    def _event(self, cut: PowerCut) -> CalendarEvent | None:
        start = cut.planned_start
        if start is None:
            return None
        end = cut.planned_end or cut.estimated_restoration or start + _DEFAULT_LENGTH
        if end <= start:
            end = start + _DEFAULT_LENGTH
        coordinator = self.coordinator
        where = (
            f"Your postcode ({coordinator.postcode})"
            if coordinator.postcode in cut.postcodes
            else f"Within {coordinator.radius_km:g} km of home"
        )
        lines = [
            where,
            f"NGED reference: {cut.id}",
            f"Postcodes: {', '.join(sorted(cut.postcodes))}",
        ]
        if cut.planned_reason:
            lines.append(f"Reason code: {cut.planned_reason}")
        return CalendarEvent(
            start=start,
            end=end,
            summary=f"Planned power cut ({cut.category or 'NGED'})",
            description="\n".join(lines),
            uid=cut.id,
        )
