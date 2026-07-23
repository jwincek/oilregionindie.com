"""
Event RSVPs (issue #85): the toggle view, public counts, and the
follower+RSVP notification audience.
"""
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Notification
from apps.core.notifications import (
    _event_notify_users, notify_event_relocated, notify_event_status_changed,
)
from apps.creators.tests.helpers import make_user
from apps.events.models import Event, EventRSVP
from apps.events.tests.helpers import make_event
from apps.venues.tests.helpers import make_venue


class RSVPModelTest(TestCase):
    def test_one_rsvp_per_user_per_event(self):
        event = make_event()
        user = make_user()
        EventRSVP.objects.create(event=event, user=user, status="going")
        with self.assertRaises(IntegrityError):
            EventRSVP.objects.create(event=event, user=user, status="interested")


class RSVPViewTest(TestCase):
    def setUp(self):
        self.event = make_event(title="RSVP Show")
        self.user = make_user()
        self.url = reverse("events:rsvp", kwargs={"slug": self.event.slug})

    def test_login_required(self):
        r = self.client.post(self.url, {"status": "going"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(EventRSVP.objects.exists())

    def test_going_creates_rsvp(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {"status": "going"})
        rsvp = EventRSVP.objects.get(event=self.event, user=self.user)
        self.assertEqual(rsvp.status, "going")

    def test_same_status_toggles_off(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {"status": "going"})
        self.client.post(self.url, {"status": "going"})
        self.assertFalse(EventRSVP.objects.filter(user=self.user).exists())

    def test_switching_status_updates_single_row(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {"status": "going"})
        self.client.post(self.url, {"status": "interested"})
        rsvps = EventRSVP.objects.filter(event=self.event, user=self.user)
        self.assertEqual(rsvps.count(), 1)
        self.assertEqual(rsvps.first().status, "interested")

    def test_invalid_status_404(self):
        self.client.force_login(self.user)
        r = self.client.post(self.url, {"status": "maybe"})
        self.assertEqual(r.status_code, 404)

    def test_htmx_returns_partial_with_counts(self):
        self.client.force_login(self.user)
        r = self.client.post(self.url, {"status": "going"}, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "rsvp-widget")
        self.assertContains(r, "1</span> going")


class RSVPDetailPageTest(TestCase):
    def test_detail_shows_counts_and_button(self):
        event = make_event(title="Counted Show")
        EventRSVP.objects.create(event=event, user=make_user(), status="going")
        EventRSVP.objects.create(event=event, user=make_user(), status="interested")
        r = self.client.get(event.get_absolute_url())
        self.assertContains(r, "rsvp-widget")
        self.assertContains(r, "1</span> going")
        self.assertContains(r, "1</span> interested")


class RSVPNotificationTest(TestCase):
    def setUp(self):
        self.venue = make_venue(name="Notify Venue")
        self.event = make_event(title="Notify Show", organizing_venue=self.venue)

    def test_notify_audience_unions_followers_and_rsvps_deduped(self):
        follower = make_user()
        follower.profile.followed_venues.add(self.venue)
        rsvper = make_user()
        EventRSVP.objects.create(event=self.event, user=rsvper, status="going")
        # A user who BOTH follows and RSVP'd must appear only once.
        both = make_user()
        both.profile.followed_venues.add(self.venue)
        EventRSVP.objects.create(event=self.event, user=both, status="interested")

        users = _event_notify_users(self.event)
        self.assertEqual(users, {follower, rsvper, both})

    def test_status_change_notifies_rsvpers(self):
        rsvper = make_user()
        EventRSVP.objects.create(event=self.event, user=rsvper, status="going")
        self.event.status = Event.Status.CANCELLED
        self.event.save()
        notify_event_status_changed(self.event)
        self.assertTrue(
            Notification.objects.filter(
                recipient=rsvper,
                notification_type=Notification.NotificationType.EVENT,
            ).exists()
        )

    def test_relocation_notifies_rsvpers(self):
        rsvper = make_user()
        EventRSVP.objects.create(event=self.event, user=rsvper, status="interested")
        notify_event_relocated(self.event, old_location="Old Park")
        note = Notification.objects.get(recipient=rsvper)
        self.assertIn("has moved to", note.message)
