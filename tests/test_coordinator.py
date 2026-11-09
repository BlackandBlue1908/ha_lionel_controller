"""Connection behaviour of the Lionel coordinator (regressions from 1.x)."""
from __future__ import annotations

import asyncio

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.lionel_controller.const import DOMAIN
from custom_components.lionel_controller.coordinator import (
    percent_to_speed_step,
    speed_step_to_percent,
)

from .conftest import FakeBluetooth


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("percent", "step"), [(0, 0), (1, 1), (3, 1), (50, 16), (100, 31), (150, 31)]
)
def test_speed_to_step(percent: int, step: int) -> None:
    """Small throttle settings still move the train; 1.x sent 0 for 1-3 %."""
    assert percent_to_speed_step(percent) == step


def test_step_to_speed() -> None:
    """Round trip stays close."""
    assert speed_step_to_percent(31) == 100
    assert speed_step_to_percent(16) == 52


async def test_connects_at_setup_when_visible(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """Setup starts a connection when the train is already advertising."""
    await _setup(hass, config_entry)
    assert config_entry.runtime_data.connected
    assert hass.states.get("binary_sensor.polar_express_connection").state == "on"
    assert hass.states.get("switch.polar_express_lights").state == "on"


async def test_loads_while_train_is_off(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """The entry loads without the train; controls are unavailable."""
    fake_bt.visible = False
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert not fake_bt.clients
    assert hass.states.get("number.polar_express_throttle").state == "unavailable"
    assert hass.states.get("button.polar_express_connect").state != "unavailable"


async def test_command_while_disconnected_does_not_hang(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """1.x deadlocked here: the send lock was held while connect took it again."""
    fake_bt.visible = False
    await _setup(hass, config_entry)
    fake_bt.visible = True
    coordinator = config_entry.runtime_data
    async with asyncio.timeout(5):
        await coordinator.async_set_speed(40)
    assert coordinator.connected
    fake_bt.client.write_gatt_char.assert_awaited_once()
    assert coordinator.state.speed == 40


async def test_drop_after_manual_connect_is_noticed(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """1.x's Connect button connected without a disconnect callback."""
    fake_bt.visible = False
    await _setup(hass, config_entry)
    fake_bt.visible = True
    coordinator = config_entry.runtime_data
    await coordinator.async_connect()
    assert coordinator.connected
    fake_bt.client.drop()
    await hass.async_block_till_done()
    assert not coordinator.connected
    assert hass.states.get("binary_sensor.polar_express_connection").state == "off"


async def test_stale_link_retries_once(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """A write on a dead link reconnects and sends again."""
    await _setup(hass, config_entry)
    first = fake_bt.client
    first.write_gatt_char.side_effect = asyncio.TimeoutError
    await config_entry.runtime_data.async_set_lights(False)
    assert len(fake_bt.clients) == 2
    fake_bt.client.write_gatt_char.assert_awaited_once()
    assert hass.states.get("switch.polar_express_lights").state == "off"


async def test_unreachable_train_raises(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """Commands fail loudly instead of returning False silently."""
    fake_bt.visible = False
    await _setup(hass, config_entry)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "set_speed", {"speed": 30}, blocking=True)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.polar_express_connect"}, blocking=True
        )
    assert config_entry.runtime_data.stats.last_error


async def test_unload_does_not_reconnect(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """1.x started a reconnect loop when unloading disconnected the train."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert not coordinator.connected
    coordinator._async_on_advertisement(None, None)  # noqa: SLF001 - late advert after unload
    await hass.async_block_till_done()
    assert len(fake_bt.clients) == 1


async def test_advertisement_reconnects_with_backoff(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """After a drop, the next advertisement reconnects; failures back off."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    fake_bt.client.drop()
    fake_bt.fail_connect = True
    coordinator._async_on_advertisement(None, None)  # noqa: SLF001
    await hass.async_block_till_done()
    assert not coordinator.connected
    attempts = coordinator.stats.connection_attempts
    fake_bt.fail_connect = False
    coordinator._async_on_advertisement(None, None)  # noqa: SLF001 - inside backoff window
    await hass.async_block_till_done()
    assert coordinator.stats.connection_attempts == attempts
    coordinator._next_attempt = 0  # noqa: SLF001 - backoff elapsed
    coordinator._async_on_advertisement(None, None)  # noqa: SLF001
    await hass.async_block_till_done()
    assert coordinator.connected


async def test_user_disconnect_sticks_until_connect(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """Disconnect releases the train; adverts don't grab it back until Connect."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    client = fake_bt.client
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.polar_express_disconnect"}, blocking=True
    )
    assert not coordinator.connected
    assert client.write_gatt_char.await_args.args[1] == bytes([0x00, 0x4B, 0x00, 0x00])
    coordinator._async_on_advertisement(None, None)  # noqa: SLF001
    await hass.async_block_till_done()
    assert len(fake_bt.clients) == 1
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.polar_express_connect"}, blocking=True
    )
    assert coordinator.connected


async def test_auto_reconnect_off(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """With auto reconnect off, adverts are ignored."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.polar_express_auto_reconnect"}, blocking=True
    )
    fake_bt.client.drop()
    coordinator._async_on_advertisement(None, None)  # noqa: SLF001
    await hass.async_block_till_done()
    assert not coordinator.connected


async def test_notification_updates_entities(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth
) -> None:
    """Status reports from the train reach the entities, lights included."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    coordinator._on_notification(None, bytearray([0x00, 0x81, 0x02, 31, 0x02, 0x03, 0x0C, 0x00]))  # noqa: SLF001
    await hass.async_block_till_done()
    assert hass.states.get("number.polar_express_throttle").state == "100"
    assert hass.states.get("sensor.polar_express_direction").state == "reverse"
    assert hass.states.get("switch.polar_express_lights").state == "off"


async def test_device_info_from_gatt(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_bt: FakeBluetooth, device_registry
) -> None:
    """Model and versions read from the train land on the device."""
    original = fake_bt.establish_connection

    async def connect(*args, **kwargs):
        client = await original(*args, **kwargs)
        client.read_gatt_char.side_effect = lambda uuid: {
            "00002a26-0000-1000-8000-00805f9b34fb": b"1.4\x00",
            "00002a25-0000-1000-8000-00805f9b34fb": b"SN123",
        }.get(uuid, b"")
        return client

    fake_bt.establish_connection = connect
    await _setup(hass, config_entry)
    device = device_registry.async_get_device(identifiers={("lionel_controller", config_entry.unique_id)})
    assert device.sw_version == "1.4"
    assert device.serial_number == "SN123"
    assert device.manufacturer == "Lionel"
