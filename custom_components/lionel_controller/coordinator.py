"""Connection and state management for a Lionel LionChief locomotive."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import logging
import time
from typing import Any

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import (
    CMD_BELL,
    CMD_DIRECTION,
    CMD_DISCONNECT,
    CMD_HORN,
    CMD_ANNOUNCEMENT,
    CMD_LIGHTS,
    CMD_MASTER_VOLUME,
    CMD_SOUND_VOLUME,
    CMD_SPEED,
    CONF_MAC_ADDRESS,
    CONF_TRAIN_MODEL,
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    DOMAIN,
    FIRMWARE_REVISION_CHAR_UUID,
    HARDWARE_REVISION_CHAR_UUID,
    MANUFACTURER_NAME_CHAR_UUID,
    MODEL_NUMBER_CHAR_UUID,
    NOTIFY_CHARACTERISTIC_UUID,
    SERIAL_NUMBER_CHAR_UUID,
    SOFTWARE_REVISION_CHAR_UUID,
    SOUND_SOURCE_BELL,
    SOUND_SOURCE_ENGINE,
    SOUND_SOURCE_HORN,
    SOUND_SOURCE_SPEECH,
    WRITE_CHARACTERISTIC_UUID,
    build_simple_command,
)

_LOGGER = logging.getLogger(__name__)

# The train speaks speed in 32 steps (0x00-0x1F); Home Assistant uses 0-100 %.
SPEED_STEPS = 31

# Backoff between automatic connection attempts, in seconds.
RECONNECT_BACKOFF = (5, 10, 20, 30, 60)

DEVICE_INFO_CHARS = {
    MODEL_NUMBER_CHAR_UUID: "model_number",
    SERIAL_NUMBER_CHAR_UUID: "serial_number",
    FIRMWARE_REVISION_CHAR_UUID: "firmware_revision",
    HARDWARE_REVISION_CHAR_UUID: "hardware_revision",
    SOFTWARE_REVISION_CHAR_UUID: "software_revision",
    MANUFACTURER_NAME_CHAR_UUID: "manufacturer_name",
}

PLACEHOLDER_VALUES = {
    "model number", "serial number", "firmware revision", "hardware revision",
    "software revision", "manufacturer name",
}

SOUND_SOURCES = {
    SOUND_SOURCE_HORN: "horn_volume",
    SOUND_SOURCE_BELL: "bell_volume",
    SOUND_SOURCE_SPEECH: "speech_volume",
    SOUND_SOURCE_ENGINE: "engine_volume",
}


def percent_to_speed_step(percent: int) -> int:
    """Convert 0-100 % to the train's 0-31 scale; any non-zero speed moves."""
    if percent <= 0:
        return 0
    return max(1, min(SPEED_STEPS, round(percent * SPEED_STEPS / 100)))


def speed_step_to_percent(step: int) -> int:
    """Convert the train's 0-31 scale to 0-100 %."""
    return max(0, min(100, round(step * 100 / SPEED_STEPS)))


@dataclass
class TrainState:
    """What we know about the locomotive."""

    speed: int = 0
    direction_forward: bool = True
    # LionChief locomotives power up with their lights on.
    lights_on: bool = True
    horn_on: bool = False
    bell_on: bool = False
    master_volume: int = 5
    horn_volume: int = 5
    bell_volume: int = 5
    speech_volume: int = 5
    engine_volume: int = 5


@dataclass
class TrainStats:
    """Connection and command counters for diagnostics."""

    connection_attempts: int = 0
    successful_commands: int = 0
    failed_commands: int = 0
    last_error: str | None = None
    last_error_time: datetime | None = None
    last_message_hex: str | None = None
    gatt_info: dict[str, str] = field(default_factory=dict)


type LionelConfigEntry = ConfigEntry[LionelTrainCoordinator]


