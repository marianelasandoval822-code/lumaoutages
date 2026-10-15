"""Shared entity bases for the three data sources."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import TOTAL_KEY, RegionData, TownOutage
from .const import (
    CONF_INCLUDE_TOTAL,
    CONF_REGIONS,
    DOMAIN,
    REGION_LABELS,
    TOWN_OPTIONS,
)
from .coordinator import (
    GenerationCoordinator,
    LumaConfigEntry,
    LumaCoordinator,
    TownsCoordinator,
)

THIRD_PARTY = "hayluzpr.com"


def selected_region_keys(entry: LumaConfigEntry) -> list[str]:
    """Regions the user picked, plus the island total if enabled."""
    keys = list(entry.options.get(CONF_REGIONS, []))
    if entry.options.get(CONF_INCLUDE_TOTAL, False):
        keys.append(TOTAL_KEY)
    return keys


# ------------------------------------------------------------- LUMA regions


class LumaEntity(CoordinatorEntity[LumaCoordinator]):
    """One entity for one LUMA region (or the island total)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LumaCoordinator,
        entry: LumaConfigEntry,
        region_key: str,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._region_key = region_key
        self._attr_unique_id = f"{entry.entry_id}_{region_key}_{key}"
        label = REGION_LABELS.get(region_key, region_key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{region_key}")},
            name=f"LUMA {label}",
            manufacturer="LUMA Energy",
            model="Outage region",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def region(self) -> RegionData | None:
        return self.coordinator.data.get(self._region_key)

    @property
    def available(self) -> bool:
        return super().available and self.region is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        region = self.region
        if region is not None:
            attrs["region"] = region.name
        stamp = self.coordinator.data.reported_at
        if stamp is not None:
            attrs["reported_at"] = stamp.isoformat()
        return attrs


# --------------------------------------------------------------- generation


class LumaGenerationEntity(CoordinatorEntity[GenerationCoordinator]):
    """Entities on the 'LUMA Generation' device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: GenerationCoordinator, entry: LumaConfigEntry, suffix: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_gen_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_generation")},
            name="LUMA Generation",
            manufacturer=THIRD_PARTY,
            model="Power plant output",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is not None and data.fetched_at is not None:
            return {"fetched_at": data.fetched_at.isoformat()}
        return {}


# -------------------------------------------------------------------- towns


def town_device(entry: LumaConfigEntry, town_key: str) -> DeviceInfo:
    label = TOWN_OPTIONS.get(town_key, town_key)
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_town_{town_key}")},
        name=f"LUMA {label} (town)",
        manufacturer=THIRD_PARTY,
        model="Town outage zones",
        entry_type=DeviceEntryType.SERVICE,
    )


class LumaTownEntity(CoordinatorEntity[TownsCoordinator]):
    """One entity for one followed town."""

    _attr_has_entity_name = True
    # The zone list can change every poll; keep it out of the recorder.
    _unrecorded_attributes = frozenset({"zones"})

    def __init__(
        self,
        coordinator: TownsCoordinator,
        entry: LumaConfigEntry,
        town_key: str,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._town_key = town_key
        self._attr_unique_id = f"{entry.entry_id}_town_{town_key}_{key}"
        self._attr_device_info = town_device(entry, town_key)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def zones(self) -> tuple[str, ...]:
        """Zones LUMA lists for this town; empty when the town is not listed."""
        data = self.coordinator.data
        if data is None:
            return ()
        outage: TownOutage | None = data.affected.get(self._town_key)
        return outage.zones if outage else ()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "town": TOWN_OPTIONS.get(self._town_key, self._town_key),
            "zones": list(self.zones),
        }
        data = self.coordinator.data
        if data is not None and data.fetched_at is not None:
            attrs["fetched_at"] = data.fetched_at.isoformat()
        return attrs
