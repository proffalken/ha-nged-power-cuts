"""Diagnostics support for the NGED Power Cuts integration.

The home's postcode and location are redacted, along with the postcodes and
locations of the cuts near it, which would give the home away.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from . import NGEDPowerCutsConfigEntry
from .const import CONF_POSTCODE

_REDACT = {CONF_POSTCODE, CONF_LATITUDE, CONF_LONGITUDE, "postcodes"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NGEDPowerCutsConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "title": "**REDACTED**",
            "data": async_redact_data(dict(entry.data), _REDACT),
            "options": dict(entry.options),
        },
        "summary": {
            "total": data.total,
            "yours": len(data.yours),
            "nearby": len(data.nearby),
            "planned": len(data.planned),
        },
        "relevant": [
            async_redact_data(
                {k: v for k, v in c.as_dict().items() if k != "distance_km"},
                _REDACT,
            )
            for c in data.relevant
        ],
    }
