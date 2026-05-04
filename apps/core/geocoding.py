"""
Geocoding using OpenStreetMap's Nominatim API.
Free, no API key required, but rate-limited to 1 request per second.
"""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "OilRegionCreativeHub/1.0"


def geocode_address(address_obj):
    """
    Geocode an Address object using Nominatim.
    Updates latitude/longitude in place. Returns True if successful.
    """
    parts = [address_obj.street, address_obj.city, address_obj.state, address_obj.zip_code]
    query = ", ".join(p for p in parts if p)

    if not query:
        return False

    try:
        response = httpx.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": address_obj.country.lower() if address_obj.country else "us",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        results = response.json()

        if results:
            address_obj.latitude = results[0]["lat"]
            address_obj.longitude = results[0]["lon"]
            address_obj.save(update_fields=["latitude", "longitude"])
            logger.info("Geocoded %s: %s, %s", query, address_obj.latitude, address_obj.longitude)
            return True
        else:
            logger.warning("No geocoding results for: %s", query)
            return False

    except Exception:
        logger.exception("Geocoding failed for: %s", query)
        return False


def geocode_all_pending():
    """Geocode all addresses that don't have coordinates yet. Rate-limited."""
    from .models import Address

    pending = Address.objects.filter(latitude__isnull=True)
    total = pending.count()
    success = 0

    for addr in pending:
        if geocode_address(addr):
            success += 1
        # Nominatim rate limit: max 1 request per second
        time.sleep(1.1)

    return success, total
