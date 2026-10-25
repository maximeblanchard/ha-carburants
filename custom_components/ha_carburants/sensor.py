"""Capteurs : station la moins chère de la zone."""
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
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, FUELS, TOP_N
from .coordinator import CarburantCoordinator


@dataclass(frozen=True, kw_only=True)
class CarburantSensorDescription(SensorEntityDescription):
    value_fn: Callable[[list[dict]], Any]


def _best(data: list[dict], key: str) -> Any:
    return data[0][key] if data else None


def _average(data: list[dict]) -> float | None:
    return round(sum(s["prix"] for s in data) / len(data), 3) if data else None


SENSORS: tuple[CarburantSensorDescription, ...] = (
    CarburantSensorDescription(
        key="prix_min",
        name="Prix le plus bas",
        icon="mdi:gas-station",
        native_unit_of_measurement="€/L",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda d: _best(d, "prix"),
    ),
    CarburantSensorDescription(
        key="station",
        name="Station la moins chère",
        icon="mdi:map-marker",
        value_fn=lambda d: _best(d, "station"),
    ),
    CarburantSensorDescription(
        key="distance",
        name="Distance de la station",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _best(d, "distance_km"),
    ),
    CarburantSensorDescription(
        key="prix_moyen",
        name="Prix moyen de la zone",
        icon="mdi:cash",
        native_unit_of_measurement="€/L",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=_average,
    ),
    CarburantSensorDescription(
        key="nb_stations",
        name="Stations dans la zone",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=len,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: CarburantCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(CarburantSensor(coordinator, entry, d) for d in SENSORS)


class CarburantSensor(CoordinatorEntity[CarburantCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: CarburantSensorDescription

    def __init__(
        self,
        coordinator: CarburantCoordinator,
        entry: ConfigEntry,
        description: CarburantSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=(
                f"Carburant {FUELS[coordinator.fuel]} - {coordinator.city} "
                f"({int(coordinator.radius)} km)"
            ),
            manufacturer="mon-essence.fr",
            entry_type="service",
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "prix_min" or not self.coordinator.data:
            return None
        best = self.coordinator.data[0]
        return {
            "station": best["station"],
            "distance_km": best["distance_km"],
            "verification": best["verification"],
            "url": best["url"],
            "rayon_km": self.coordinator.radius,
            "classement": [
                {
                    "station": s["station"],
                    "prix": s["prix"],
                    "distance_km": s["distance_km"],
                    "verification": s["verification"],
                }
                for s in self.coordinator.data[:TOP_N]
            ],
        }
