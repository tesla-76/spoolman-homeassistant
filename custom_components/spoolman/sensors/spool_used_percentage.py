"""Sensor class: SpoolUsedPercentage."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import (
    CONF_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

ICON = "mdi:printer-3d-nozzle"

class SpoolUsedPercentage(CoordinatorEntity, SensorEntity):
    """Sensor for spool used percentage."""

    def __init__(
        self, hass, coordinator, spool_data, config_entry
    ) -> None:
        """Initialize the used percentage sensor."""
        super().__init__(coordinator)

        self.config = hass.data[DOMAIN]
        self._spool = spool_data
        self.spool_id = spool_data['id']
        self._entry = config_entry
        self._attr_available = True

        # Display name is resolved via translation_key (see strings.json / translations/*.json).

        self.entity_id = generate_entity_id(
            "sensor.{}",
            f"spoolman_spool_{spool_data['id']}_used_percentage",
            hass=hass
        )
        self._attr_unique_id = f"spoolman_{self._entry.entry_id}_spool_{spool_data['id']}_used_percentage"
        self._attr_has_entity_name = True
        self._attr_translation_key = "used_percentage"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%"
        self._attr_icon = "mdi:percent"

        # Set device info to match spool device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.config[CONF_URL], f"spool_{self._spool['id']}")},
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        spool_data = next(
            (s for s in self.coordinator.data.get("spools", []) if s["id"] == self.spool_id),
            None
        )

        if spool_data is None:
            _LOGGER.warning(
                "SpoolManCoordinator: Spool with ID '%s' not found in coordinator data. Marking as unavailable.",
                self.spool_id,
            )
            self._attr_available = False
            self.async_write_ha_state()
            return

        self._attr_available = True
        self._spool = spool_data

        # Calculate used percentage
        filament = spool_data.get("filament", {})
        if filament.get("weight") and spool_data.get("used_weight") is not None:
            self._spool["used_percentage"] = round(
                (spool_data["used_weight"] / filament["weight"]) * 100, 1
            )
        else:
            self._spool["used_percentage"] = 0

        self.async_write_ha_state()

    @property
    def state(self):
        """Return the used percentage."""
        return self._spool.get("used_percentage", 0)

    async def async_update(self):
        """Fetch the latest data from the coordinator."""
        await self.coordinator.async_request_refresh()
