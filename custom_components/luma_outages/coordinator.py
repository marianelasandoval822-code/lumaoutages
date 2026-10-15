"""Polling coordinators: one per data source."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    GenerationData,
    HayluzClient,
    LumaApiBlockedError,
    LumaApiError,
    LumaClient,
    LumaData,
    TownsData,
    parse_headers,
)
from .const import CONF_HEADERS, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type LumaConfigEntry = ConfigEntry[LumaRuntimeData]


def _interval(entry: ConfigEntry) -> timedelta:
    return timedelta(minutes=int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))


class LumaCoordinator(DataUpdateCoordinator[LumaData]):
    """LUMA's regional endpoint. One request per cycle serves every region."""

    config_entry: LumaConfigEntry

    def __init__(self, hass: HomeAssistant, entry: LumaConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} regions",
            config_entry=entry,
            update_interval=_interval(entry),
        )
        try:
            headers = parse_headers(entry.options.get(CONF_HEADERS))
        except ValueError:
            _LOGGER.warning("Ignoring invalid custom headers in LUMA Outages options")
            headers = {}
        self.client = LumaClient(async_get_clientsession(hass), headers)

    async def _async_update_data(self) -> LumaData:
        try:
            return await self.client.async_fetch()
        except LumaApiBlockedError as err:
            raise UpdateFailed(
                f"LUMA rejected the request ({err}). Check the device-emulation "
                "headers in the integration options."
            ) from err
        except LumaApiError as err:
            raise UpdateFailed(str(err)) from err


class GenerationCoordinator(DataUpdateCoordinator[GenerationData]):
    """Power-plant output from hayluzpr.com."""

    config_entry: LumaConfigEntry

    def __init__(self, hass: HomeAssistant, entry: LumaConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} generation",
            config_entry=entry,
            update_interval=_interval(entry),
        )
        self.client = HayluzClient(async_get_clientsession(hass))

    async def _async_update_data(self) -> GenerationData:
        try:
            return await self.client.async_fetch_generation()
        except LumaApiError as err:
            raise UpdateFailed(f"hayluzpr.com generation data: {err}") from err


class TownsCoordinator(DataUpdateCoordinator[TownsData]):
    """Town-level outage zones from hayluzpr.com."""

    config_entry: LumaConfigEntry

    def __init__(self, hass: HomeAssistant, entry: LumaConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} towns",
            config_entry=entry,
            update_interval=_interval(entry),
        )
        self.client = HayluzClient(async_get_clientsession(hass))

    async def _async_update_data(self) -> TownsData:
        try:
            return await self.client.async_fetch_towns()
        except LumaApiError as err:
            raise UpdateFailed(f"hayluzpr.com town outages: {err}") from err


@dataclass
class LumaRuntimeData:
    """Whichever coordinators the user's options turned on."""

    outages: LumaCoordinator | None
    generation: GenerationCoordinator | None
    towns: TownsCoordinator | None