class LionelTrainCoordinator:
    """Owns the Bluetooth connection to one locomotive."""

    def __init__(self, hass: HomeAssistant, entry: LionelConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.address: str = entry.data[CONF_MAC_ADDRESS].upper()
        self.name: str = entry.data.get(CONF_NAME) or entry.title
        self.train_model: str = entry.data.get(CONF_TRAIN_MODEL, "Generic")

        self.state = TrainState()
        self.stats = TrainStats()

        self._client: BleakClientWithServiceCache | None = None
        # Two locks: connecting and sending are separate so a command can
        # connect first without waiting on itself.
        self._connect_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._listeners: list[CALLBACK_TYPE] = []
        self._connect_task: asyncio.Task[None] | None = None
        self._expected_disconnect = False
        self._user_disconnected = False
        self._failures = 0
        self._next_attempt = 0.0
        self._auto_reconnect = True
        self._closed = False
        self._retry_cancel: CALLBACK_TYPE | None = None

    # ----------------------------------------------------------------- state

    @property
    def connected(self) -> bool:
        """Return True while the GATT connection is up."""
        return self._client is not None and self._client.is_connected

    @property
    def auto_reconnect(self) -> bool:
        """Return True if the train is reconnected automatically."""
        return self._auto_reconnect

    @callback
    def async_add_listener(self, update_callback: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Register a state listener; returns the function that removes it."""
        self._listeners.append(update_callback)

        @callback
        def remove_listener() -> None:
            self._listeners.remove(update_callback)

        return remove_listener

    @callback
    def _async_notify(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()

    @callback
    def _record_error(self, message: str) -> None:
        self.stats.last_error = message
        self.stats.last_error_time = dt_util.utcnow()

    # ------------------------------------------------------------ lifecycle

    @callback
    def async_start(self) -> None:
        """Watch for the train's advertisements and connect when it shows up."""
        self.entry.async_on_unload(
            bluetooth.async_register_callback(
                self.hass,
                self._async_on_advertisement,
                bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
                bluetooth.BluetoothScanningMode.PASSIVE,
            )
        )
        if bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True):
            self._async_schedule_connect()

    async def async_shutdown(self) -> None:
        """Disconnect without triggering a reconnect."""
        self._closed = True
        self._async_cancel_retry()
        if self._connect_task and not self._connect_task.done():
            self._connect_task.cancel()
        await self._async_drop_client()

    @callback
    def async_set_auto_reconnect(self, enabled: bool) -> None:
        """Turn automatic reconnection on or off."""
        self._auto_reconnect = enabled
        if enabled:
            self._next_attempt = 0.0
            if bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True):
                self._async_schedule_connect()
        else:
            self._async_cancel_retry()
            if self._connect_task and not self._connect_task.done():
                self._connect_task.cancel()
        self._async_notify()

    # ----------------------------------------------------------- connecting

    @callback
    def _async_on_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """The train's advertisement changed, e.g. it was just powered on.

        Home Assistant only calls this when the advertisement's content changes,
        so a train that stays on and keeps advertising the same data is handled
        by the retry timer instead.
        """
        if self._auto_reconnect and not self._user_disconnected and not self.connected:
            self._async_schedule_connect()

    @callback
    def _async_schedule_connect(self) -> None:
        if self._closed:
            return
        if self._connect_task and not self._connect_task.done():
            return
        if time.monotonic() < self._next_attempt:
            return
        self._connect_task = self.entry.async_create_background_task(
            self.hass, self._async_background_connect(), f"{DOMAIN} connect {self.address}"
        )

    async def _async_background_connect(self) -> None:
        try:
            await self._async_ensure_connected()
        except (BleakError, TimeoutError) as err:
            _LOGGER.debug("%s: automatic connection failed: %s", self.name, err)
            self._async_schedule_retry()

    @callback
    def _async_schedule_retry(self) -> None:
        """Try again later: 5, 10, 20, 30 s, then every 60 s."""
        if self._closed or not self._auto_reconnect or self._user_disconnected or self.connected:
            return
        self._async_cancel_retry()
        delay = RECONNECT_BACKOFF[min(self._failures, len(RECONNECT_BACKOFF) - 1)]
        self._retry_cancel = async_call_later(self.hass, delay, self._async_retry)

    @callback
    def _async_retry(self, _now: datetime) -> None:
        self._retry_cancel = None
        self._next_attempt = 0.0
        self._async_schedule_connect()

    @callback
    def _async_cancel_retry(self) -> None:
        if self._retry_cancel is not None:
            self._retry_cancel()
            self._retry_cancel = None

    async def _async_ensure_connected(self) -> BleakClientWithServiceCache:
        """Return a connected client, connecting first if needed."""
        if self._client is not None and self._client.is_connected:
            return self._client
        async with self._connect_lock:
            if self._client is not None and self._client.is_connected:
                return self._client

            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                self._failures += 1
                message = f"{self.name} is not in range of any Bluetooth adapter or proxy"
                self._record_error(message)
                self._async_notify()
                raise BleakError(message)

            self.stats.connection_attempts += 1
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.name,
                    disconnected_callback=self._on_disconnected,
                    max_attempts=3,
                    ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                        self.hass, self.address, connectable=True
                    )
                    or ble_device,
                )
            except (BleakError, TimeoutError) as err:
                self._failures += 1
                delay = RECONNECT_BACKOFF[min(self._failures, len(RECONNECT_BACKOFF)) - 1]
                self._next_attempt = time.monotonic() + delay
                self._record_error(f"Connection failed: {err}")
                self._async_notify()
                raise

            self._client = client
            self._expected_disconnect = False
            self._async_cancel_retry()
            self._failures = 0
            self._next_attempt = 0.0
            self.stats.last_error = None
            self.stats.last_error_time = None
            _LOGGER.info("Connected to %s (%s)", self.name, self.address)

            try:
                await client.start_notify(NOTIFY_CHARACTERISTIC_UUID, self._on_notification)
            except BleakError as err:
                _LOGGER.debug("%s: notifications unavailable: %s", self.name, err)

            if not self.stats.gatt_info:
                await self._async_read_device_info(client)

            self._async_notify()
            return client

    def _on_disconnected(self, client: BleakClientWithServiceCache) -> None:
        """Bleak calls this when the link drops, including on purpose."""
        if client is not self._client:
            return
        self._client = None
        expected, self._expected_disconnect = self._expected_disconnect, False
        if expected:
            _LOGGER.debug("%s: disconnected", self.name)
        else:
            _LOGGER.info("%s: connection lost; reconnecting", self.name)
            self._async_schedule_retry()
        self._async_notify()

    async def _async_drop_client(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        self._expected_disconnect = True
        try:
            await client.disconnect()
        except BleakError as err:
            _LOGGER.debug("%s: error while disconnecting: %s", self.name, err)
        self._async_notify()

    async def _async_read_device_info(self, client: BleakClientWithServiceCache) -> None:
        """Read the Device Information service and copy it to the device registry."""
        for char_uuid, key in DEVICE_INFO_CHARS.items():
            try:
                raw = await client.read_gatt_char(char_uuid)
            except BleakError:
                continue
            value = raw.decode("utf-8", errors="ignore").strip("\x00 ").strip()
            # LionChief firmware answers with the field's own name ("Serial Number").
            if value and value.lower() not in PLACEHOLDER_VALUES:
                self.stats.gatt_info[key] = value

        info = self.stats.gatt_info
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, self.address)})
        if device is None:
            return
        device_registry.async_update_device(
            device.id,
            model_id=info.get("model_number"),
            sw_version=info.get("software_revision") or info.get("firmware_revision"),
            hw_version=info.get("hardware_revision"),
            serial_number=info.get("serial_number"),
        )

    def _on_notification(self, _: BleakGATTCharacteristic, data: bytearray) -> None:
        """Parse status reports: [0x00, 0x81, 0x02, speed, direction, 0x03, 0x0C, flags]."""
        self.stats.last_message_hex = data.hex()
        if len(data) >= 8 and data[0] == 0x00 and data[1] == 0x81 and data[2] == 0x02:
            self.state.speed = speed_step_to_percent(data[3])
            self.state.direction_forward = data[4] == DIRECTION_FORWARD
            self.state.lights_on = bool(data[7] & 0x04)
            self.state.bell_on = bool(data[7] & 0x02)
        self._async_notify()

    # -------------------------------------------------------------- commands

    async def _async_send(self, payload: list[int]) -> None:
        """Write one command, connecting first and retrying once on a stale link."""
        async with self._command_lock:
            for attempt in (1, 2):
                try:
                    client = await self._async_ensure_connected()
                except (BleakError, TimeoutError) as err:
                    self.stats.failed_commands += 1
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="not_connected",
                        translation_placeholders={"name": self.name, "error": str(err)},
                    ) from err
                try:
                    await client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, bytes(payload))
                except (BleakError, TimeoutError) as err:
                    _LOGGER.debug("%s: write failed (attempt %d): %s", self.name, attempt, err)
                    await self._async_drop_client()
                    if attempt == 2:
                        self.stats.failed_commands += 1
                        self._record_error(f"Command failed: {err}")
                        self._async_notify()
                        raise HomeAssistantError(
                            translation_domain=DOMAIN,
                            translation_key="command_failed",
                            translation_placeholders={"name": self.name, "error": str(err)},
                        ) from err
                    continue
                self.stats.successful_commands += 1
                self.stats.last_message_hex = bytes(payload).hex()
                self._async_notify()
                return

    async def async_connect(self) -> None:
        """Connect now (user request); also re-enables automatic reconnection."""
        self._user_disconnected = False
        self._next_attempt = 0.0
        try:
            await self._async_ensure_connected()
        except (BleakError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_connected",
                translation_placeholders={"name": self.name, "error": str(err)},
            ) from err

    async def async_disconnect(self) -> None:
        """Release the train (user request) and stay off until asked to connect."""
        self._user_disconnected = True
        self._async_cancel_retry()
        if self._connect_task and not self._connect_task.done():
            self._connect_task.cancel()
        async with self._command_lock:
            if self.connected and self._client is not None:
                try:
                    await self._client.write_gatt_char(
                        WRITE_CHARACTERISTIC_UUID,
                        bytes(build_simple_command(CMD_DISCONNECT, [0x00, 0x00])),
                    )
                except BleakError as err:
                    _LOGGER.debug("%s: disconnect command failed: %s", self.name, err)
            await self._async_drop_client()

    async def async_set_speed(self, speed: int) -> None:
        """Set speed in percent (0-100)."""
        await self._async_send(build_simple_command(CMD_SPEED, [percent_to_speed_step(speed)]))
        self.state.speed = max(0, min(100, speed))
        self._async_notify()

    async def async_set_direction(self, forward: bool) -> None:
        """Set direction of travel."""
        value = DIRECTION_FORWARD if forward else DIRECTION_REVERSE
        await self._async_send(build_simple_command(CMD_DIRECTION, [value]))
        self.state.direction_forward = forward
        self._async_notify()

    async def async_set_lights(self, on: bool) -> None:
        """Turn the headlight on or off."""
        await self._async_send(build_simple_command(CMD_LIGHTS, [0x01 if on else 0x00]))
        self.state.lights_on = on
        self._async_notify()

    async def async_set_horn(self, on: bool) -> None:
        """Start or stop the horn."""
        await self._async_send(build_simple_command(CMD_HORN, [0x01 if on else 0x00]))
        self.state.horn_on = on
        self._async_notify()

    async def async_set_bell(self, on: bool) -> None:
        """Start or stop the bell."""
        await self._async_send(build_simple_command(CMD_BELL, [0x01 if on else 0x00]))
        self.state.bell_on = on
        self._async_notify()

    async def async_horn_blast(self, seconds: float = 0.5) -> None:
        """Sound the horn briefly."""
        await self.async_set_horn(True)
        await asyncio.sleep(seconds)
        await self.async_set_horn(False)

    async def async_ring_bell(self, seconds: float = 0.5) -> None:
        """Ring the bell briefly."""
        await self.async_set_bell(True)
        await asyncio.sleep(seconds)
        await self.async_set_bell(False)

    async def async_play_announcement(self, code: int) -> None:
        """Play one of the locomotive's recorded announcements."""
        await self._async_send(build_simple_command(CMD_ANNOUNCEMENT, [code, 0x00]))

    async def async_set_master_volume(self, volume: int) -> None:
        """Set overall volume (0-7)."""
        await self._async_send(build_simple_command(CMD_MASTER_VOLUME, [volume]))
        self.state.master_volume = volume
        self._async_notify()

    async def async_set_sound_volume(self, sound_source: int, volume: int) -> None:
        """Set the volume (0-7) of one sound source."""
        await self._async_send(build_simple_command(CMD_SOUND_VOLUME, [sound_source, volume]))
        setattr(self.state, SOUND_SOURCES[sound_source], volume)
        self._async_notify()

    # ---------------------------------------------------------- diagnostics

    def diagnostics(self) -> dict[str, Any]:
        """Data for the config entry diagnostics download."""
        services: list[dict[str, Any]] = []
        if self._client is not None and self.connected:
            for service in self._client.services:
                services.append(
                    {
                        "uuid": service.uuid,
                        "characteristics": [
                            {"uuid": char.uuid, "properties": char.properties}
                            for char in service.characteristics
                        ],
                    }
                )
        return {
            "address": self.address,
            "connected": self.connected,
            "auto_reconnect": self._auto_reconnect,
            "user_disconnected": self._user_disconnected,
            "consecutive_failures": self._failures,
            "state": self.state.__dict__,
            "stats": {
                **{k: v for k, v in self.stats.__dict__.items() if k != "last_error_time"},
                "last_error_time": self.stats.last_error_time.isoformat()
                if self.stats.last_error_time
                else None,
            },
            "gatt_services": services,
        }
