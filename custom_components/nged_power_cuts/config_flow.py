"""Config and options flows for the NGED Power Cuts integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .api import NGEDApiClient, NGEDError
from .const import (
    CONF_POSTCODE,
    CONF_RADIUS_KM,
    DATASET_URL,
    DEFAULT_RADIUS_KM,
    DOMAIN,
)
from .models import normalise_postcode

_LOGGER = logging.getLogger(__name__)

_RADIUS = NumberSelector(
    NumberSelectorConfig(
        min=0, max=50, step=0.5, unit_of_measurement="km", mode=NumberSelectorMode.BOX
    )
)


def radius_km(entry: ConfigEntry) -> float:
    """The radius from options, falling back to the initial setup."""
    return entry.options.get(CONF_RADIUS_KM, entry.data[CONF_RADIUS_KM])


class NGEDPowerCutsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one home: its postcode, where it is, and how far is "nearby"."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            postcode = normalise_postcode(user_input[CONF_POSTCODE])
            if postcode is None:
                errors[CONF_POSTCODE] = "invalid_postcode"
            else:
                await self.async_set_unique_id(postcode)
                self._abort_if_unique_id_configured()
                try:
                    await NGEDApiClient(
                        async_get_clientsession(self.hass)
                    ).async_get_power_cuts()
                except NGEDError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error checking the NGED feed")
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(
                        title=postcode,
                        data={
                            CONF_POSTCODE: postcode,
                            CONF_LATITUDE: user_input[CONF_LATITUDE],
                            CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                            CONF_RADIUS_KM: user_input[CONF_RADIUS_KM],
                        },
                    )

        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_POSTCODE, default=defaults.get(CONF_POSTCODE, "")
                ): str,
                vol.Required(
                    CONF_LATITUDE,
                    default=defaults.get(CONF_LATITUDE, self.hass.config.latitude),
                ): cv.latitude,
                vol.Required(
                    CONF_LONGITUDE,
                    default=defaults.get(CONF_LONGITUDE, self.hass.config.longitude),
                ): cv.longitude,
                vol.Required(
                    CONF_RADIUS_KM,
                    default=defaults.get(CONF_RADIUS_KM, DEFAULT_RADIUS_KM),
                ): _RADIUS,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"dataset_url": DATASET_URL},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return NGEDPowerCutsOptionsFlow()


class NGEDPowerCutsOptionsFlow(OptionsFlow):
    """Change how far away a power cut counts as nearby."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_RADIUS_KM, default=radius_km(self.config_entry)
                ): _RADIUS,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
