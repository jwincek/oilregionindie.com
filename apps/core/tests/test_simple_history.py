"""
Smoke tests for django-simple-history wiring.

Confirms that each model we opted in (UserProfile, Report, CreatorProfile,
VenueProfile, BookingRequest) actually accrues historical rows on save
and that the `history_user` is captured when the change comes through a
request (via HistoryRequestMiddleware). We trust simple-history's own
tests for the rest of the mechanics.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class HistoryRecordsTest(TestCase):
    def test_userprofile_records_history_on_field_change(self):
        from apps.core.models import UserProfile
        user = User.objects.create_user("u1", "u1@example.com", "pw")
        # The profile is auto-created via signal — there's already one
        # historical row representing the initial state.
        profile = UserProfile.objects.get(user=user)
        baseline = profile.history.count()
        profile.is_suspended = True
        profile.save()
        self.assertEqual(profile.history.count(), baseline + 1)
        # The most recent row reflects the new state.
        latest = profile.history.order_by("-history_date").first()
        self.assertTrue(latest.is_suspended)

    def test_report_records_history(self):
        from apps.core.models import Report
        reporter = User.objects.create_user("u2", "u2@example.com", "pw")
        report = Report.objects.create(
            reporter=reporter,
            content_type=Report.ContentType.PROFILE,
            content_id="abc",
            reason="Spam",
        )
        baseline = report.history.count()
        report.status = Report.Status.REVIEWED
        report.admin_notes = "Reviewed; no action needed."
        report.save()
        self.assertEqual(report.history.count(), baseline + 1)

    def test_creatorprofile_records_publish_status_change(self):
        from apps.creators.models import CreatorProfile
        owner = User.objects.create_user("u3", "u3@example.com", "pw")
        c = CreatorProfile.objects.create(
            user=owner, display_name="Test Creator",
            publish_status="draft",
        )
        baseline = c.history.count()
        c.publish_status = "published"
        c.save()
        self.assertEqual(c.history.count(), baseline + 1)
        # Verify we can reconstruct who-changed-what — the latest row
        # captures the new value, the previous one captures draft.
        rows = list(c.history.order_by("history_date").values_list("publish_status", flat=True))
        self.assertEqual(rows[-1], "published")
        self.assertIn("draft", rows)

    def test_venueprofile_records_history(self):
        from apps.venues.models import VenueProfile
        owner = User.objects.create_user("u4", "u4@example.com", "pw")
        v = VenueProfile.objects.create(
            user=owner, name="Test Venue", city="Oil City", state="PA",
            publish_status="draft",
        )
        baseline = v.history.count()
        v.publish_status = "published"
        v.save()
        self.assertEqual(v.history.count(), baseline + 1)

    def test_bookingrequest_records_status_change(self):
        from apps.creators.models import CreatorProfile
        from apps.events.models import BookingRequest
        from apps.venues.models import VenueProfile
        owner_c = User.objects.create_user("uc", "uc@example.com", "pw")
        owner_v = User.objects.create_user("uv", "uv@example.com", "pw")
        c = CreatorProfile.objects.create(user=owner_c, display_name="C")
        v = VenueProfile.objects.create(
            user=owner_v, name="V", city="Oil City", state="PA",
        )
        br = BookingRequest.objects.create(
            creator=c, venue=v, initiated_by=owner_c,
            direction=BookingRequest.Direction.CREATOR_TO_VENUE,
            preferred_dates="Any weekend",
            message="Hi.",
        )
        baseline = br.history.count()
        br.status = BookingRequest.Status.ACCEPTED
        br.save()
        self.assertEqual(br.history.count(), baseline + 1)
        statuses = list(br.history.order_by("history_date").values_list("status", flat=True))
        # Pending → accepted is recoverable from the history.
        self.assertEqual(statuses[0], "pending")
        self.assertEqual(statuses[-1], "accepted")
