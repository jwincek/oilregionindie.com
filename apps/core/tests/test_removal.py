"""
Non-consensual profile removal (issue #90): anonymous removal requests
mirroring the feedback flow, and admin suppression that hides a profile.
"""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Report
from apps.creators.tests.helpers import make_creator, make_user
from apps.venues.tests.helpers import make_venue


class RemovalRequestTest(TestCase):
    def setUp(self):
        cache.clear()  # the per-IP throttle is cache-backed
        self.creator = make_creator(user=None)  # unclaimed, admin-seeded
        self.url = reverse(
            "request_removal",
            kwargs={"profile_type": "creator", "slug": self.creator.slug},
        )

    def test_get_renders_form_anonymously(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Request removal")

    def test_anonymous_post_creates_report(self):
        self.client.post(self.url, {"reason": "This is me, I never agreed", "email": "a@b.com"})
        report = Report.objects.get()
        self.assertIsNone(report.reporter)  # anonymous
        self.assertIn("[REMOVAL REQUEST]", report.reason)
        self.assertEqual(report.content_type, "profile")

    def test_honeypot_drops_silently(self):
        self.client.post(self.url, {"reason": "spam", "website": "http://bot.example"})
        self.assertFalse(Report.objects.exists())

    def test_missing_reason_creates_no_report(self):
        self.client.post(self.url, {"reason": "  "})
        self.assertFalse(Report.objects.exists())

    def test_per_ip_throttle(self):
        for i in range(5):
            self.client.post(self.url, {"reason": f"request {i}"})
        self.client.post(self.url, {"reason": "over the limit"})  # 6th blocked
        self.assertEqual(Report.objects.count(), 5)

    def test_unknown_profile_404(self):
        r = self.client.get(reverse(
            "request_removal", kwargs={"profile_type": "creator", "slug": "nope"}))
        self.assertEqual(r.status_code, 404)


class SuppressionTest(TestCase):
    def test_suppressed_creator_is_hidden_from_detail(self):
        creator = make_creator(user=None)
        creator.publish_status = "suppressed"
        creator.save(update_fields=["publish_status"])
        self.assertTrue(creator.is_suppressed)
        r = self.client.get(creator.get_absolute_url())
        self.assertEqual(r.status_code, 404)

    def test_suppressed_venue_is_hidden_from_detail(self):
        venue = make_venue(user=None)
        venue.publish_status = "suppressed"
        venue.save(update_fields=["publish_status"])
        r = self.client.get(venue.get_absolute_url())
        self.assertEqual(r.status_code, 404)

    def test_claim_banner_shows_removal_link_on_unclaimed(self):
        creator = make_creator()  # helper auto-creates a user...
        creator.user = None       # ...so null it to make it genuinely unclaimed
        creator.save(update_fields=["user"])
        r = self.client.get(creator.get_absolute_url())
        self.assertContains(r, reverse(
            "request_removal", kwargs={"profile_type": "creator", "slug": creator.slug}))
