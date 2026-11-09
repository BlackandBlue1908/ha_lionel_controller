"""Base entity for Lionel Train Controller."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import LionelTrainCoordinator


class LionelEntity(Entity):
    """An entity that belongs to one locomotive and follows its state."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    # Entities that make sense while the train is off (connect, settings) set this False.
    _requires_connection = True

    def __init__(self, coordinator: LionelTrainCoordinator, key: str) -> None:
        """Initialize the entity."""
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            name=coordinator.name,
            manufacturer="Lionel",
            model=(
                coordinator.train_model
                if coordinator.train_model != "Generic"
                else "LionChief locomotive"
            ),
        )

    async def async_added_to_hass(self) -> None:
        """Follow coordinator updates while the entity exists."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        """Controls are only available while connected."""
        return self.coordinator.connected if self._requires_connection else True
