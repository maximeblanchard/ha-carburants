"""Config flow : ville, carburant, rayon en km."""
from __future__ import annotations

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_CITY,
    CONF_CITY_INPUT,
    CONF_FUEL,
    CONF_RADIUS,
    DEFAULT_RADIUS,
    DOMAIN,
    FUELS,
)
from .scraper import (
    CityNotFound,
    PageFormatError,
    fetch_stations,
    resolve_city,
    within_radius,
)


class CarburantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        user_input = user_input or {}

        if CONF_CITY_INPUT in user_input:
            session = async_get_clientsession(self.hass)
            fuel = user_input[CONF_FUEL]
            radius = float(user_input[CONF_RADIUS])
            try:
                city_ref = await resolve_city(session, user_input[CONF_CITY_INPUT])
                if city_ref is None:
                    errors["base"] = "city_not_found"
                else:
                    stations = await fetch_stations(session, city_ref, fuel)
                    if not stations:
                        errors["base"] = "no_stations"
                    elif not within_radius(stations, radius):
                        errors["base"] = "no_stations_in_radius"
            except CityNotFound:
                errors["base"] = "city_not_found"
            except PageFormatError:
                errors["base"] = "parse_error"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"

            if not errors:
                await self.async_set_unique_id(f"{city_ref}_{fuel}_{int(radius)}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{FUELS[fuel]} - {city_ref} ({int(radius)} km)",
                    data={CONF_CITY: city_ref, CONF_FUEL: fuel, CONF_RADIUS: radius},
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CITY_INPUT, default=user_input.get(CONF_CITY_INPUT, "")
                ): str,
                vol.Required(
                    CONF_FUEL, default=user_input.get(CONF_FUEL, "sp95_e10")
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[{"value": k, "label": v} for k, v in FUELS.items()],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_RADIUS, default=user_input.get(CONF_RADIUS, DEFAULT_RADIUS)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=50,
                        step=1,
                        unit_of_measurement="km",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
