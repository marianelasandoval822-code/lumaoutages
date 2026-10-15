"""LUMA Outages: regional outages, load shed, planned work, generation and town zones."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_GENERATION, CONF_INCLUDE_TOTAL, CONF_REGIONS, CONF_TOWNS
from .coordinator import (
    GenerationCoordinator,
    LumaConfigEntry,
    LumaCoordinator,
    LumaRuntimeData,
    TownsCoordinator,
)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: LumaConfigEntry) -> bool:
    options = entry.options

    # LUMA's own data is the one source that must work for setup to succeed.
    outages: LumaCoordinator | None = None
    if options.get(CONF_REGIONS) or options.get(CONF_INCLUDE_TOTAL):
        outages = LumaCoordinator(hass, entry)
        await outages.async_config_entry_first_refresh()

    # hayluzpr.com is a third party: if it is down at startup the entities just
    # show unavailable and recover on a later poll.
    generation: GenerationCoordinator | None = None
    if options.get(CONF_GENERATION, False):
        generation = GenerationCoordinator(hass, entry)
        await generation.async_refresh()

    towns: TownsCoordinator | None = None
    if options.get(CONF_TOWNS):
        towns = TownsCoordinator(hass, entry)
        await towns.async_refresh()

    entry.runtime_data = LumaRuntimeData(
        outages=outages, generation=generation, towns=towns
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LumaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: LumaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
