"""Switch platform for Lionel Train Controller."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import LionelConfigEntry, LionelTrainCoordinator
from .entity import LionelEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LionelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        [LionelLightsSwitch(coordinator), LionelAutoReconnectSwitch(coordinator)]
    )


class LionelLightsSwitch(LionelEntity, SwitchEntity):
    """The locomotive's headlight."""

    _attr_translation_key = "lights"

    def __init__(self, coordinator: LionelTrainCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "lights")

    @property
    def is_on(self) -> bool:
        """Return True if the lights are on."""
        return self.coordinator.state.lights_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the lights on."""
        await self.coordinator.async_set_lights(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the lights off."""
        await self.coordinator.async_set_lights(False)


class LionelAutoReconnectSwitch(LionelEntity, SwitchEntity, RestoreEntity):
    """Whether to connect automatically whenever the train is powered on."""

    _attr_translation_key = "auto_reconnect"
    _attr_entity_category = EntityCategory.CONFIG
    _requires_connection = False

    def __init__(self, coordinator: LionelTrainCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "auto_reconnect")

    async def async_added_to_hass(self) -> None:
        """Restore the user's choice across restarts."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) and last_state.state == STATE_OFF:
            self.coordinator.async_set_auto_reconnect(False)

    @property
    def is_on(self) -> bool:
        """Return True if auto-reconnect is on."""
        return self.coordinator.auto_reconnect

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable auto-reconnect."""
        self.coordinator.async_set_auto_reconnect(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable auto-reconnect."""
        self.coordinator.async_set_auto_reconnect(False)
