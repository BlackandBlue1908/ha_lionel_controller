"""Sensor platform for Lionel Train Controller."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            LionelStatusSensor(coordinator),
            LionelModelSensor(coordinator),
            LionelDirectionSensor(coordinator),
            LionelDiagnosticsSensor(coordinator),
        ]
    )


class LionelStatusSensor(LionelEntity, SensorEntity):
    """Last message exchanged with the train, as hex."""

    _attr_translation_key = "status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: LionelTrainCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "status")

    @property
    def native_value(self) -> str | None:
        """Return the last message."""
        return self.coordinator.stats.last_message_hex

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the tracked train state."""
        state = self.coordinator.state
        return {
            "speed": state.speed,
            "direction_forward": state.direction_forward,
            "lights_on": state.lights_on,
            "bell_on": state.bell_on,
            "horn_on": state.horn_on,
        }


class LionelModelSensor(LionelEntity, SensorEntity):
    """The train model chosen at setup (decides announcement names)."""

    _attr_translation_key = "train_model"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _requires_connection = False

    def __init__(self, coordinator: LionelTrainCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "train_model")
        self._attr_native_value = coordinator.train_model


class LionelDirectionSensor(LionelEntity, SensorEntity):
    """Direction of travel."""

    _attr_translation_key = "direction"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["forward", "reverse"]

    def __init__(self, coordinator: LionelTrainCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "direction")

    @property
    def native_value(self) -> str:
        """Return forward or reverse."""
        return "forward" if self.coordinator.state.direction_forward else "reverse"


class LionelDiagnosticsSensor(LionelEntity, SensorEntity):
    """OK / Disconnected / Error, with counters. Full detail is in Download diagnostics."""

    _attr_translation_key = "diagnostics"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ok", "disconnected", "error"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _requires_connection = False

    def __init__(self, coordinator: LionelTrainCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "diagnostics")

    @property
    def native_value(self) -> str:
        """Return the overall health."""
        if self.coordinator.connected:
            return "ok"
        if self.coordinator.stats.last_error:
            return "error"
        return "disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return counters and the last error."""
        stats = self.coordinator.stats
        return {
            "last_error": stats.last_error,
            "last_error_time": stats.last_error_time.isoformat() if stats.last_error_time else None,
            "connection_attempts": stats.connection_attempts,
            "successful_commands": stats.successful_commands,
            "failed_commands": stats.failed_commands,
            "connected": self.coordinator.connected,
            "auto_reconnect_enabled": self.coordinator.auto_reconnect,
        }
