"""Button platform for Lionel Train Controller."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ANNOUNCEMENTS
from .coordinator import LionelConfigEntry, LionelTrainCoordinator
from .entity import LionelEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LionelButtonDescription(ButtonEntityDescription):
    """Describes a Lionel button."""

    press_fn: Callable[[LionelTrainCoordinator], Awaitable[None]]
    requires_connection: bool = True


BUTTONS: tuple[LionelButtonDescription, ...] = (
    LionelButtonDescription(
        key="connect",
        translation_key="connect",
        entity_category=EntityCategory.CONFIG,
        requires_connection=False,
        press_fn=lambda coordinator: coordinator.async_connect(),
    ),
    LionelButtonDescription(
        key="disconnect",
        translation_key="disconnect",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda coordinator: coordinator.async_disconnect(),
    ),
    LionelButtonDescription(
        key="stop",
        translation_key="stop",
        press_fn=lambda coordinator: coordinator.async_set_speed(0),
    ),
    LionelButtonDescription(
        key="forward",
        translation_key="forward",
        press_fn=lambda coordinator: coordinator.async_set_direction(True),
    ),
    LionelButtonDescription(
        key="reverse",
        translation_key="reverse",
        press_fn=lambda coordinator: coordinator.async_set_direction(False),
    ),
    LionelButtonDescription(
        key="horn",
        translation_key="horn",
        press_fn=lambda coordinator: coordinator.async_horn_blast(0.3),
    ),
    LionelButtonDescription(
        key="bell",
        translation_key="bell",
        press_fn=lambda coordinator: coordinator.async_ring_bell(0.3),
    ),
)


def _announcement(name: str, code: int) -> LionelButtonDescription:
    return LionelButtonDescription(
        # Unique id suffix kept from earlier versions so entity ids don't change.
        key=f"announcement_{name.lower().replace(' ', '_')}",
        translation_key="announcement",
        translation_placeholders={"announcement": name},
        press_fn=lambda coordinator: coordinator.async_play_announcement(code),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LionelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    coordinator = entry.runtime_data
    descriptions = [
        *BUTTONS,
        *(_announcement(name, item["code"]) for name, item in ANNOUNCEMENTS.items()),
    ]
    async_add_entities(LionelButton(coordinator, description) for description in descriptions)


class LionelButton(LionelEntity, ButtonEntity):
    """A one-shot train action."""

    entity_description: LionelButtonDescription

    def __init__(
        self, coordinator: LionelTrainCoordinator, description: LionelButtonDescription
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._requires_connection = description.requires_connection

    async def async_press(self) -> None:
        """Run the action."""
        await self.entity_description.press_fn(self.coordinator)
