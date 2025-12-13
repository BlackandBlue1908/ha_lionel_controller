"""Button platform for Lionel Train Controller integration."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LionelTrainCoordinator
from .const import ANNOUNCEMENTS, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Lionel Train button platform."""
    coordinator: LionelTrainCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    name = config_entry.data[CONF_NAME]
    
    buttons = [
        LionelTrainConnectButton(coordinator, name),
        LionelTrainDisconnectButton(coordinator, name),
        LionelTrainStopButton(coordinator, name),
        LionelTrainForwardButton(coordinator, name),
        LionelTrainReverseButton(coordinator, name),
        LionelTrainHornButton(coordinator, name),
        LionelTrainBellButton(coordinator, name),
    ]
    
    # Add announcement buttons
    for announcement_name in ANNOUNCEMENTS:
        buttons.append(
            LionelTrainAnnouncementButton(coordinator, name, announcement_name)
        )
    
    async_add_entities(buttons, True)


class LionelTrainButtonBase(ButtonEntity):
    """Base class for Lionel Train buttons."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LionelTrainCoordinator, device_name: str) -> None:
        """Initialize the button."""
        self._coordinator = coordinator
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.mac_address)},
            "name": device_name,
            **coordinator.device_info,
        }

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        self._coordinator.register_callback(self._handle_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        self._coordinator.unregister_callback(self._handle_coordinator_update)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._coordinator.connected


class LionelTrainConnectButton(ButtonEntity):
    """Button for connecting to the train."""

    _attr_has_entity_name = True
    _attr_name = "Connect"
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, coordinator: LionelTrainCoordinator, device_name: str) -> None:
        """Initialize the connect button."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.mac_address}_connect"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.mac_address)},
            "name": device_name,
            **coordinator.device_info,
        }

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        self._coordinator.register_callback(self._handle_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed from hass."""
        self._coordinator.unregister_callback(self._handle_coordinator_update)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True if entity is available (always available for connect)."""
        return True

    async def async_press(self) -> None:
        """Press the button to connect."""
        await self._coordinator.async_force_reconnect()


class LionelTrainDisconnectButton(LionelTrainButtonBase):
    """Button for disconnecting from the train."""

    _attr_name = "Disconnect"
    _attr_icon = "mdi:bluetooth-off"

    def __init__(self, coordinator: LionelTrainCoordinator, device_name: str) -> None:
        """Initialize the disconnect button."""
        super().__init__(coordinator, device_name)
        self._attr_unique_id = f"{coordinator.mac_address}_disconnect"

    async def async_press(self) -> None:
        """Press the button."""
        await self._coordinator.async_disconnect()


class LionelTrainStopButton(LionelTrainButtonBase):
    """Button for stopping the train."""

    _attr_name = "Stop"
    _attr_icon = "mdi:stop"

    def __init__(self, coordinator: LionelTrainCoordinator, device_name: str) -> None:
        """Initialize the stop button."""
        super().__init__(coordinator, device_name)
        self._attr_unique_id = f"{coordinator.mac_address}_stop"

    async def async_press(self) -> None:
        """Press the button."""
        await self._coordinator.async_set_speed(0)


class LionelTrainForwardButton(LionelTrainButtonBase):
    """Button for setting forward direction."""

    _attr_name = "Forward"
    _attr_icon = "mdi:arrow-right"

    def __init__(self, coordinator: LionelTrainCoordinator, device_name: str) -> None:
        """Initialize the forward button."""
        super().__init__(coordinator, device_name)
        self._attr_unique_id = f"{coordinator.mac_address}_forward"

    async def async_press(self) -> None:
        """Press the button."""
        await self._coordinator.async_set_direction(True)


class LionelTrainReverseButton(LionelTrainButtonBase):
    """Button for setting reverse direction."""

    _attr_name = "Reverse"
    _attr_icon = "mdi:arrow-left"

    def __init__(self, coordinator: LionelTrainCoordinator, device_name: str) -> None:
        """Initialize the reverse button."""
        super().__init__(coordinator, device_name)
        self._attr_unique_id = f"{coordinator.mac_address}_reverse"

    async def async_press(self) -> None:
        """Press the button."""
        await self._coordinator.async_set_direction(False)


class LionelTrainHornButton(LionelTrainButtonBase):
    """Button for sounding the horn."""

    _attr_name = "Horn"
    _attr_icon = "mdi:bullhorn"

    def __init__(self, coordinator: LionelTrainCoordinator, device_name: str) -> None:
        """Initialize the horn button."""
        super().__init__(coordinator, device_name)
        self._attr_unique_id = f"{coordinator.mac_address}_horn"

    async def async_press(self) -> None:
        """Press the button to sound horn."""
        await self._coordinator.async_set_horn(True)


class LionelTrainBellButton(LionelTrainButtonBase):
    """Button for ringing the bell."""

    _attr_name = "Bell"
    _attr_icon = "mdi:bell"

    def __init__(self, coordinator: LionelTrainCoordinator, device_name: str) -> None:
        """Initialize the bell button."""
        super().__init__(coordinator, device_name)
        self._attr_unique_id = f"{coordinator.mac_address}_bell"

    async def async_press(self) -> None:
        """Press the button to ring bell."""
        await self._coordinator.async_set_bell(True)


class LionelTrainAnnouncementButton(LionelTrainButtonBase):
    """Button for playing announcements."""

    _attr_icon = "mdi:bullhorn-variant"

    def __init__(
        self, coordinator: LionelTrainCoordinator, device_name: str, announcement_name: str
    ) -> None:
        """Initialize the announcement button."""
        super().__init__(coordinator, device_name)
        self._announcement_name = announcement_name
        self._attr_name = f"Announcement {announcement_name}"
        self._attr_unique_id = f"{coordinator.mac_address}_announcement_{announcement_name.lower().replace(' ', '_')}"

    async def async_press(self) -> None:
        """Press the button."""
        announcement_config = ANNOUNCEMENTS[self._announcement_name]
        announcement_code = announcement_config["code"]
        await self._coordinator.async_play_announcement(announcement_code)
