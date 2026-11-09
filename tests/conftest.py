"""Fixtures for Lionel Train Controller tests."""
from __future__ import annotations

import time
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from habluetooth import BluetoothServiceInfoBleak
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lionel_controller.const import (
    CONF_MAC_ADDRESS,
    CONF_SERVICE_UUID,
    CONF_TRAIN_MODEL,
    DOMAIN,
    LIONCHIEF_SERVICE_UUID,
)

ADDRESS = "44:A6:E5:45:50:31"
COORD = "custom_components.lionel_controller.coordinator"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in every test."""


@pytest.fixture(autouse=True)
def _bluetooth(enable_bluetooth: None) -> None:
    """Start a mocked Bluetooth stack in every test."""


def service_info(
    name: str = "LC-0-1-0401-3150",
    address: str = ADDRESS,
    uuids: list[str] | None = None,
) -> BluetoothServiceInfoBleak:
    """Build an advertisement as Home Assistant's Bluetooth stack would."""
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-60,
        manufacturer_data={},
        service_data={},
        service_uuids=[LIONCHIEF_SERVICE_UUID] if uuids is None else uuids,
        source="local",
        device=BLEDevice(address, name, None),
        advertisement=None,
        connectable=True,
        time=time.monotonic(),
        tx_power=None,
    )


class FakeClient:
    """Stands in for a connected BleakClient."""

    def __init__(self, disconnected_callback: Any) -> None:
        self.is_connected = True
        self._disconnected_callback = disconnected_callback
        self.write_gatt_char = AsyncMock()
        self.start_notify = AsyncMock()
        self.read_gatt_char = AsyncMock(return_value=b"")
        self.services: list[Any] = []

    async def disconnect(self) -> None:
        self.drop()

    def drop(self) -> None:
        """Simulate the link going down."""
        if self.is_connected:
            self.is_connected = False
            self._disconnected_callback(self)


class FakeBluetooth:
    """Controls what the train looks like over Bluetooth during a test."""

    def __init__(self) -> None:
        self.visible = True
        self.fail_connect = False
        self.clients: list[FakeClient] = []

    async def establish_connection(self, client_class, device, name, disconnected_callback, **kwargs):
        if self.fail_connect:
            raise BleakError("connection refused")
        client = FakeClient(disconnected_callback)
        self.clients.append(client)
        return client

    def ble_device(self, hass, address, connectable=True):
        return BLEDevice(address, "LC-0-1-0401-3150", None) if self.visible else None

    @property
    def client(self) -> FakeClient:
        return self.clients[-1]


@pytest.fixture
def fake_bt() -> Generator[FakeBluetooth]:
    """Patch the coordinator's Bluetooth access."""
    fake = FakeBluetooth()
    with (
        patch(f"{COORD}.establish_connection", new=lambda *a, **k: fake.establish_connection(*a, **k)),
        patch(f"{COORD}.bluetooth.async_ble_device_from_address", new=lambda *a, **k: fake.ble_device(*a, **k)),
    ):
        yield fake


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured Polar Express."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="LC-0-1-0401-3150",
        unique_id=ADDRESS,
        data={
            CONF_MAC_ADDRESS: ADDRESS,
            "name": "Polar Express",
            CONF_SERVICE_UUID: LIONCHIEF_SERVICE_UUID,
            CONF_TRAIN_MODEL: "Polar Express",
        },
    )
