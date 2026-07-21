"""
Map views for the Oil Region Creative Hub.
Uses Leaflet.js with OpenStreetMap tiles.
"""

import json
from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.views.decorators.http import require_GET

# How far ahead events are shown — far enough to plan around, not so far
# that something six months out clutters the map next to tonight's show.
EVENT_WINDOW_DAYS = 30
UPCOMING_EVENTS_PER_VENUE = 5


def _display_date(dt):
    return format_date(timezone.localtime(dt), "D, M j, g:i A")


@require_GET
def map_view(request):
    """Interactive map showing creators, venues, and off-venue events
    with coordinates."""
    from apps.creators.models import CreatorProfile
    from apps.events.models import Event
    from apps.venues.models import VenueProfile

    now = timezone.now()
    window_end = now + timedelta(days=EVENT_WINDOW_DAYS)

    venues = list(VenueProfile.objects.filter(
        publish_status="published",
        address__isnull=False,
        address__latitude__isnull=False,
    ).select_related("address"))

    # One query for every venue's upcoming shows, grouped in Python —
    # avoids an N+1 query per venue marker. Matches the venue detail
    # page's own filtering (published, upcoming); cancelled/postponed
    # events stay in the list (with their badge) rather than vanishing,
    # same philosophy as everywhere else status is shown.
    upcoming_by_venue = {}
    venue_events = Event.objects.filter(
        is_published=True,
        start_datetime__gte=now,
        venue_id__in=[v.pk for v in venues],
    ).order_by("start_datetime")
    for event in venue_events:
        upcoming_by_venue.setdefault(event.venue_id, []).append({
            "title": event.title,
            "url": event.get_absolute_url(),
            "date": _display_date(event.start_datetime),
            "status": event.status,
        })

    venue_markers = []
    for venue in venues:
        venue_markers.append({
            "lat": float(venue.address.latitude),
            "lng": float(venue.address.longitude),
            "name": venue.name,
            "type": "venue",
            "venue_type": venue.get_venue_type_display(),
            "city": venue.city,
            "url": venue.get_absolute_url(),
            "upcoming_events": upcoming_by_venue.get(venue.pk, [])[:UPCOMING_EVENTS_PER_VENUE],
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

    # Off-venue events (street fairs, house shows, pop-up crawls) get
    # their own pin. Events at a listed venue are deliberately NOT
    # duplicated here — they already sit in that venue's own pin via
    # upcoming_events, so a busy venue doesn't get a pile of markers
    # stacked exactly on top of it.
    event_markers = []
    for event in Event.objects.filter(
        is_published=True,
        venue__isnull=True,
        location_address__isnull=False,
        location_address__latitude__isnull=False,
        start_datetime__gte=now,
        start_datetime__lte=window_end,
    ).select_related("location_address").order_by("start_datetime"):
        event_markers.append({
            "lat": float(event.location_address.latitude),
            "lng": float(event.location_address.longitude),
            "name": event.title,
            "type": "event",
            "event_type": event.get_event_type_display(),
            "date": _display_date(event.start_datetime),
            "location_name": event.location_name,
            "status": event.status,
            "url": event.get_absolute_url(),
        })

    markers = venue_markers + creator_markers + event_markers

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
        "event_count": len(event_markers),
    })
