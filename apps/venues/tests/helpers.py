"""
Shared test helpers for the venues app.

Reuses make_user from the creators test helpers and adds
venue-specific factory functions.
"""

from apps.creators.tests.helpers import make_user  # noqa: F401 — re-exported

from apps.venues.models import (
    Amenity,
    VenueArea,
    VenueContact,
    VenueProfile,
    VenueSocialLink,
)
from apps.core.models import Address, SocialPlatform


def make_amenity(name="PA System", **kwargs):
    """Create or retrieve an Amenity."""
    obj, _ = Amenity.objects.get_or_create(name=name, defaults=kwargs)
    return obj


def make_address(city="Oil City", state="PA", street="123 Seneca St", zip_code="16301", **kwargs):
    """Create an Address."""
    return Address.objects.create(
        city=city, state=state, street=street, zip_code=zip_code, **kwargs
    )


def make_venue(user=None, name="Test Venue", is_published=True, **kwargs):
    """Create a VenueProfile with sensible defaults including an Address."""
    if user is None:
        user = make_user()
    # Create an Address if one isn't provided
    if "address" not in kwargs:
        kwargs["address"] = make_address(
            city=kwargs.pop("city", "Oil City"),
            state=kwargs.pop("state", "PA"),
            street=kwargs.pop("street", "123 Seneca St"),
            zip_code=kwargs.pop("zip_code", "16301"),
        )
    # Sync city/state onto the venue for legacy query fields
    city = kwargs.get("city", kwargs["address"].city if kwargs.get("address") else "Oil City")
    state = kwargs.get("state", kwargs["address"].state if kwargs.get("address") else "PA")
    defaults = {
        "name": name,
        "is_published": is_published,
        "venue_type": VenueProfile.VenueType.BAR,
        "city": city,
        "state": state,
    }
    defaults.update(kwargs)
    return VenueProfile.objects.create(user=user, **defaults)


def make_venue_contact(
    venue,
    contact_type=VenueContact.ContactType.BOOKING,
    method=VenueContact.Method.EMAIL,
    value="booking@example.com",
    **kwargs,
):
    """Create a VenueContact."""
    return VenueContact.objects.create(
        venue=venue, contact_type=contact_type, method=method, value=value, **kwargs
    )


def make_venue_area(venue, name="Main Stage", **kwargs):
    """Create a VenueArea within a venue."""
    return VenueArea.objects.create(venue=venue, name=name, **kwargs)


def make_venue_social_link(venue, platform=SocialPlatform.FACEBOOK, url="https://facebook.com/example", **kwargs):
    """Create a VenueSocialLink."""
    return VenueSocialLink.objects.create(
        venue=venue, platform=platform, url=url, **kwargs
    )
