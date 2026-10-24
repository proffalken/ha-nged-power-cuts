"""Data update coordinator for the NGED Power Cuts integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import NGEDApiClient, NGEDError
from .const import DOMAIN, EVENT_POWER_CUT_CHANGED, UPDATE_INTERVAL
from .models import PowerCut, PowerCutSummary, diff_cuts, summarise
from .places import (
    Place,
    PostcodesClient,
    PostcodesError,
    describe_places,
    postcode_sectors,
)

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
        *,
        places_client: PostcodesClient,
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
        self._places_client = places_client
        # Postcodes don't move, so each is looked up once.
        self._places: dict[str, Place | None] = {}

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
        await self._async_look_up_places(relevant.values())
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

    async def _async_look_up_places(self, cuts) -> None:
        missing = {pc for cut in cuts for pc in cut.postcodes} - self._places.keys()
        if not missing:
            return
        try:
            found = await self._places_client.async_lookup(sorted(missing))
        except PostcodesError as err:
            # Place names are a nicety; carry on without them and retry later.
            _LOGGER.debug("Couldn't look up place names: %s", err)
            return
        self._places.update({pc: found.get(pc) for pc in missing})

    def describe(
        self, cut: PowerCut, distance_km: float | None = None
    ) -> dict[str, Any]:
        """A cut's details plus the places and postcode sectors it covers."""
        places = [self._places.get(pc) for pc in sorted(cut.postcodes)]
        names = [p.name for p in places if p is not None]
        return {
            **cut.as_dict(distance_km),
            "places": sorted(set(names), key=lambda n: (-names.count(n), n)),
            "place_summary": describe_places(places),
            "postcode_sectors": postcode_sectors(cut.postcodes),
        }

    def _fire(self, change: str, cut: PowerCut) -> None:
        self.hass.bus.async_fire(
            EVENT_POWER_CUT_CHANGED,
            {
                "config_entry_id": self.config_entry.entry_id,
                "location": self.config_entry.title,
                "change": change,
                "affects_you": self.postcode in cut.postcodes,
                **self.describe(cut, cut.distance_km(self.latitude, self.longitude)),
            },
        )
