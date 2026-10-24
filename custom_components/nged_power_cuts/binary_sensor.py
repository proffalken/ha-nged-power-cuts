"""Binary sensor: is there a power cut at your postcode right now?"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NGEDPowerCutsConfigEntry
from .entity import NGEDPowerCutsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NGEDPowerCutsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([PowerCutBinarySensor(entry.runtime_data, "power_cut")])


class PowerCutBinarySensor(NGEDPowerCutsEntity, BinarySensorEntity):
    """On while NGED lists your postcode in a power cut that has started."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.yours)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "power_cuts": [
                self.coordinator.describe(c) for c in self.coordinator.data.yours
            ]
        }
