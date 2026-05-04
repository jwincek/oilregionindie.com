"""
Map views for the Oil Region Creative Hub.
Uses Leaflet.js with OpenStreetMap tiles.
"""

import json

from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def map_view(request):
    """Interactive map showing creators and venues with coordinates."""
    from apps.creators.models import CreatorProfile
    from apps.venues.models import VenueProfile

    # Venues with coordinates
    venue_markers = []
    for venue in VenueProfile.objects.filter(
        publish_status="published",
        address__isnull=False,
        address__latitude__isnull=False,
    ).select_related("address"):
        venue_markers.append({
            "lat": float(venue.address.latitude),
            "lng": float(venue.address.longitude),
            "name": venue.name,
            "type": "venue",
            "venue_type": venue.get_venue_type_display(),
            "city": venue.city,
            "url": venue.get_absolute_url(),
        })

    # Creators with coordinates
    creator_markers = []
    for creator in CreatorProfile.objects.filter(
        publish_status="published",
        address__isnull=False,
        address__latitude__isnull=False,
    ).select_related("address"):
        creator_markers.append({
            "lat": float(creator.address.latitude),
            "lng": float(creator.address.longitude),
            "name": creator.display_name,
            "type": "creator",
            "disciplines": creator.discipline_list,
            "location": creator.location,
            "url": creator.get_absolute_url(),
        })

    markers = venue_markers + creator_markers

    # Default center: Oil City, PA (or first marker)
    if markers:
        center_lat = sum(m["lat"] for m in markers) / len(markers)
        center_lng = sum(m["lng"] for m in markers) / len(markers)
    else:
        center_lat, center_lng = 41.434, -79.7025

    return render(request, "core/map.html", {
        "markers_json": json.dumps(markers),
        "center_lat": center_lat,
        "center_lng": center_lng,
        "venue_count": len(venue_markers),
        "creator_count": len(creator_markers),
    })
