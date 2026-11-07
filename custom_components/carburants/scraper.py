"""Lecture des prix collaboratifs"""
from __future__ import annotations

import html as html_lib
import json
import re
import unicodedata
from typing import Any
from urllib.parse import quote_plus, urljoin

import aiohttp

from .const import BASE_URL, HEADERS

TIMEOUT = aiohttp.ClientTimeout(total=30)

# Une fiche station = un lien <a href=".../station/<ville>/<station>"> qui
# contient le nom, la distance (« 1,4 km »), le prix (« 2,250 € ») et l'état.
CARD_RE = re.compile(
    r'<a\b[^>]*?href="(?P<href>[^"]*?/station/[^"/]+/[^"/?#]+[^"]*)"[^>]*>(?P<body>.*?)</a>',
    re.S | re.I,
)
TAG_RE = re.compile(r"<[^>]+>")
KM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*km", re.I)
PRICE_RE = re.compile(r"(\d[.,]\d{3})\s*€")
LD_JSON_RE = re.compile(
    r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>\s*(\{.*?\})\s*</script>',
    re.S | re.I,
)
APPLE_MAPS_RE = re.compile(
    r"maps\.apple\.com/\?q=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
    re.I,
)


class CityNotFound(Exception):
    """La page ville n'existe pas."""


class PageFormatError(Exception):
    """Aucune fiche station reconnue dans la page."""


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def parse_city_ref(value: str) -> str | None:
    """Accepte une ville."""
    value = value.strip().lower()
    m = re.search(r"/ville/(\d+-[a-z0-9-]+)", value) or re.fullmatch(
        r"(\d+-[a-z0-9-]+)", value
    )
    return m.group(1) if m else None


async def resolve_city(session: aiohttp.ClientSession, text: str) -> str | None:
    """Nom de ville."""
    ref = parse_city_ref(text)
    if ref:
        return ref
    slug = slugify(text)
    if not slug:
        return None
    async with session.get(
        f"{BASE_URL}/recherche/", params={"q": slug}, headers=HEADERS, timeout=TIMEOUT
    ) as resp:
        resp.raise_for_status()
        m = re.search(r"/ville/(\d+-[a-z0-9-]+)", str(resp.url))
        if m:
            return m.group(1)
        body = await resp.text()
    for candidate in re.findall(r"/ville/(\d+-[a-z0-9-]+)", body):
        if candidate.endswith(f"-{slug}"):
            return candidate
    return None


def build_google_maps_url(
    station_name: str,
    latitude: float | None = None,
    longitude: float | None = None,
    address: str | None = None,
) -> str:
    """Construit l'URL universelle d'itinéraire Google Maps (ouvre l'app GPS sur mobile)."""
    if latitude is not None and longitude is not None:
        return f"https://www.google.com/maps/dir/?api=1&destination={latitude},{longitude}"
    query = f"{station_name}, {address}" if address else station_name
    return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(query)}"


def build_waze_url(
    station_name: str,
    latitude: float | None = None,
    longitude: float | None = None,
) -> str:
    """Construit l'URL universelle de navigation Waze."""
    if latitude is not None and longitude is not None:
        return f"https://waze.com/ul?ll={latitude},{longitude}&navigate=yes"
    return f"https://waze.com/ul?q={quote_plus(station_name)}&navigate=yes"


def parse_stations(page: str) -> list[dict[str, Any]]:
    """Extrait les stations (avec prix) de la page ville."""
    stations: list[dict[str, Any]] = []
    seen: set[str] = set()
    cards = 0
    for m in CARD_RE.finditer(page):
        href = m.group("href")
        if href in seen:
            continue
        seen.add(href)
        text = html_lib.unescape(TAG_RE.sub(" ", m.group("body")))
        text = re.sub(r"\s+", " ", text).strip()
        km = KM_RE.search(text)
        if not km:
            continue
        cards += 1
        price = PRICE_RE.search(text, km.end())
        if not price:  # pénurie / indisponible
            continue
        name = re.sub(r"^Enseigne\s+", "", text[: km.start()]).strip()
        status = text[price.end():].strip()
        stations.append(
            {
                "station": name,
                "prix": float(price.group(1).replace(",", ".")),
                "distance_km": float(km.group(1).replace(",", ".")),
                "verification": status or None,
                "url": urljoin(BASE_URL, href),
                "adresse": None,
                "latitude": None,
                "longitude": None,
                "google_maps_url": build_google_maps_url(name),
                "waze_url": build_waze_url(name),
            }
        )
    if not cards:
        raise PageFormatError("aucune fiche station reconnue")
    return stations


def parse_station_details(page: str) -> dict[str, Any]:
    """Extrait les coordonnées GPS et l'adresse depuis la page d'une station."""
    latitude: float | None = None
    longitude: float | None = None
    address_str: str | None = None

    for match in LD_JSON_RE.finditer(page):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        geo = data.get("geo")
        if isinstance(geo, dict):
            try:
                if geo.get("latitude") is not None and geo.get("longitude") is not None:
                    latitude = float(geo["latitude"])
                    longitude = float(geo["longitude"])
            except (TypeError, ValueError):
                pass
        addr = data.get("address")
        if isinstance(addr, dict):
            street = (addr.get("streetAddress") or "").strip()
            postal = (addr.get("postalCode") or "").strip()
            city = (addr.get("addressLocality") or "").strip()
            city_line = " ".join(part for part in (postal, city) if part)
            full_addr = ", ".join(part for part in (street, city_line) if part)
            if full_addr:
                address_str = full_addr
        if latitude is not None and longitude is not None:
            break

    if latitude is None or longitude is None:
        m = APPLE_MAPS_RE.search(page)
        if m:
            try:
                latitude = float(m.group(1))
                longitude = float(m.group(2))
            except ValueError:
                pass

    return {
        "adresse": address_str,
        "latitude": latitude,
        "longitude": longitude,
    }


async def enrich_station_details(
    session: aiohttp.ClientSession, station: dict[str, Any]
) -> None:
    """Enrichit une station avec ses coordonnées GPS et liens d'itinéraire précis."""
    url = station.get("url")
    if not url:
        return
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return
            page = await resp.text()
    except (aiohttp.ClientError, TimeoutError):
        return

    details = parse_station_details(page)
    lat = details["latitude"]
    lon = details["longitude"]
    addr = details["adresse"]

    station["adresse"] = addr
    station["latitude"] = lat
    station["longitude"] = lon
    station["google_maps_url"] = build_google_maps_url(
        station["station"], latitude=lat, longitude=lon, address=addr
    )
    station["waze_url"] = build_waze_url(
        station["station"], latitude=lat, longitude=lon
    )


async def fetch_stations(
    session: aiohttp.ClientSession, city_ref: str, fuel: str
) -> list[dict[str, Any]]:
    """Stations de la page ville pour ce carburant (toutes distances)."""
    async with session.get(
        f"{BASE_URL}/ville/{city_ref}",
        params={"q": "", "gtf": fuel, "sort_by": "price"},
        headers=HEADERS,
        timeout=TIMEOUT,
    ) as resp:
        if resp.status == 404:
            raise CityNotFound(city_ref)
        resp.raise_for_status()
        page = await resp.text()
    return parse_stations(page)


def within_radius(stations: list[dict[str, Any]], radius_km: float) -> list[dict[str, Any]]:
    close = [s for s in stations if s["distance_km"] <= radius_km]
    close.sort(key=lambda s: (s["prix"], s["distance_km"]))
    return close
