"""The Lionel Train Controller integration."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

import voluptuous as vol

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import LionelConfigEntry, LionelTrainCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_URL = "/lionel_controller"

_TARGET = {vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string])}

SERVICES: dict[str, tuple[vol.Schema, Callable[[LionelTrainCoordinator, ServiceCall], Awaitable[None]]]] = {
    "set_speed": (
        vol.Schema({**_TARGET, vol.Required("speed"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100))}),
        lambda c, call: c.async_set_speed(call.data["speed"]),
    ),
    "set_direction": (
        vol.Schema({**_TARGET, vol.Required("direction"): vol.In(["forward", "reverse"])}),
        lambda c, call: c.async_set_direction(call.data["direction"] == "forward"),
    ),
    "stop": (vol.Schema(_TARGET), lambda c, call: c.async_set_speed(0)),
    "horn": (vol.Schema(_TARGET), lambda c, call: c.async_horn_blast()),
    "bell": (vol.Schema(_TARGET), lambda c, call: c.async_ring_bell()),
    "lights_on": (vol.Schema(_TARGET), lambda c, call: c.async_set_lights(True)),
    "lights_off": (vol.Schema(_TARGET), lambda c, call: c.async_set_lights(False)),
    "play_announcement": (
        vol.Schema({**_TARGET, vol.Required("announcement"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255))}),
        lambda c, call: c.async_play_announcement(call.data["announcement"]),
    ),
    "connect": (vol.Schema(_TARGET), lambda c, call: c.async_connect()),
    "disconnect": (vol.Schema(_TARGET), lambda c, call: c.async_disconnect()),
}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions and the card's static path once."""

    def _targets(call: ServiceCall) -> list[LionelTrainCoordinator]:
        loaded = {
            entry.entry_id: entry.runtime_data
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        }
        if not (device_ids := call.data.get(ATTR_DEVICE_ID)):
            if not loaded:
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_trains")
            return list(loaded.values())
        device_registry = dr.async_get(hass)
        targets: list[LionelTrainCoordinator] = []
        for device_id in device_ids:
            device = device_registry.async_get(device_id)
            matches = [loaded[eid] for eid in (device.config_entries if device else ()) if eid in loaded]
            if not matches:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="unknown_train",
                    translation_placeholders={"device_id": device_id},
                )
            targets.extend(matches)
        return targets

    def _make_handler(
        action: Callable[[LionelTrainCoordinator, ServiceCall], Awaitable[None]],
    ) -> Callable[[ServiceCall], Awaitable[None]]:
        async def handle(call: ServiceCall) -> None:
            for coordinator in _targets(call):
                await action(coordinator, call)

        return handle

    for name, (schema, action) in SERVICES.items():
        hass.services.async_register(DOMAIN, name, _make_handler(action), schema=schema)

    if hass.http is not None:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(Path(__file__).parent / "www"), False)]
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LionelConfigEntry) -> bool:
    """Set up one locomotive.

    Loads even while the train is off; it connects when it starts advertising.
    """
    coordinator = LionelTrainCoordinator(hass, entry)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LionelConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
    return unload_ok
