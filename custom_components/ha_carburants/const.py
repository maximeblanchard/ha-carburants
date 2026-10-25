"""Constantes de l'intégration HA Carburants."""
from datetime import timedelta

DOMAIN = "ha_carburants"

CONF_FUEL = "fuel_type"
CONF_CITY = "city"          # identifiant mon-essence, ex. "28508-le-mans"
CONF_CITY_INPUT = "city_input"
CONF_RADIUS = "radius_km"

DEFAULT_RADIUS = 10

# valeur du paramètre ?gtf= de mon-essence.fr -> libellé
FUELS = {
    "go": "Gazole",
    "sp95_e10": "SP95-E10",
    "sp95": "SP95",
    "sp98": "SP98",
    "e85": "E85",
    "gpl": "GPL",
}

BASE_URL = "https://mon-essence.fr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HomeAssistant ha-carburants)",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

SCAN_INTERVAL = timedelta(minutes=30)
TOP_N = 10
