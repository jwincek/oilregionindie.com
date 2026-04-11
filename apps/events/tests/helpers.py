"""
Shared test helpers for the events app.

Reuses factories from creators and venues helpers, adds event-specific ones.
"""

from datetime import time, timedelta

from django.utils import timezone

from apps.creators.tests.helpers import make_creator, make_user  # noqa: F401
from apps.venues.tests.helpers import make_venue, make_venue_area, make_venue_contact  # noqa: F401

from apps.events.models import BookingRequest, Event, EventSlot


def make_event(
    created_by=None,
    title="Test Event",
    is_published=True,
    start_datetime=None,
    venue=None,
    **kwargs,
):
    """Create an Event with sensible defaults."""
    if created_by is None:
        created_by = make_user()
    if start_datetime is None:
        # Default to 7 days in the future so listing view picks it up
        start_datetime = timezone.now() + timedelta(days=7)
    defaults = {
        "title": title,
        "is_published": is_published,
        "event_type": Event.EventType.CONCERT,
        "is_free": True,
        "venue": venue,
    }
    defaults.update(kwargs)
    return Event.objects.create(
        created_by=created_by, start_datetime=start_datetime, **defaults
    )


def make_past_event(created_by=None, title="Past Event", **kwargs):
    """Create an event in the past."""
    return make_event(
        created_by=created_by,
        title=title,
        start_datetime=timezone.now() - timedelta(days=30),
        **kwargs,
    )


def make_event_slot(event, creator, **kwargs):
    """Create an EventSlot linking a creator to an event."""
    defaults = {
        "sort_order": 0,
        "status": EventSlot.Status.CONFIRMED,
    }
    defaults.update(kwargs)
    return EventSlot.objects.create(event=event, creator=creator, **defaults)


def make_booking_request(
    creator,
    venue,
    initiated_by=None,
    direction=BookingRequest.Direction.CREATOR_TO_VENUE,
    **kwargs,
):
    """Create a BookingRequest."""
    if initiated_by is None:
        if direction == BookingRequest.Direction.CREATOR_TO_VENUE:
            initiated_by = creator.user
        else:
            initiated_by = venue.user
    defaults = {
        "event_type": Event.EventType.CONCERT,
        "preferred_dates": "Any Friday in July",
        "message": "We'd love to play at your venue.",
        "status": BookingRequest.Status.PENDING,
    }
    defaults.update(kwargs)
    return BookingRequest.objects.create(
        creator=creator,
        venue=venue,
        initiated_by=initiated_by,
        direction=direction,
        **defaults,
    )
