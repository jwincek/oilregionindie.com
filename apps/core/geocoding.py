"""
Geocoding for addresses.

Primary: the US Census Geocoder (TIGER/Line data — free, no API key,
US-only, and markedly more accurate for US street addresses than OSM;
e.g. it places 210 Seneca St ~140m closer to reality than Nominatim).
Fallback: OpenStreetMap Nominatim, for anything Census can't match —
including non-US addresses, so an international fork still geocodes.

Both are polite-use APIs; callers rate-limit the batch loop.
"""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "OilRegionCreativeHub/1.0"


def _census_lookup(query):
    """(lat, lon) from the US Census geocoder, or None. US addresses only."""
    try:
        resp = httpx.get(
            CENSUS_URL,
            params={
                "address": query,
                "benchmark": "Public_AR_Current",
                "format": "json",
            },
            timeout=15,
        )
        matches = resp.json().get("result", {}).get("addressMatches", [])
        if matches:
            c = matches[0]["coordinates"]  # x = longitude, y = latitude
            return c["y"], c["x"]
    except Exception:
        logger.exception("Census geocoding failed for: %s", query)
    return None


def _nominatim_lookup(query, country):
    """(lat, lon) from Nominatim, or None."""
    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": country.lower() if country else "us",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        results = resp.json()
        if results:
            return results[0]["lat"], results[0]["lon"]
    except Exception:
        logger.exception("Nominatim geocoding failed for: %s", query)
    return None


def geocode_address(address_obj):
    """
    Geocode an Address in place (Census, then Nominatim). Returns True on
    success. Never overwrites a manually-placed pin — a human who set
    coordinates_manual deliberately corrected the geocoder, so respect it.
    Nominatim is only called when Census returns no match.
    """
    if address_obj.coordinates_manual:
        return False

    parts = [address_obj.street, address_obj.city, address_obj.state, address_obj.zip_code]
    query = ", ".join(p for p in parts if p)
    if not query:
        return False

    coords = _census_lookup(query)
    source = "census"
    if coords is None:
        coords = _nominatim_lookup(query, address_obj.country)
        source = "nominatim"

    if coords is None:
        logger.warning("No geocoding results for: %s", query)
        return False

    address_obj.latitude, address_obj.longitude = coords
    address_obj.save(update_fields=["latitude", "longitude"])
    logger.info("Geocoded (%s) %s: %s, %s",
                source, query, address_obj.latitude, address_obj.longitude)
    return True


def search_candidates(query, limit=6):
    """
    Ranked geocode candidates for the interactive picker. Uses Nominatim's
    general search, which surfaces named POIs (amenity/building/shop nodes
    a human placed on the actual building — markedly more accurate for an
    established venue than address-range interpolation) alongside plain
    address matches. Returns [{lat, lon, label, kind}], best first.

    This is deliberately picker-only: a name search can be ambiguous
    ("The Shamrock" may match a tavern in the wrong neighborhood), so a
    human confirms the pick — it is never wired into the silent pipeline.
    """
    query = (query or "").strip()
    if not query:
        return []
    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": limit, "addressdetails": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        return [
            {
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "label": r.get("display_name", ""),
                "kind": "/".join(p for p in (r.get("class"), r.get("type")) if p),
            }
            for r in resp.json()
        ]
    except Exception:
        logger.exception("Geocode search failed for: %s", query)
        return []


def geocode_all_pending():
    """
    Geocode every address that still needs it — those with no coordinates
    and not manually placed. A resolved address has a non-null latitude
    and is excluded here, so it is geocoded at most once (until its text
    changes, which clears the coordinates via Address.save and re-queues
    it). Manually-placed pins are never touched. Rate-limited.
    """
    from .models import Address

    pending = Address.objects.filter(
        latitude__isnull=True, coordinates_manual=False,
    )
    total = pending.count()
    success = 0
    for addr in pending:
        if geocode_address(addr):
            success += 1
        time.sleep(1.1)  # polite rate limit for both providers
    return success, total
