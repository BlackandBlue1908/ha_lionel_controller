"""Switch platform for Lionel Train Controller."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
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
        [
            LionelLightsSwitch(coordinator),
            LionelAutoReconnectSwitch(coordinator),
            LionelHornSwitch(coordinator),
            LionelBellSwitch(coordinator),
        ]
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


# A held horn button in a dashboard sends on, then off. If the off never arrives
# (phone locked mid-press, lost connection), stop sounding after this long.
HORN_MAX_SECONDS = 10


class LionelHornSwitch(LionelEntity, SwitchEntity):
    """The horn sounds while this is on (for press-and-hold controls)."""

    _attr_translation_key = "horn_sound"

    def __init__(self, coordinator: LionelTrainCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "horn_sound")
        self._cancel_safety: CALLBACK_TYPE | None = None

    @property
    def is_on(self) -> bool:
        """Return True while the horn sounds."""
        return self.coordinator.state.horn_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the horn; it stops by itself after HORN_MAX_SECONDS."""
        await self.coordinator.async_set_horn(True)
        self._clear_safety()
        self._cancel_safety = async_call_later(self.hass, HORN_MAX_SECONDS, self._safety_off)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the horn."""
        self._clear_safety()
        await self.coordinator.async_set_horn(False)

    async def _safety_off(self, _now: datetime) -> None:
        self._cancel_safety = None
        if self.coordinator.state.horn_on and self.coordinator.connected:
            await self.coordinator.async_set_horn(False)

    @callback
    def _clear_safety(self) -> None:
        if self._cancel_safety is not None:
            self._cancel_safety()
            self._cancel_safety = None

    async def async_will_remove_from_hass(self) -> None:
        """Cancel the safety timer."""
        self._clear_safety()
        await super().async_will_remove_from_hass()


class LionelBellSwitch(LionelEntity, SwitchEntity):
    """The bell rings continuously while this is on."""

    _attr_translation_key = "bell_ringing"

    def __init__(self, coordinator: LionelTrainCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "bell_ringing")

    @property
    def is_on(self) -> bool:
        """Return True while the bell rings (the train reports this too)."""
        return self.coordinator.state.bell_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start ringing."""
        await self.coordinator.async_set_bell(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop ringing."""
        await self.coordinator.async_set_bell(False)
