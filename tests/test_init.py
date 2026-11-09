"""Setup, entity ids, actions and diagnostics."""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.lionel_controller.const import DOMAIN

from .conftest import ADDRESS, FakeBluetooth


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_unique_ids_unchanged(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth, entity_registry: er.EntityRegistry
) -> None:
    """Unique ids match 1.x, so existing entity ids and the card keep working."""
    await _setup(hass, config_entry)
    unique_ids = {
        e.unique_id for e in er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    }
    for key in (
        "throttle", "master_volume", "horn_volume", "bell_volume", "speech_volume", "engine_volume",
        "lights", "auto_reconnect", "connect", "disconnect", "stop", "forward", "reverse", "horn",
        "bell", "announcement_ready_to_roll", "announcement_penna_flyer", "connection", "status",
        "train_model", "direction", "diagnostics",
    ):
        assert f"{ADDRESS}_{key}" in unique_ids
    assert len(unique_ids) == 29
    assert hass.states.get("button.polar_express_announcement_hey_there") is not None


async def test_actions_target_trains(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth, device_registry
) -> None:
    """Actions go to every train by default, or to the chosen device."""
    await _setup(hass, config_entry)
    await hass.services.async_call(DOMAIN, "set_speed", {"speed": 25}, blocking=True)
    assert config_entry.runtime_data.state.speed == 25
    device = device_registry.async_get_device(identifiers={(DOMAIN, ADDRESS)})
    await hass.services.async_call(
        DOMAIN, "set_direction", {"direction": "reverse", "device_id": device.id}, blocking=True
    )
    assert config_entry.runtime_data.state.direction_forward is False
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "stop", {"device_id": "nope"}, blocking=True)


async def test_actions_without_trains(hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth) -> None:
    """With nothing loaded the actions say so."""
    await _setup(hass, config_entry)
    await hass.config_entries.async_unload(config_entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "horn", {}, blocking=True)


async def test_diagnostics(
    hass: HomeAssistant, hass_client, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """The diagnostics download describes the connection."""
    await _setup(hass, config_entry)
    diag = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)
    assert diag["train"]["connected"] is True
    assert diag["train"]["address"] == ADDRESS


async def test_horn_hold_switch_has_safety_stop(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """Horn sound switch sounds until turned off, and stops by itself after 10 s."""
    from datetime import timedelta

    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from homeassistant.util import dt as dt_util

    await _setup(hass, config_entry)
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.polar_express_horn_sound"}, blocking=True)
    assert hass.states.get("switch.polar_express_horn_sound").state == "on"
    assert fake_bt.client.write_gatt_char.await_args.args[1] == bytes([0x00, 0x48, 0x01])
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert hass.states.get("switch.polar_express_horn_sound").state == "off"
    assert fake_bt.client.write_gatt_char.await_args.args[1] == bytes([0x00, 0x48, 0x00])
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.polar_express_bell_ringing"}, blocking=True)
    assert hass.states.get("switch.polar_express_bell_ringing").state == "on"
