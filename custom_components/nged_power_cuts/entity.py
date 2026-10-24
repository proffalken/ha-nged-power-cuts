"""Shared base entity for NGED Power Cuts platforms."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, POWER_CUT_MAP_URL
from .coordinator import PowerCutsCoordinator


class NGEDPowerCutsEntity(CoordinatorEntity[PowerCutsCoordinator]):
    """Base entity: one device per home, unique IDs scoped to the entry."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: PowerCutsCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Power cuts {entry.title}",
            manufacturer="National Grid Electricity Distribution",
            model="Live power cuts",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=POWER_CUT_MAP_URL,
        )
