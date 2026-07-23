"""
schema.org structured data (JSON-LD) builders for the SEO-relevant
models: events, venues, creators. Kept out of the models so the SEO
shape lives in one place; rendered via the {% structured_data_script %}
template tag.

Absolute URLs use WAGTAILADMIN_BASE_URL (the site's canonical base),
so no request is needed.
"""

from django.conf import settings
from django.utils.html import strip_tags


def site_url(path):
    return settings.WAGTAILADMIN_BASE_URL.rstrip("/") + (path or "")


def _image(img):
    return site_url(img.url) if img else None


def _postal(addr):
    p = {"@type": "PostalAddress"}
    if addr.street:
        p["streetAddress"] = addr.street
    if addr.city:
        p["addressLocality"] = addr.city
    if addr.state:
        p["addressRegion"] = addr.state
    if addr.zip_code:
        p["postalCode"] = addr.zip_code
    p["addressCountry"] = addr.country or "US"
    return p


def _geo(addr):
    return {
        "@type": "GeoCoordinates",
        "latitude": float(addr.latitude),
        "longitude": float(addr.longitude),
    }


def _same_as(profile):
    """sameAs: the profile's website plus every social/Google-Business link
    — tells search engines these external profiles are the same entity."""
    links = []
    if getattr(profile, "website", ""):
        links.append(profile.website)
    links += [link.url for link in profile.social_links.all()]
    return links


def event_ld(event):
    concert_types = {"concert", "open_mic", "festival"}
    data = {
        "@context": "https://schema.org",
        "@type": "MusicEvent" if event.event_type in concert_types else "Event",
        "name": event.title,
        "startDate": event.start_datetime.isoformat(),
        "url": site_url(event.get_absolute_url()),
        "eventStatus": {
            "scheduled": "https://schema.org/EventScheduled",
            "cancelled": "https://schema.org/EventCancelled",
            "postponed": "https://schema.org/EventPostponed",
        }.get(event.status, "https://schema.org/EventScheduled"),
    }
    if event.end_datetime:
        data["endDate"] = event.end_datetime.isoformat()
    if event.description:
        data["description"] = strip_tags(event.description)[:300]
    if event.poster_image:
        data["image"] = _image(event.poster_image)

    if event.is_virtual:
        data["eventAttendanceMode"] = "https://schema.org/OnlineEventAttendanceMode"
        if event.stream_url:
            data["location"] = {"@type": "VirtualLocation", "url": event.stream_url}
    else:
        data["eventAttendanceMode"] = "https://schema.org/OfflineEventAttendanceMode"
        loc = {"@type": "Place", "name": event.location_display}
        addr = event.map_address
        if addr:
            loc["address"] = _postal(addr)
            if addr.has_coordinates:
                loc["geo"] = _geo(addr)
        data["location"] = loc

    if event.is_free:
        data["isAccessibleForFree"] = True
    elif event.ticket_price_cents:
        offer = {
            "@type": "Offer",
            "price": f"{event.ticket_price_cents / 100:.2f}",
            "priceCurrency": "USD",
        }
        if event.ticket_url:
            offer["url"] = event.ticket_url
        data["offers"] = offer

    performers = []
    for slot in event.lineup:
        if slot.creator:
            performers.append({
                "@type": "MusicGroup" if slot.creator.is_group else "Person",
                "name": slot.creator.display_name,
                "url": site_url(slot.creator.get_absolute_url()),
            })
        elif slot.guest_name:
            performers.append({"@type": "PerformingGroup", "name": slot.guest_name})
    if performers:
        data["performer"] = performers

    organizer = event.organizing_creator or event.organizing_venue
    if organizer:
        data["organizer"] = {
            "@type": "MusicGroup" if getattr(organizer, "is_group", False) else "Organization",
            "name": getattr(organizer, "display_name", None) or getattr(organizer, "name", ""),
            "url": site_url(organizer.get_absolute_url()),
        }
    return data


def venue_ld(venue):
    schema_type = {
        "gallery": "ArtGallery",
        "cafe": "CafeOrCoffeeShop",
        "theater": "PerformingArtsTheater",
    }.get(venue.venue_type, "MusicVenue")
    data = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "name": venue.name,
        "url": site_url(venue.get_absolute_url()),
    }
    if venue.address:
        data["address"] = _postal(venue.address)
        if venue.address.has_coordinates:
            data["geo"] = _geo(venue.address)
    if venue.profile_image:
        data["image"] = _image(venue.profile_image)
    if venue.description:
        data["description"] = strip_tags(venue.description)[:300]
    same = _same_as(venue)
    if same:
        data["sameAs"] = same
    if venue.capacity:
        data["maximumAttendeeCapacity"] = venue.capacity
    return data


def creator_ld(creator):
    data = {
        "@context": "https://schema.org",
        "@type": "MusicGroup" if creator.is_group else "Person",
        "name": creator.display_name,
        "url": site_url(creator.get_absolute_url()),
    }
    if creator.profile_image:
        data["image"] = _image(creator.profile_image)
    if creator.bio:
        data["description"] = strip_tags(creator.bio)[:300]
    genres = [g.name for g in creator.genres.all()]
    if genres:
        data["genre"] = genres
    same = _same_as(creator)
    if same:
        data["sameAs"] = same
    return data


def structured_data(obj):
    """Dispatch to the right builder by model type; None for unsupported."""
    from apps.creators.models import CreatorProfile
    from apps.events.models import Event
    from apps.venues.models import VenueProfile

    if isinstance(obj, Event):
        return event_ld(obj)
    if isinstance(obj, VenueProfile):
        return venue_ld(obj)
    if isinstance(obj, CreatorProfile):
        return creator_ld(obj)
    return None
