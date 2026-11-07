"""Coordinator de mise à jour."""
from __future__ import annotations

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_CITY, CONF_FUEL, CONF_RADIUS, DOMAIN, SCAN_INTERVAL
from .scraper import (
    CityNotFound,
    PageFormatError,
    enrich_station_details,
    fetch_stations,
    within_radius,
)

_LOGGER = logging.getLogger(__name__)


class CarburantCoordinator(DataUpdateCoordinator[list[dict]]):
    """Stations de la zone, triées par prix (la moins chère en premier)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.entry = entry
        self.city: str = entry.data[CONF_CITY]
        self.fuel: str = entry.data[CONF_FUEL]
        self.radius: float = float(entry.data[CONF_RADIUS])
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> list[dict]:
        try:
            stations = await fetch_stations(self._session, self.city, self.fuel)
        except (aiohttp.ClientError, TimeoutError, CityNotFound) as err:
            raise UpdateFailed(f"Erreur de récupération : {err}") from err
        except PageFormatError as err:
            raise UpdateFailed(
                "Page API illisible"
            ) from err
        # liste vide possible : pénurie dans la zone -> capteurs sans valeur
        close = within_radius(stations, self.radius)
        if close:
            await enrich_station_details(self._session, close[0])
            maps_url = close[0].get("google_maps_url")
            if maps_url:
                dev_reg = dr.async_get(self.hass)
                device = dev_reg.async_get_device(
                    identifiers={(DOMAIN, self.entry.entry_id)}
                )
                if device and device.configuration_url != maps_url:
                    dev_reg.async_update_device(
                        device.id, configuration_url=maps_url
                    )
        return close
