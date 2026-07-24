"""
Event view tracking + the venue engagement dashboard (issue #85):
EventView recording and the owner-only stats surface that ties venue
views, event views, and RSVPs into attribution.
"""
from django.test import TestCase
from django.urls import reverse

from apps.core.models import ProfileView
from apps.creators.tests.helpers import make_user
from apps.events.models import EventRSVP, EventView
from apps.events.tests.helpers import make_event
from apps.venues.tests.helpers import make_venue


class EventViewRecordingTest(TestCase):
    def test_record_view_increments_daily_row(self):
        event = make_event()
        EventView.record_view(event)
        EventView.record_view(event)
        row = EventView.objects.get(event=event)  # one row per event per day
        self.assertEqual(row.count, 2)

    def test_detail_records_a_view_for_visitor(self):
        event = make_event()
        self.client.get(event.get_absolute_url())
        self.assertEqual(EventView.objects.filter(event=event).count(), 1)

    def test_detail_does_not_count_the_organizer(self):
        owner = make_user()
        event = make_event(created_by=owner)
        self.client.force_login(owner)
        self.client.get(event.get_absolute_url())
        self.assertFalse(EventView.objects.filter(event=event).exists())


class VenueStatsAccessTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.venue = make_venue(user=self.owner)
        self.url = reverse("venues:stats", kwargs={"slug": self.venue.slug})

    def test_login_required(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)  # redirect to login

    def test_non_owner_forbidden(self):
        self.client.force_login(make_user())
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 403)

    def test_owner_can_view(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)


class VenueStatsAggregationTest(TestCase):
    def test_dashboard_reflects_views_and_rsvps(self):
        owner = make_user()
        venue = make_venue(user=owner)
        event = make_event(title="Festival Night", venue=venue)

        ProfileView.record_view(venue=venue)
        EventView.record_view(event)
        EventView.record_view(event)
        EventRSVP.objects.create(event=event, user=make_user(), status="going")
        EventRSVP.objects.create(event=event, user=make_user(), status="interested")

        self.client.force_login(owner)
        r = self.client.get(reverse("venues:stats", kwargs={"slug": venue.slug}))

        self.assertEqual(r.context["profile_views_all"], 1)
        self.assertEqual(r.context["event_views_all"], 2)
        self.assertEqual(r.context["total_going"], 1)
        self.assertEqual(r.context["total_interested"], 1)
        # Per-event row present with its own counts.
        self.assertContains(r, "Festival Night")
        row = next(row for row in r.context["rows"] if row["event"].pk == event.pk)
        self.assertEqual(row["views"], 2)
        self.assertEqual(row["going"], 1)
        self.assertEqual(row["interested"], 1)
