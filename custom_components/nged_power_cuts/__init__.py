"""The NGED Power Cuts integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NGEDApiClient
from .config_flow import radius_km
from .const import CONF_POSTCODE
from .coordinator import PowerCutsCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.SENSOR,
]

type NGEDPowerCutsConfigEntry = ConfigEntry[PowerCutsCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: NGEDPowerCutsConfigEntry
) -> bool:
    """Set up NGED Power Cuts from a config entry."""
    coordinator = PowerCutsCoordinator(
        hass,
        entry,
        NGEDApiClient(async_get_clientsession(hass)),
        entry.data[CONF_POSTCODE],
        entry.data[CONF_LATITUDE],
        entry.data[CONF_LONGITUDE],
        radius_km(entry),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: NGEDPowerCutsConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: NGEDPowerCutsConfigEntry
) -> None:
    """Reload when the radius changes."""
    await hass.config_entries.async_reload(entry.entry_id)
