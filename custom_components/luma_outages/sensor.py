"""Sensors: LUMA regions, power-plant generation, and town outage zones."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import GenerationData, PlantData, RegionData
from .const import CONF_TOWNS, DOMAIN
from .coordinator import (
    GenerationCoordinator,
    LumaConfigEntry,
    LumaCoordinator,
    TownsCoordinator,
)
from .entity import (
    THIRD_PARTY,
    LumaEntity,
    LumaGenerationEntity,
    LumaTownEntity,
    selected_region_keys,
)

# ------------------------------------------------------------ LUMA regions


@dataclass(frozen=True, kw_only=True)
class LumaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[RegionData], float | int]


SENSORS: tuple[LumaSensorDescription, ...] = (
    LumaSensorDescription(
        key="percent_with_power",
        translation_key="percent_with_power",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash",
        value_fn=lambda r: r.percent_with,
    ),
    LumaSensorDescription(
        key="percent_without_service",
        translation_key="percent_without_service",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash-off",
        value_fn=lambda r: r.percent_without,
    ),
    LumaSensorDescription(
        key="clients_without_service",
        translation_key="clients_without_service",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-lightning-bolt-outline",
        value_fn=lambda r: r.without_service,
    ),
    LumaSensorDescription(
        key="unplanned_outage_clients",
        translation_key="unplanned_outage_clients",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower-off",
        value_fn=lambda r: r.unplanned_outage,
    ),
    LumaSensorDescription(
        key="planned_outage_clients",
        translation_key="planned_outage_clients",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
        value_fn=lambda r: r.planned_outage,
    ),
    LumaSensorDescription(
        key="load_shed_clients",
        translation_key="load_shed_clients",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:power-plug-off",
        value_fn=lambda r: r.load_shed,
    ),
    LumaSensorDescription(
        key="clients_with_service",
        translation_key="clients_with_service",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda r: r.with_service,
    ),
    LumaSensorDescription(
        key="clients_total",
        translation_key="clients_total",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda r: r.total_clients,
    ),
)


class LumaSensor(LumaEntity, SensorEntity):
    entity_description: LumaSensorDescription

    def __init__(
        self,
        coordinator: LumaCoordinator,
        entry: LumaConfigEntry,
        region_key: str,
        description: LumaSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, region_key, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        region = self.region
        return None if region is None else self.entity_description.value_fn(region)


# --------------------------------------------------------------- generation


@dataclass(frozen=True, kw_only=True)
class GenerationTotalDescription(SensorEntityDescription):
    value_fn: Callable[[GenerationData], float]


GENERATION_TOTALS: tuple[GenerationTotalDescription, ...] = (
    GenerationTotalDescription(
        key="total_output",
        translation_key="total_output",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.MEGA_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:transmission-tower",
        value_fn=lambda d: d.total_current_mw,
    ),
    GenerationTotalDescription(
        key="total_capacity",
        translation_key="total_capacity",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.MEGA_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.total_max_mw,
    ),
    GenerationTotalDescription(
        key="total_utilization",
        translation_key="total_utilization",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:gauge",
        value_fn=lambda d: d.total_percent_of_max,
    ),
)


@dataclass(frozen=True, kw_only=True)
class PlantSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PlantData], float]


PLANT_SENSORS: tuple[PlantSensorDescription, ...] = (
    PlantSensorDescription(
        key="output",
        translation_key="plant_output",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.MEGA_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda p: p.current_mw,
    ),
    PlantSensorDescription(
        key="utilization",
        translation_key="plant_utilization",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:gauge",
        value_fn=lambda p: p.percent_of_max,
    ),
)


class LumaGenerationTotalSensor(LumaGenerationEntity, SensorEntity):
    entity_description: GenerationTotalDescription

    def __init__(
        self,
        coordinator: GenerationCoordinator,
        entry: LumaConfigEntry,
        description: GenerationTotalDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        return None if data is None else self.entity_description.value_fn(data)


class LumaPlantSensor(LumaGenerationEntity, SensorEntity):
    entity_description: PlantSensorDescription

    def __init__(
        self,
        coordinator: GenerationCoordinator,
        entry: LumaConfigEntry,
        plant: PlantData,
        description: PlantSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, f"{plant.key}_{description.key}")
        self.entity_description = description
        self._plant_key = plant.key
        self._attr_translation_placeholders = {"plant": plant.label}

    @property
    def plant(self) -> PlantData | None:
        data = self.coordinator.data
        return None if data is None else data.plants.get(self._plant_key)

    @property
    def available(self) -> bool:
        return super().available and self.plant is not None

    @property
    def native_value(self) -> float | None:
        plant = self.plant
        return None if plant is None else self.entity_description.value_fn(plant)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        plant = self.plant
        if plant is not None:
            attrs["plant"] = plant.label
            attrs["max_mw"] = plant.max_mw
        return attrs


# -------------------------------------------------------------------- towns


class LumaTownZonesSensor(LumaTownEntity, SensorEntity):
    """How many zones in the followed town are listed as without service."""

    _attr_translation_key = "town_zones"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-alert-outline"

    def __init__(
        self, coordinator: TownsCoordinator, entry: LumaConfigEntry, town_key: str
    ) -> None:
        super().__init__(coordinator, entry, town_key, "zones")

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return len(self.zones)


class LumaTownsSummarySensor(CoordinatorEntity[TownsCoordinator], SensorEntity):
    """How many towns have any zone without service, island-wide."""

    _attr_has_entity_name = True
    _attr_translation_key = "towns_with_outages"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-radius-outline"
    _unrecorded_attributes = frozenset({"towns"})

    def __init__(self, coordinator: TownsCoordinator, entry: LumaConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_towns_with_outages"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_towns_summary")},
            name="LUMA Towns",
            manufacturer=THIRD_PARTY,
            model="Town outage zones",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        return None if data is None else data.count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is None:
            return {}
        attrs: dict[str, Any] = {
            "towns": sorted(t.name for t in data.affected.values())
        }
        if data.fetched_at is not None:
            attrs["fetched_at"] = data.fetched_at.isoformat()
        return attrs


# -------------------------------------------------------------------- setup


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data

    if runtime.outages is not None:
        async_add_entities(
            LumaSensor(runtime.outages, entry, region_key, description)
            for region_key in selected_region_keys(entry)
            for description in SENSORS
        )

    if runtime.generation is not None:
        generation = runtime.generation
        async_add_entities(
            LumaGenerationTotalSensor(generation, entry, description)
            for description in GENERATION_TOTALS
        )

        known_plants: set[str] = set()

        @callback
        def _add_new_plants() -> None:
            # Plants are discovered from the data, so a new plant in the feed
            # (or a first successful poll after a failed start) gets entities.
            data = generation.data
            if data is None:
                return
            new = [p for k, p in data.plants.items() if k not in known_plants]
            if not new:
                return
            known_plants.update(p.key for p in new)
            async_add_entities(
                LumaPlantSensor(generation, entry, plant, description)
                for plant in new
                for description in PLANT_SENSORS
            )

        entry.async_on_unload(generation.async_add_listener(_add_new_plants))
        _add_new_plants()

    if runtime.towns is not None:
        towns = runtime.towns
        entities: list[SensorEntity] = [LumaTownsSummarySensor(towns, entry)]
        entities.extend(
            LumaTownZonesSensor(towns, entry, town_key)
            for town_key in entry.options.get(CONF_TOWNS, [])
        )
        async_add_entities(entities)
