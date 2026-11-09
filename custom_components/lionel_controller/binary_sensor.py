"""Binary sensor platform for Lionel Train Controller."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LionelConfigEntry, LionelTrainCoordinator
from .entity import LionelEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LionelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the connection sensor."""
    async_add_entities([LionelConnectionSensor(entry.runtime_data)])


class LionelConnectionSensor(LionelEntity, BinarySensorEntity):
    """On while Home Assistant holds a Bluetooth connection to the train."""

    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _requires_connection = False

    def __init__(self, coordinator: LionelTrainCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "connection")

    @property
    def is_on(self) -> bool:
        """Return True if connected."""
        return self.coordinator.connected
