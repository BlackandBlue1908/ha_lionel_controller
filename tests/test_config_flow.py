"""Config flow tests."""
from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.lionel_controller.const import CONF_MAC_ADDRESS, CONF_TRAIN_MODEL, DOMAIN

from .conftest import ADDRESS, service_info

FLOW = "custom_components.lionel_controller.config_flow"


async def test_bluetooth_discovery(hass: HomeAssistant) -> None:
    """A discovered locomotive is confirmed, given a model, and created."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=service_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "train_model"
    with patch("custom_components.lionel_controller.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TRAIN_MODEL: "Polar Express"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == ADDRESS
    assert result["data"][CONF_MAC_ADDRESS] == ADDRESS
    assert result["data"][CONF_TRAIN_MODEL] == "Polar Express"


async def test_bluetooth_discovery_not_a_train(hass: HomeAssistant) -> None:
    """Devices that are not LionChief locomotives are dropped."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=service_info(name="Luba-VPQEU7P6", address="AA:BB:CC:DD:EE:FF", uuids=[]),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_lionel_device"


async def test_user_picks_visible_train(hass: HomeAssistant) -> None:
    """The user step lists trains Home Assistant can see (no private scanner)."""
    with patch(f"{FLOW}.bluetooth.async_discovered_service_info", return_value=[service_info(), service_info(name="Other", address="11:22:33:44:55:66", uuids=[])]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["step_id"] == "user"
    assert not result["errors"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"device": ADDRESS})
    assert result["step_id"] == "train_model"
    with patch("custom_components.lionel_controller.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TRAIN_MODEL: "Generic"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "LC-0-1-0401-3150"


async def test_manual_entry(hass: HomeAssistant) -> None:
    """Manual entry validates the address and needs the train in range."""
    with patch(f"{FLOW}.bluetooth.async_discovered_service_info", return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["errors"] == {"base": "no_devices_found"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": "__manual_entry__"}
    )
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MAC_ADDRESS: "not-a-mac", "name": "Train"}
    )
    assert result["errors"] == {CONF_MAC_ADDRESS: "invalid_mac"}
    with patch(f"{FLOW}.bluetooth.async_ble_device_from_address", return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MAC_ADDRESS: ADDRESS.lower(), "name": "Train"}
        )
    assert result["errors"] == {"base": "cannot_connect"}
    with patch(f"{FLOW}.bluetooth.async_ble_device_from_address", return_value=object()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MAC_ADDRESS: ADDRESS.lower(), "name": "Train"}
        )
    assert result["step_id"] == "train_model"
