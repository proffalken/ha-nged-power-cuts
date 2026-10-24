"""Sensors: when your power should be back, and how many cuts are nearby."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
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
    coordinator = entry.runtime_data
    async_add_entities(
        [
            EstimatedRestorationSensor(coordinator, "estimated_restoration"),
            NearbyPowerCutsSensor(coordinator, "nearby_power_cuts"),
        ]
    )


class EstimatedRestorationSensor(NGEDPowerCutsEntity, SensorEntity):
    """NGED's estimate of when power at your postcode will be back.

    With more than one cut at your postcode, the latest estimate wins. Planned
    work without an estimate uses its planned end.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        times = [
            c.estimated_restoration or c.planned_end
            for c in self.coordinator.data.yours
        ]
        return max((t for t in times if t is not None), default=None)


class NearbyPowerCutsSensor(NGEDPowerCutsEntity, SensorEntity):
    """How many power cuts have started within the chosen radius of home."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "power cuts"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.nearby)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "radius_km": self.coordinator.radius_km,
            "power_cuts": [
                self.coordinator.describe(c, d) for c, d in self.coordinator.data.nearby
            ],
        }
