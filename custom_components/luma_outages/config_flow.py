"""Config and options flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .api import LumaApiBlockedError, LumaApiError, LumaClient, parse_headers
from .const import (
    CONF_GENERATION,
    CONF_HEADERS,
    CONF_INCLUDE_TOTAL,
    CONF_REGIONS,
    CONF_SCAN_INTERVAL,
    CONF_THRESHOLD,
    CONF_TOWNS,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_THRESHOLD,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    REGION_OPTIONS,
    TOWN_OPTIONS,
)


def _dropdown(options: dict[str, str]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=k, label=v) for k, v in options.items()],
            multiple=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _schema(defaults: dict[str, Any], *, first_setup: bool) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_REGIONS,
                default=defaults.get(CONF_REGIONS, [DEFAULT_REGION] if first_setup else []),
            ): _dropdown(REGION_OPTIONS),
            vol.Required(
                CONF_INCLUDE_TOTAL, default=defaults.get(CONF_INCLUDE_TOTAL, False)
            ): BooleanSelector(),
            vol.Required(
                CONF_THRESHOLD, default=defaults.get(CONF_THRESHOLD, DEFAULT_THRESHOLD)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.1,
                    max=100,
                    step=0.1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="%",
                )
            ),
            vol.Optional(
                CONF_TOWNS, default=defaults.get(CONF_TOWNS, [])
            ): _dropdown(TOWN_OPTIONS),
            vol.Required(
                CONF_GENERATION, default=defaults.get(CONF_GENERATION, True)
            ): BooleanSelector(),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=60,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
            vol.Optional(
                CONF_HEADERS,
                description={"suggested_value": defaults.get(CONF_HEADERS, "")},
            ): TextSelector(TextSelectorConfig(multiline=True)),
        }
    )


async def _validate(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Check the form and, if LUMA data is wanted, try one real request."""
    errors: dict[str, str] = {}
    headers_text = (user_input.get(CONF_HEADERS) or "").strip()
    options = {
        CONF_REGIONS: list(user_input.get(CONF_REGIONS, [])),
        CONF_INCLUDE_TOTAL: bool(user_input.get(CONF_INCLUDE_TOTAL, False)),
        CONF_THRESHOLD: float(user_input.get(CONF_THRESHOLD, DEFAULT_THRESHOLD)),
        CONF_TOWNS: list(user_input.get(CONF_TOWNS, [])),
        CONF_GENERATION: bool(user_input.get(CONF_GENERATION, False)),
        CONF_SCAN_INTERVAL: max(
            MIN_SCAN_INTERVAL,
            int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        ),
        CONF_HEADERS: headers_text,
    }

    wants_luma = bool(options[CONF_REGIONS] or options[CONF_INCLUDE_TOTAL])
    if not (wants_luma or options[CONF_TOWNS] or options[CONF_GENERATION]):
        errors["base"] = "nothing_selected"
        return options, errors

    try:
        headers = parse_headers(headers_text)
    except ValueError:
        errors[CONF_HEADERS] = "invalid_headers"
        return options, errors

    if wants_luma:
        client = LumaClient(async_get_clientsession(hass), headers)
        try:
            await client.async_fetch()
        except LumaApiBlockedError:
            errors["base"] = "blocked"
        except LumaApiError:
            errors["base"] = "cannot_connect"
    return options, errors


class LumaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return LumaOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            options, errors = await _validate(self.hass, user_input)
            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="LUMA Outages", data={}, options=options
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}, first_setup=True),
            errors=errors,
        )


class LumaOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            options, errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(data=options)
        defaults = user_input or dict(self.config_entry.options)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(defaults, first_setup=False),
            errors=errors,
        )
