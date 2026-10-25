"""Constantes de l'intégration Carburants."""
from datetime import timedelta

DOMAIN = "carburants"

CONF_FUEL = "fuel_type"
CONF_CITY = "city"          # identifiant 
CONF_CITY_INPUT = "city_input"
CONF_RADIUS = "radius_km"

DEFAULT_RADIUS = 10

# valeur du paramètre ?gtf=-> libellé
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36 Edg/156.0.0.0",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

SCAN_INTERVAL = timedelta(minutes=120)
TOP_N = 10
