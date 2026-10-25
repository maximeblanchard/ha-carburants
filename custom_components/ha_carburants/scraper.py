"""Lecture des prix collaboratifs sur mon-essence.fr."""
from __future__ import annotations

import html as html_lib
import re
import unicodedata
from typing import Any
from urllib.parse import urljoin

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


class CityNotFound(Exception):
    """La page ville n'existe pas."""


class PageFormatError(Exception):
    """Aucune fiche station reconnue dans la page."""


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def parse_city_ref(value: str) -> str | None:
    """Accepte une URL mon-essence ou un identifiant « 28508-le-mans »."""
    value = value.strip().lower()
    m = re.search(r"/ville/(\d+-[a-z0-9-]+)", value) or re.fullmatch(
        r"(\d+-[a-z0-9-]+)", value
    )
    return m.group(1) if m else None


async def resolve_city(session: aiohttp.ClientSession, text: str) -> str | None:
    """Nom de ville / URL / identifiant -> identifiant mon-essence."""
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
            }
        )
    if not cards:
        raise PageFormatError("aucune fiche station reconnue")
    return stations


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
