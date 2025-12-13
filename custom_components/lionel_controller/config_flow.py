"""Config flow for Lionel Train Controller integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from bleak import BleakScanner
from bleak.exc import BleakError
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

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

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MAC_ADDRESS): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_SERVICE_UUID, default=DEFAULT_SERVICE_UUID): str,
    }
)

# Special value for manual entry option
MANUAL_ENTRY = "__manual_entry__"


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    mac_address = data[CONF_MAC_ADDRESS]
    
    # Validate MAC address format
    if not _is_valid_mac_address(mac_address):
        raise InvalidMacAddress

    # Try to discover the device
    try:
        scanner = BleakScanner()
        devices = await scanner.discover(timeout=10.0)
        
        device_found = any(
            device.address.upper() == mac_address.upper() for device in devices
        )
        
        if not device_found:
            raise CannotConnect
            
    except BleakError as err:
        _LOGGER.exception("Error discovering Bluetooth devices")
        raise CannotConnect from err

    # Return info that you want to store in the config entry.
    return {
        "title": data[CONF_NAME],
        "mac_address": mac_address.upper(),
        "service_uuid": data[CONF_SERVICE_UUID],
    }


def _is_valid_mac_address(mac: str) -> bool:
    """Check if MAC address is valid."""
    parts = mac.split(":")
    if len(parts) != 6:
        return False
    
    for part in parts:
        if len(part) != 2:
            return False
        try:
            int(part, 16)
        except ValueError:
            return False
    
    return True


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lionel Train Controller."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._scanned_devices: dict[str, dict[str, Any]] = {}
        self._pending_device: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - scan for devices or manual entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = user_input.get("device")
            
            if selected == MANUAL_ENTRY:
                # User wants to enter MAC address manually
                return await self.async_step_manual()
            
            if selected and selected in self._scanned_devices:
                # User selected a discovered device - proceed to train model selection
                device_info = self._scanned_devices[selected]
                
                # Check if already configured
                await self.async_set_unique_id(device_info["mac_address"])
                self._abort_if_unique_id_configured()
                
                # Store device info and proceed to train model selection
                self._pending_device = {
                    CONF_MAC_ADDRESS: device_info["mac_address"],
                    CONF_NAME: device_info["name"],
                    CONF_SERVICE_UUID: DEFAULT_SERVICE_UUID,
                }
                return await self.async_step_train_model()

        # Scan for Lionel trains
        _LOGGER.info("Scanning for Lionel LionChief trains...")
        await self._async_scan_for_trains()
        _LOGGER.info("Scan complete. Found %d trains.", len(self._scanned_devices))
        
        # Build selection list - always show the form with manual entry option
        device_options = {
            mac: f"{info['name']} ({mac})"
            for mac, info in self._scanned_devices.items()
        }
        device_options[MANUAL_ENTRY] = "Enter MAC address manually..."
        
        # Show description based on whether devices were found
        if not self._scanned_devices:
            errors["base"] = "no_devices_found"
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): vol.In(device_options),
                }
            ),
            errors=errors,
        )

    async def _async_scan_for_trains(self) -> None:
        """Scan for Lionel LionChief trains via Bluetooth."""
        self._scanned_devices = {}
        
        try:
            # First, check Home Assistant's Bluetooth cache for known devices
            service_infos = bluetooth.async_discovered_service_info(self.hass)
            
            _LOGGER.debug("Scanning devices from HA Bluetooth cache")
            
            for service_info in service_infos:
                device_name = service_info.name or ""
                
                # Only show devices with name starting with "LC" (LionChief naming convention)
                # This is the most reliable filter as the service UUID may not always be advertised
                if not device_name.upper().startswith("LC"):
                    continue
                
                _LOGGER.debug(
                    "Found LC device: name='%s', address=%s, uuids=%s",
                    device_name, service_info.address, service_info.service_uuids
                )
                
                mac = service_info.address.upper()
                
                # Skip already configured devices
                if self._is_already_configured(mac):
                    _LOGGER.debug("Skipping already configured device: %s", mac)
                    continue
                
                self._scanned_devices[mac] = {
                    "mac_address": mac,
                    "name": device_name,
                }
                _LOGGER.info("Found Lionel train: %s at %s", device_name, mac)
            
            # If no devices found in cache, try active scanning
            if not self._scanned_devices:
                _LOGGER.debug("No trains in cache, performing active scan...")
                scanner = BleakScanner()
                devices = await scanner.discover(timeout=10.0)
                
                for device in devices:
                    device_name = device.name or ""
                    
                    # Only show devices with name starting with "LC"
                    if not device_name.upper().startswith("LC"):
                        continue
                    
                    mac = device.address.upper()
                    
                    if self._is_already_configured(mac):
                        continue
                    
                    self._scanned_devices[mac] = {
                        "mac_address": mac,
                        "name": device_name,
                    }
                    _LOGGER.debug("Found Lionel train via scan: %s at %s", device_name, mac)
                            

        except BleakError as err:
            _LOGGER.warning("Error scanning for Bluetooth devices: %s", err)

    def _is_already_configured(self, mac_address: str) -> bool:
        """Check if a device is already configured."""
        for entry in self._async_current_entries():
            if entry.data.get(CONF_MAC_ADDRESS, "").upper() == mac_address.upper():
                return True
        return False

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual MAC address entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidMacAddress:
                errors[CONF_MAC_ADDRESS] = "invalid_mac"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Check if already configured
                await self.async_set_unique_id(info["mac_address"])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data={
                    CONF_MAC_ADDRESS: info["mac_address"],
                    CONF_NAME: info["title"],
                    CONF_SERVICE_UUID: info["service_uuid"],
                })

        return self.async_show_form(
            step_id="manual", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_train_model(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle train model selection step."""
        if user_input is not None:
            train_model = user_input.get(CONF_TRAIN_MODEL, "Generic")
            
            # Create the entry with the selected train model
            return self.async_create_entry(
                title=self._pending_device[CONF_NAME],
                data={
                    **self._pending_device,
                    CONF_TRAIN_MODEL: train_model,
                },
            )

        # Build train model options
        model_options = {model: model for model in TRAIN_MODEL_OPTIONS}

        return self.async_show_form(
            step_id="train_model",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TRAIN_MODEL, default="Generic"): vol.In(model_options),
                }
            ),
            description_placeholders={
                "name": self._pending_device[CONF_NAME],
            },
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        # Check if this is a Lionel train by service UUID
        lionel_service_found = False
        for service_uuid in discovery_info.service_uuids:
            if service_uuid.lower() == DEFAULT_SERVICE_UUID.lower():
                lionel_service_found = True
                break
        
        if not lionel_service_found:
            return self.async_abort(reason="not_lionel_device")

        self._discovered_devices[discovery_info.address] = discovery_info
        
        # Set context for better user experience
        self.context["title_placeholders"] = {
            "name": discovery_info.name or f"Lionel Train ({discovery_info.address[-5:]})"
        }
        
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        if user_input is not None:
            discovery_info = self._discovered_devices[self.unique_id]
            
            # Try to get device name from discovery or use default
            device_name = discovery_info.name
            if not device_name:
                # Create a friendly name based on MAC address
                mac_suffix = discovery_info.address[-5:].replace(":", "")
                device_name = f"Lionel Train {mac_suffix}"
            
            return self.async_create_entry(
                title=device_name,
                data={
                    CONF_MAC_ADDRESS: discovery_info.address,
                    CONF_NAME: device_name,
                    CONF_SERVICE_UUID: DEFAULT_SERVICE_UUID,
                },
            )

        # Show confirmation form with device details
        discovery_info = self._discovered_devices[self.unique_id]
        device_name = discovery_info.name or f"Lionel Train ({discovery_info.address[-5:]})"
        
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": device_name,
                "address": discovery_info.address,
            },
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidMacAddress(HomeAssistantError):
    """Error to indicate there is invalid MAC address."""