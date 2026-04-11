"""
Tests for events app views.

Covers: listing (upcoming only, filters, HTMX), detail, past events,
create (login, created_by auto-set, organizing_creator auto-set),
edit (permission checking via all three paths).
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event

from .helpers import (
    make_creator,
    make_event,
    make_past_event,
    make_user,
    make_venue,
)


# ---------------------------------------------------------------------------
# Listing view (upcoming events)
# ---------------------------------------------------------------------------


class EventListingViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("events:listing")
        cls.user = make_user()

        cls.venue_oc = make_venue(name="Billy's", city="Oil City", state="PA")
        cls.venue_franklin = make_venue(name="The Brewhouse", city="Franklin", state="PA")

        cls.concert = make_event(
            created_by=cls.user,
            title="Friday Night Concert",
            event_type=Event.EventType.CONCERT,
            venue=cls.venue_oc,
        )
        cls.market = make_event(
            created_by=cls.user,
            title="Holiday Maker Market",
            event_type=Event.EventType.MARKET,
            venue=cls.venue_franklin,
        )
        cls.unpublished = make_event(
            created_by=cls.user,
            title="Secret Show",
            is_published=False,
        )
        cls.past = make_past_event(
            created_by=cls.user,
            title="Last Month's Show",
        )

    def test_listing_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/listing.html")

    def test_shows_upcoming_events(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Friday Night Concert")
        self.assertContains(response, "Holiday Maker Market")

    def test_excludes_unpublished(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "Secret Show")

    def test_excludes_past_events(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "Last Month")

    def test_filter_by_event_type(self):
        response = self.client.get(self.url, {"type": "market"})
        self.assertContains(response, "Holiday Maker Market")
        self.assertNotContains(response, "Friday Night Concert")

    def test_filter_by_location(self):
        response = self.client.get(self.url, {"location": "Franklin"})
        self.assertContains(response, "Holiday Maker Market")
        self.assertNotContains(response, "Friday Night Concert")

    def test_search_by_title(self):
        response = self.client.get(self.url, {"q": "Maker"})
        self.assertContains(response, "Holiday Maker Market")
        self.assertNotContains(response, "Friday Night Concert")

    def test_empty_results(self):
        response = self.client.get(self.url, {"q": "zzzznonexistent"})
        self.assertContains(response, "No upcoming events")

    def test_htmx_returns_partial(self):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/_event_list.html")


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------


class EventDetailViewTest(TestCase):
    def test_published_event_loads(self):
        event = make_event(title="Visible Event")
        response = self.client.get(
            reverse("events:detail", kwargs={"slug": event.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Event")

    def test_unpublished_event_returns_404(self):
        event = make_event(title="Hidden", is_published=False)
        response = self.client.get(
            reverse("events:detail", kwargs={"slug": event.slug})
        )
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_slug_returns_404(self):
        response = self.client.get(
            reverse("events:detail", kwargs={"slug": "no-such-event"})
        )
        self.assertEqual(response.status_code, 404)

    def test_shows_venue_info(self):
        venue = make_venue(name="The Nickel", city="Oil City")
        event = make_event(title="Show at Nickel", venue=venue)
        response = self.client.get(
            reverse("events:detail", kwargs={"slug": event.slug})
        )
        self.assertContains(response, "The Nickel")

    def test_shows_free_badge(self):
        event = make_event(title="Free Show", is_free=True)
        response = self.client.get(
            reverse("events:detail", kwargs={"slug": event.slug})
        )
        self.assertContains(response, "Free")

    def test_shows_ticket_price(self):
        event = make_event(title="Paid Show", is_free=False, ticket_price_cents=1000)
        response = self.client.get(
            reverse("events:detail", kwargs={"slug": event.slug})
        )
        self.assertContains(response, "$10.00")


# ---------------------------------------------------------------------------
# Past events view
# ---------------------------------------------------------------------------


class PastEventsViewTest(TestCase):
    def setUp(self):
        self.url = reverse("events:past")

    def test_past_view_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/past.html")

    def test_shows_past_events(self):
        make_past_event(title="Old Festival")
        response = self.client.get(self.url)
        self.assertContains(response, "Old Festival")

    def test_excludes_upcoming_events(self):
        make_event(title="Future Show")
        response = self.client.get(self.url)
        self.assertNotContains(response, "Future Show")

    def test_excludes_unpublished(self):
        make_past_event(title="Hidden Past", is_published=False)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Hidden Past")


# ---------------------------------------------------------------------------
# Create view
# ---------------------------------------------------------------------------


class EventCreateViewTest(TestCase):
    def setUp(self):
        self.url = reverse("events:create")
        self.user = make_user()
        self.future = (timezone.now() + timedelta(days=14)).strftime("%Y-%m-%dT%H:%M")

    def get_valid_data(self, **overrides):
        data = {
            "title": "New Event",
            "event_type": "concert",
            "start_datetime": self.future,
            "description": "",
            "is_free": True,
            "ticket_price_cents": "",
            "ticket_url": "",
            "is_virtual": False,
            "stream_url": "",
            "is_published": True,
        }
        data.update(overrides)
        return data

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_loads_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/create.html")

    def test_creates_event_on_post(self):
        self.client.force_login(self.user)
        self.client.post(self.url, self.get_valid_data())
        self.assertTrue(Event.objects.filter(title="New Event").exists())

    def test_auto_sets_created_by(self):
        self.client.force_login(self.user)
        self.client.post(self.url, self.get_valid_data())
        event = Event.objects.get(title="New Event")
        self.assertEqual(event.created_by, self.user)

    def test_auto_sets_organizing_creator_if_profile_exists(self):
        """If the user has a creator profile, it's set as the organizer."""
        creator = make_creator(user=self.user, display_name="My Profile")
        self.client.force_login(self.user)
        self.client.post(self.url, self.get_valid_data())
        event = Event.objects.get(title="New Event")
        self.assertEqual(event.organizing_creator, creator)

    def test_no_organizing_creator_if_no_profile(self):
        """If the user has no creator profile, organizing_creator is None."""
        self.client.force_login(self.user)
        self.client.post(self.url, self.get_valid_data())
        event = Event.objects.get(title="New Event")
        self.assertIsNone(event.organizing_creator)

    def test_creates_with_venue(self):
        venue = make_venue(name="Show Venue")
        self.client.force_login(self.user)
        self.client.post(self.url, self.get_valid_data(venue=venue.pk))
        event = Event.objects.get(title="New Event")
        self.assertEqual(event.venue, venue)


