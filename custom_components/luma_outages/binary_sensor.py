"""Binary sensors: regional outage/load-shed/planned work, and town outage reports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import RegionData
from .const import CONF_THRESHOLD, CONF_TOWNS, DEFAULT_THRESHOLD
from .coordinator import LumaConfigEntry, LumaCoordinator, TownsCoordinator
from .entity import LumaEntity, LumaTownEntity, selected_region_keys


@dataclass(frozen=True, kw_only=True)
class LumaBinaryDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[RegionData, float], bool]


BINARY_SENSORS: tuple[LumaBinaryDescription, ...] = (
    LumaBinaryDescription(
        key="significant_outage",
        translation_key="significant_outage",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda r, threshold: r.percent_without >= threshold,
    ),
    LumaBinaryDescription(
        key="load_shed",
        translation_key="load_shed",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda r, threshold: r.load_shed > 0,
    ),
    LumaBinaryDescription(
        key="planned_work",
        translation_key="planned_work",
        icon="mdi:calendar-clock",
        is_on_fn=lambda r, threshold: r.planned_outage > 0,
    ),
)


class LumaBinarySensor(LumaEntity, BinarySensorEntity):
    entity_description: LumaBinaryDescription

    def __init__(
        self,
        coordinator: LumaCoordinator,
        entry: LumaConfigEntry,
        region_key: str,
        description: LumaBinaryDescription,
    ) -> None:
        super().__init__(coordinator, entry, region_key, description.key)
        self.entity_description = description
        self._threshold = float(entry.options.get(CONF_THRESHOLD, DEFAULT_THRESHOLD))

    @property
    def is_on(self) -> bool | None:
        region = self.region
        if region is None:
            return None
        return self.entity_description.is_on_fn(region, self._threshold)


class LumaTownOutageSensor(LumaTownEntity, BinarySensorEntity):
    """On when LUMA lists at least one zone in the followed town as without service."""

    _attr_translation_key = "town_outage"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self, coordinator: TownsCoordinator, entry: LumaConfigEntry, town_key: str
    ) -> None:
        super().__init__(coordinator, entry, town_key, "outage")

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return bool(self.zones)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data

    if runtime.outages is not None:
        async_add_entities(
            LumaBinarySensor(runtime.outages, entry, region_key, description)
            for region_key in selected_region_keys(entry)
            for description in BINARY_SENSORS
        )

    if runtime.towns is not None:
        async_add_entities(
            LumaTownOutageSensor(runtime.towns, entry, town_key)
            for town_key in entry.options.get(CONF_TOWNS, [])
        )
