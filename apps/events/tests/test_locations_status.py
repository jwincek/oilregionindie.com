"""
Off-platform event locations (issue #17) and lifecycle status (issue #20).

Events not at a listed venue carry a freeform location_name, optionally
with an address whose presence gates the public directions link (house
shows simply omit it). Cancelled/postponed events stay listed with a
badge, and followers of the organizing profiles get notified.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Address, Notification
from apps.events.forms import EventForm
from apps.events.models import Event

from .helpers import make_creator, make_event, make_user, make_venue


def form_data(**overrides):
    base = {
        "title": "Fair on Seneca",
        "event_type": Event.EventType.MARKET,
        "start_datetime": "2026-09-01T15:00",
        "is_free": "on",
        "is_published": "on",
    }
    base.update(overrides)
    return base


class EventLocationFormTest(TestCase):
    def test_location_only_is_valid_with_scheduled_default(self):
        form = EventForm(data=form_data(location_name="Seneca Street, Oil City"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["status"], Event.Status.SCHEDULED)

    def test_venue_and_location_together_invalid(self):
        venue = make_venue(user=make_user())
        form = EventForm(data=form_data(
            venue=str(venue.pk), location_name="Somewhere Else",
        ))
        self.assertFalse(form.is_valid())
        self.assertIn("not both", str(form.errors))

    def test_address_without_location_name_invalid(self):
        form = EventForm(data=form_data(location_street="123 Elm St"))
        self.assertFalse(form.is_valid())

    def test_address_fields_create_address_on_save(self):
        form = EventForm(data=form_data(
            location_name="Justus Park",
            location_street="200 Elm St",
            location_city="Oil City",
            location_state="PA",
        ))
        self.assertTrue(form.is_valid(), form.errors)
        event = form.save(commit=False)
        event.created_by = make_user()
        event.save()
        # save(commit=False) defers the address attach; run full save path
        form.instance.created_by = event.created_by
        event = form.save()
        self.assertIsNotNone(event.location_address)
        self.assertEqual(event.location_address.city, "Oil City")
        self.assertIn("Justus", event.location_display)
        self.assertIn("google.com/maps", event.directions_url)


class EventLocationModelTest(TestCase):
    def test_constraint_rejects_venue_plus_location(self):
        venue = make_venue(user=make_user())
        event = Event(
            title="Bad", slug="bad-event", created_by=make_user(),
            start_datetime=timezone.now(), venue=venue,
            location_name="Also a place",
        )
        with self.assertRaises(ValidationError):
            event.full_clean()

    def test_directions_url_empty_without_address(self):
        event = make_event(location_name="Secret House Show")
        self.assertEqual(event.directions_url, "")

    def test_directions_url_uses_venue_address_for_venue_events(self):
        venue = make_venue(user=make_user())
        venue.address.latitude, venue.address.longitude = 41.4347, -79.7088
        venue.address.save()
        event = make_event(venue=venue)
        self.assertEqual(event.directions_url, venue.address.directions_url)
        self.assertIn("41.4347", event.directions_url)


class EventLocationRenderTest(TestCase):
    def test_detail_shows_location_and_directions_when_address(self):
        addr = Address.objects.create(street="200 Elm St", city="Oil City", state="PA")
        event = make_event(location_name="Justus Park", location_address=addr)
        r = self.client.get(event.get_absolute_url())
        self.assertContains(r, "Justus Park")
        self.assertContains(r, "Get directions")

    def test_detail_hides_directions_without_address(self):
        event = make_event(location_name="A Friend's Porch")
        r = self.client.get(event.get_absolute_url())
        self.assertContains(r, "A Friend&#x27;s Porch")
        self.assertNotContains(r, "Get directions")

    def test_listing_shows_location_name(self):
        make_event(title="Street Fair", location_name="Seneca Street")
        r = self.client.get(reverse("events:listing"))
        self.assertContains(r, "Seneca Street")


class EventStatusTest(TestCase):
    def test_cancelled_event_stays_listed_with_badge(self):
        make_event(title="Rained Out Show", status=Event.Status.CANCELLED)
        r = self.client.get(reverse("events:listing"))
        self.assertContains(r, "Rained Out Show")
        self.assertContains(r, "Cancelled")

    def test_detail_shows_postponed_badge(self):
        event = make_event(status=Event.Status.POSTPONED)
        r = self.client.get(event.get_absolute_url())
        self.assertContains(r, "Postponed")

    def test_cancelling_notifies_followers_once(self):
        owner = make_user()
        organizer = make_creator(user=make_user(), display_name="The Organizers")
        event = make_event(created_by=owner, organizing_creator=organizer)
        fan = make_user()
        fan.profile.followed_creators.add(organizer)

        self.client.force_login(owner)
        url = reverse("events:edit", kwargs={"slug": event.slug})
        r = self.client.post(url, form_data(
            title=event.title, status=Event.Status.CANCELLED,
        ))
        self.assertEqual(r.status_code, 302)
        notes = Notification.objects.filter(
            recipient=fan, notification_type=Notification.NotificationType.EVENT,
        )
        self.assertEqual(notes.count(), 1)
        self.assertIn("cancelled", notes.first().message)

        # Saving again with the same status must not re-notify.
        self.client.post(url, form_data(
            title=event.title, status=Event.Status.CANCELLED,
        ))
        self.assertEqual(notes.count(), 1)


class EventLocationAddressStaleCoordinateTest(TestCase):
    """Editing an event's off-venue address text must clear coordinates
    that describe the old place — the same rule that applies to venue
    addresses (apps/venues/tests/test_forms.py)."""

    def test_editing_location_street_clears_stale_coordinates(self):
        owner = make_user()
        addr = Address.objects.create(street="210 Seneca St", city="Oil City", state="PA")
        addr.latitude, addr.longitude = 41.4352, -79.7089
        addr.save()
        event = make_event(
            created_by=owner, location_name="Old Spot", location_address=addr,
        )

        form = EventForm(data=form_data(
            title=event.title, location_name="Old Spot",
            location_street="500 Washington Ave", location_city="Oil City",
            location_state="PA",
        ), instance=event)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        addr.refresh_from_db()
        self.assertFalse(addr.has_coordinates)
