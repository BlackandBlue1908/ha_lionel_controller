"""Diagnostics download for Lionel Train Controller."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import LionelConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LionelConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "entry": {"title": entry.title, "data": dict(entry.data)},
        "train": entry.runtime_data.diagnostics(),
    }
