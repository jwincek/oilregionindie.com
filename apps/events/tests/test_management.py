"""
Tests for apps.events management commands and async tasks:
  - apps.events.tasks.expire_old_bookings (Django Q task)
  - apps.events.management.commands.expire_bookings (CLI wrapper)
"""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.events.models import BookingRequest
from apps.events.tasks import expire_old_bookings
from apps.events.tests.helpers import make_booking_request
from apps.creators.tests.helpers import make_creator, make_user
from apps.venues.tests.helpers import make_venue


def _age_booking(booking, days_old):
    """Backdate created_at so the cutoff filter picks it up."""
    BookingRequest.objects.filter(pk=booking.pk).update(
        created_at=timezone.now() - timedelta(days=days_old),
    )


class ExpireOldBookingsTaskTest(TestCase):
    """Direct test of the task function used by Django Q's scheduler."""

    def setUp(self):
        self.creator = make_creator(user=make_user())
        self.venue = make_venue()

    def test_expires_pending_bookings_older_than_default_30_days(self):
        old = make_booking_request(creator=self.creator, venue=self.venue)
        recent = make_booking_request(creator=self.creator, venue=self.venue)
        _age_booking(old, 35)
        _age_booking(recent, 5)

        result = expire_old_bookings()

        old.refresh_from_db()
        recent.refresh_from_db()
        self.assertEqual(old.status, BookingRequest.Status.EXPIRED)
        self.assertEqual(recent.status, BookingRequest.Status.PENDING)
        self.assertIn("Expired 1", result)

    def test_custom_days_argument(self):
        booking = make_booking_request(creator=self.creator, venue=self.venue)
        _age_booking(booking, 10)
        result = expire_old_bookings(days=7)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingRequest.Status.EXPIRED)
        self.assertIn("Expired 1", result)

    def test_only_pending_bookings_are_touched(self):
        accepted = make_booking_request(
            creator=self.creator, venue=self.venue,
            status=BookingRequest.Status.ACCEPTED,
        )
        _age_booking(accepted, 60)
        expire_old_bookings()
        accepted.refresh_from_db()
        # Accepted booking stays accepted regardless of age.
        self.assertEqual(accepted.status, BookingRequest.Status.ACCEPTED)


class ExpireBookingsCommandTest(TestCase):
    """CLI wrapper around the task. Adds --dry-run and --days flags."""

    def setUp(self):
        self.creator = make_creator(user=make_user(), display_name="Old Act")
        self.venue = make_venue(name="The Spot")
        self.old = make_booking_request(creator=self.creator, venue=self.venue)
        _age_booking(self.old, 35)

    def test_default_run_expires_old_bookings(self):
        out = StringIO()
        call_command("expire_bookings", stdout=out)
        self.old.refresh_from_db()
        self.assertEqual(self.old.status, BookingRequest.Status.EXPIRED)
        self.assertIn("Expired 1", out.getvalue())

    def test_dry_run_does_not_modify_db(self):
        out = StringIO()
        call_command("expire_bookings", "--dry-run", stdout=out)
        self.old.refresh_from_db()
        self.assertEqual(self.old.status, BookingRequest.Status.PENDING)
        text = out.getvalue()
        self.assertIn("Would expire 1", text)
        # Dry-run output includes the creator and venue names so admins
        # can preview which bookings are about to be expired.
        self.assertIn("Old Act", text)
        self.assertIn("The Spot", text)

    def test_days_flag_changes_cutoff(self):
        """A 7-day-old booking is safe under default 30 but expires
        under --days 5."""
        recent = make_booking_request(creator=self.creator, venue=self.venue)
        _age_booking(recent, 7)
        # Default — recent stays pending.
        call_command("expire_bookings", stdout=StringIO())
        recent.refresh_from_db()
        self.assertEqual(recent.status, BookingRequest.Status.PENDING)
        # --days 5 — now it expires.
        call_command("expire_bookings", "--days", "5", stdout=StringIO())
        recent.refresh_from_db()
        self.assertEqual(recent.status, BookingRequest.Status.EXPIRED)
