"""Config flow for Lionel Train Controller."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME

from .const import (
    CONF_MAC_ADDRESS,
    CONF_SERVICE_UUID,
    CONF_TRAIN_MODEL,
    DEFAULT_NAME,
    DEFAULT_SERVICE_UUID,
    DOMAIN,
    LIONCHIEF_SERVICE_UUID,
)
from .train_models import TRAIN_MODEL_OPTIONS

MANUAL_ENTRY = "__manual_entry__"
MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def is_lionchief(service_info: bluetooth.BluetoothServiceInfoBleak) -> bool:
    """LionChief locomotives advertise their service, and are named LC-…."""
    return LIONCHIEF_SERVICE_UUID in (u.lower() for u in service_info.service_uuids) or (
        service_info.name or ""
    ).upper().startswith("LC")


class LionelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lionel Train Controller.

    Everything goes through Home Assistant's Bluetooth stack, so local adapters
    and ESPHome Bluetooth proxies both work.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovery: bluetooth.BluetoothServiceInfoBleak | None = None
        self._candidates: dict[str, str] = {}
        self._pending: dict[str, Any] = {}

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """A locomotive was seen advertising."""
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()
        if not is_lionchief(discovery_info):
            return self.async_abort(reason="not_lionel_device")
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": self._display_name(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered locomotive."""
        assert self._discovery is not None
        name = self._display_name(self._discovery)
        if user_input is not None:
            self._pending = {
                CONF_MAC_ADDRESS: self._discovery.address.upper(),
                CONF_NAME: name,
            }
            return await self.async_step_train_model()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": name, "address": self._discovery.address},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a locomotive Home Assistant can currently see, or enter one."""
        if user_input is not None:
            choice = user_input["device"]
            if choice == MANUAL_ENTRY:
                return await self.async_step_manual()
            await self.async_set_unique_id(choice, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._pending = {CONF_MAC_ADDRESS: choice, CONF_NAME: self._candidates[choice]}
            return await self.async_step_train_model()

        configured = self._async_current_ids(include_ignore=False)
        self._candidates = {
            info.address.upper(): self._display_name(info)
            for info in bluetooth.async_discovered_service_info(self.hass, connectable=True)
            if is_lionchief(info) and info.address.upper() not in configured
        }
        options = {mac: f"{name} ({mac})" for mac, name in self._candidates.items()}
        options[MANUAL_ENTRY] = "Enter MAC address manually..."
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("device"): vol.In(options)}),
            errors={} if self._candidates else {"base": "no_devices_found"},
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter a MAC address by hand."""
        errors: dict[str, str] = {}
        if user_input is not None:
            mac = user_input[CONF_MAC_ADDRESS].strip().upper().replace("-", ":")
            if not MAC_RE.match(mac):
                errors[CONF_MAC_ADDRESS] = "invalid_mac"
            elif not bluetooth.async_ble_device_from_address(self.hass, mac, connectable=True):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(mac, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                self._pending = {CONF_MAC_ADDRESS: mac, CONF_NAME: user_input[CONF_NAME]}
                return await self.async_step_train_model()
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_MAC_ADDRESS): str,
                        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_train_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the model, which names the announcement buttons."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._pending[CONF_NAME],
                data={
                    **self._pending,
                    CONF_SERVICE_UUID: DEFAULT_SERVICE_UUID,
                    CONF_TRAIN_MODEL: user_input[CONF_TRAIN_MODEL],
                },
            )
        return self.async_show_form(
            step_id="train_model",
            data_schema=vol.Schema(
                {vol.Required(CONF_TRAIN_MODEL, default="Generic"): vol.In(TRAIN_MODEL_OPTIONS)}
            ),
            description_placeholders={"name": self._pending[CONF_NAME]},
        )

    @staticmethod
    def _display_name(info: bluetooth.BluetoothServiceInfoBleak) -> str:
        return info.name or f"Lionel Train {info.address[-5:].replace(':', '')}"
