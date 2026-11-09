"""Number platform for Lionel Train Controller: throttle and volumes."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SOUND_SOURCE_BELL, SOUND_SOURCE_ENGINE, SOUND_SOURCE_HORN, SOUND_SOURCE_SPEECH
from .coordinator import LionelConfigEntry, LionelTrainCoordinator, TrainState
from .entity import LionelEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LionelNumberDescription(NumberEntityDescription):
    """Describes a Lionel number entity."""

    value_fn: Callable[[TrainState], int]
    set_fn: Callable[[LionelTrainCoordinator, int], Awaitable[None]]


def _volume(key: str, source: int | None) -> LionelNumberDescription:
    return LionelNumberDescription(
        key=key,
        translation_key=key,
        mode=NumberMode.SLIDER,
        native_min_value=0,
        native_max_value=7,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda state: getattr(state, key),
        set_fn=(
            (lambda coordinator, value: coordinator.async_set_master_volume(value))
            if source is None
            else (lambda coordinator, value: coordinator.async_set_sound_volume(source, value))
        ),
    )


NUMBERS: tuple[LionelNumberDescription, ...] = (
    LionelNumberDescription(
        key="throttle",
        translation_key="throttle",
        mode=NumberMode.SLIDER,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda state: state.speed,
        set_fn=lambda coordinator, value: coordinator.async_set_speed(value),
    ),
    _volume("master_volume", None),
    _volume("horn_volume", SOUND_SOURCE_HORN),
    _volume("bell_volume", SOUND_SOURCE_BELL),
    _volume("speech_volume", SOUND_SOURCE_SPEECH),
    _volume("engine_volume", SOUND_SOURCE_ENGINE),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LionelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator = entry.runtime_data
    async_add_entities(LionelNumber(coordinator, description) for description in NUMBERS)


class LionelNumber(LionelEntity, NumberEntity):
    """Throttle or a volume control."""

    entity_description: LionelNumberDescription

    def __init__(
        self, coordinator: LionelTrainCoordinator, description: LionelNumberDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator.state)

    async def async_set_native_value(self, value: float) -> None:
        """Send the new value to the train."""
        await self.entity_description.set_fn(self.coordinator, int(value))