# ---------------------------------------------------------------------------
# Edit view (permission checking)
# ---------------------------------------------------------------------------


class EventEditViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.event = make_event(
            created_by=self.owner,
            title="Editable Event",
        )
        self.url = reverse("events:edit", kwargs={"slug": self.event.slug})
        self.future = (timezone.now() + timedelta(days=14)).strftime("%Y-%m-%dT%H:%M")

    def get_valid_data(self, **overrides):
        data = {
            "title": "Updated Title",
            "event_type": "concert",
            "start_datetime": self.future,
            "description": "",
            "is_free": True,
            "ticket_price_cents": "",
            "ticket_url": "",
            "is_virtual": False,
            "stream_url": "",
            "is_published": True,
        }
        data.update(overrides)
        return data

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_created_by_user_can_access(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/edit.html")

    def test_stranger_gets_forbidden(self):
        stranger = make_user()
        self.client.force_login(stranger)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_organizing_creator_owner_can_access(self):
        creator_user = make_user()
        creator = make_creator(user=creator_user, display_name="Event Organizer")
        self.event.organizing_creator = creator
        self.event.save()
        self.client.force_login(creator_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_organizing_creator_manager_can_access(self):
        owner = make_user()
        manager = make_user()
        creator = make_creator(user=owner, display_name="Band")
        creator.managers.add(manager)
        self.event.organizing_creator = creator
        self.event.save()
        self.client.force_login(manager)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_organizing_venue_owner_can_access(self):
        venue_user = make_user()
        venue = make_venue(user=venue_user, name="Organizing Venue")
        self.event.organizing_venue = venue
        self.event.save()
        self.client.force_login(venue_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_organizing_venue_manager_can_access(self):
        owner = make_user()
        manager = make_user()
        venue = make_venue(user=owner, name="Managed Venue")
        venue.managers.add(manager)
        self.event.organizing_venue = venue
        self.event.save()
        self.client.force_login(manager)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_updates_event_on_post(self):
        self.client.force_login(self.owner)
        self.client.post(self.url, self.get_valid_data(title="Renamed Event"))
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "Renamed Event")

    def test_stranger_cannot_update(self):
        stranger = make_user()
        self.client.force_login(stranger)
        response = self.client.post(self.url, self.get_valid_data(title="Hacked"))
        self.assertEqual(response.status_code, 403)
        self.event.refresh_from_db()
        self.assertNotEqual(self.event.title, "Hacked")
