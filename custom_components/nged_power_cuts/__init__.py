"""The NGED Power Cuts integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import NGEDApiClient
from .config_flow import radius_km
from .const import CONF_POSTCODE, DOMAIN
from .coordinator import PowerCutsCoordinator
from .dashboard import async_register_dashboard_strategy
from .places import PostcodesClient

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.SENSOR,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type NGEDPowerCutsConfigEntry = ConfigEntry[PowerCutsCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard strategy, once, however many entries there are."""
    await async_register_dashboard_strategy(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: NGEDPowerCutsConfigEntry
) -> bool:
    """Set up NGED Power Cuts from a config entry."""
    session = async_get_clientsession(hass)
    coordinator = PowerCutsCoordinator(
        hass,
        entry,
        NGEDApiClient(session),
        entry.data[CONF_POSTCODE],
        entry.data[CONF_LATITUDE],
        entry.data[CONF_LONGITUDE],
        radius_km(entry),
        places_client=PostcodesClient(session),
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
