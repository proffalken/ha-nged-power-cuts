"""Data update coordinator for the NGED Power Cuts integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import NGEDApiClient, NGEDError
from .const import DOMAIN, EVENT_POWER_CUT_CHANGED, UPDATE_INTERVAL
from .models import PowerCut, PowerCutSummary, diff_cuts, summarise

_LOGGER = logging.getLogger(__name__)


class PowerCutsCoordinator(DataUpdateCoordinator[PowerCutSummary]):
    """Polls the NGED feed and works out what it means for one home.

    Fires an event when a cut at or near home appears, changes, starts (for
    planned work) or is restored. Nothing is fired for the first poll, so a
    restart doesn't re-announce cuts that were already known.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: NGEDApiClient,
        postcode: str,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._client = client
        self.postcode = postcode
        self.latitude = latitude
        self.longitude = longitude
        self.radius_km = radius_km
        self._previous: dict[str, PowerCut] | None = None
        self._previous_started: set[str] = set()

    async def _async_update_data(self) -> PowerCutSummary:
        try:
            cuts = await self._client.async_get_power_cuts()
        except NGEDError as err:
            raise UpdateFailed(f"Error fetching NGED power cuts: {err}") from err

        summary = summarise(
            cuts,
            self.postcode,
            self.latitude,
            self.longitude,
            self.radius_km,
            dt_util.utcnow(),
        )
        relevant = {c.id: c for c in summary.relevant}
        started = {c.id for c in summary.yours} | {c.id for c, _ in summary.nearby}

        if self._previous is not None:
            changes = diff_cuts(self._previous, relevant)
            changed_ids = {cut.id for _, cut in changes}
            changes.extend(
                ("started", relevant[cut_id])
                for cut_id in started - self._previous_started
                if cut_id in self._previous and cut_id not in changed_ids
            )
            for change, cut in changes:
                self._fire(change, cut)

        self._previous = relevant
        self._previous_started = started
        return summary

    def _fire(self, change: str, cut: PowerCut) -> None:
        self.hass.bus.async_fire(
            EVENT_POWER_CUT_CHANGED,
            {
                "config_entry_id": self.config_entry.entry_id,
                "change": change,
                "affects_you": self.postcode in cut.postcodes,
                **cut.as_dict(cut.distance_km(self.latitude, self.longitude)),
            },
        )
