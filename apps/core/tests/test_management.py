"""
Tests for apps.core management commands, async tasks, and the
geocoding helper:

  apps.core.tasks                   — send_weekly_digests + remind_unverified_users
  apps.core.geocoding               — geocode_address + geocode_all_pending
  setup_schedules command           — registers Django Q recurring schedules
  send_digests command              — CLI wrapper for the digest pipeline
  remind_unverified command         — CLI wrapper for verification reminders
  geocode_addresses command         — CLI wrapper for geocode_all_pending

External I/O (HTTP, email, time.sleep) is mocked so tests don't hit
the network or block on rate-limit timers.
"""

from datetime import timedelta
from io import StringIO
from unittest import mock

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from django_q.models import Schedule

from apps.community.models import CommunityPost
from apps.core import tasks as core_tasks
from apps.core.geocoding import geocode_address, geocode_all_pending
from apps.core.models import Address
from apps.creators.tests.helpers import make_creator, make_user

User = get_user_model()


# ---------------------------------------------------------------------------
# apps.core.tasks.send_weekly_digests
# ---------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SendWeeklyDigestsTaskTest(TestCase):
    def test_returns_summary_string_with_counts(self):
        mail.outbox.clear()
        fan = make_user()
        creator_user = make_user()
        creator = make_creator(user=creator_user)
        fan.profile.followed_creators.add(creator)
        CommunityPost.objects.create(
            author=creator_user, title="Real post", body="b",
        )
        # A second user with no follows — counted in `skipped`.
        make_user()
        result = core_tasks.send_weekly_digests()
        self.assertIn("Sent 1", result)
        self.assertIn("skipped", result)
        self.assertEqual(len(mail.outbox), 1)


# ---------------------------------------------------------------------------
# apps.core.tasks.remind_unverified_users
# ---------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RemindUnverifiedTaskTest(TestCase):
    def setUp(self):
        mail.outbox.clear()

    def _make_unverified_user(self, *, hours_old, email="u@example.com"):
        user = User.objects.create_user(email.split("@")[0], email, "pw")
        EmailAddress.objects.create(user=user, email=email, verified=False)
        User.objects.filter(pk=user.pk).update(
            date_joined=timezone.now() - timedelta(hours=hours_old),
        )
        return user

    def test_sends_reminder_to_unverified_user_older_than_24h(self):
        self._make_unverified_user(hours_old=48, email="forgot@example.com")
        result = core_tasks.remind_unverified_users()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["forgot@example.com"])
        self.assertIn("Sent 1", result)

    def test_excludes_recently_joined_users(self):
        """User joined 5h ago — still inside the grace period."""
        self._make_unverified_user(hours_old=5, email="fresh@example.com")
        core_tasks.remind_unverified_users()
        self.assertEqual(len(mail.outbox), 0)

    def test_excludes_users_older_than_7_days(self):
        """Beyond max_age — they're probably abandoned signups."""
        self._make_unverified_user(hours_old=24 * 10, email="ghost@example.com")
        core_tasks.remind_unverified_users()
        self.assertEqual(len(mail.outbox), 0)

    def test_excludes_users_who_have_any_verified_email(self):
        """A user with one verified + one unverified email shouldn't
        be reminded — they've already confirmed they exist."""
        user = self._make_unverified_user(hours_old=48, email="unv@example.com")
        EmailAddress.objects.create(
            user=user, email="other@example.com", verified=True,
        )
        core_tasks.remind_unverified_users()
        self.assertEqual(len(mail.outbox), 0)


# ---------------------------------------------------------------------------
# remind_unverified management command
# ---------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RemindUnverifiedCommandTest(TestCase):
    def setUp(self):
        mail.outbox.clear()

    def _make_unverified(self, hours_old, email):
        user = User.objects.create_user(email.split("@")[0], email, "pw")
        EmailAddress.objects.create(user=user, email=email, verified=False)
        User.objects.filter(pk=user.pk).update(
            date_joined=timezone.now() - timedelta(hours=hours_old),
        )
        return user

    def test_dry_run_does_not_send_emails(self):
        self._make_unverified(48, "preview@example.com")
        out = StringIO()
        call_command("remind_unverified", "--dry-run", stdout=out)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("Would remind 1", out.getvalue())
        self.assertIn("preview@example.com", out.getvalue())

    def test_sends_emails_by_default(self):
        self._make_unverified(48, "reminded@example.com")
        out = StringIO()
        call_command("remind_unverified", stdout=out)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Sent 1", out.getvalue())

    def test_hours_flag_changes_threshold(self):
        """A user 12h old is too fresh under default 24h but eligible
        under --hours 6."""
        self._make_unverified(12, "boundary@example.com")
        # Default — no email.
        call_command("remind_unverified", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)
        # --hours 6 — now eligible.
        call_command("remind_unverified", "--hours", "6", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)


# ---------------------------------------------------------------------------
# send_digests command (the CLI; underlying digest is tested elsewhere)
# ---------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SendDigestsCommandTest(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.fan = make_user()
        self.creator_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.fan.profile.followed_creators.add(self.creator)

    def test_dry_run_reports_counts_without_sending(self):
        CommunityPost.objects.create(
            author=self.creator_user, title="Activity", body="b",
        )
        out = StringIO()
        call_command("send_digests", "--dry-run", stdout=out)
        self.assertEqual(len(mail.outbox), 0)
        text = out.getvalue()
        self.assertIn("would send 1", text)
        self.assertIn(self.fan.email, text)

    def test_default_run_sends_digests(self):
        CommunityPost.objects.create(
            author=self.creator_user, title="Activity", body="b",
        )
        out = StringIO()
        call_command("send_digests", stdout=out)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("sent 1", out.getvalue())

    def test_days_flag_passes_window_to_digest(self):
        # Post created 10 days ago — outside default 7d window.
        old_post = CommunityPost.objects.create(
            author=self.creator_user, title="Old", body="b",
        )
        CommunityPost.objects.filter(pk=old_post.pk).update(
            created_at=timezone.now() - timedelta(days=10),
        )
        # --days 30 → activity is in range.
        out = StringIO()
        call_command("send_digests", "--days", "30", stdout=out)
        self.assertIn("sent 1", out.getvalue())


# ---------------------------------------------------------------------------
# setup_schedules command
# ---------------------------------------------------------------------------


class SetupSchedulesCommandTest(TestCase):
    def test_creates_all_four_schedules(self):
        Schedule.objects.all().delete()
        out = StringIO()
        call_command("setup_schedules", stdout=out)
        names = set(Schedule.objects.values_list("name", flat=True))
        self.assertEqual(names, {
            "weekly-email-digest",
            "daily-booking-expiration",
            "daily-verification-reminder",
            "daily-geocode-addresses",
        })
        # Output mentions each schedule.
        text = out.getvalue()
        for label in (
            "Weekly email digest", "Daily booking expiration",
            "Daily verification reminder", "Daily address geocoding",
        ):
            self.assertIn(label, text)

    def test_is_idempotent_via_update_or_create(self):
        """Running twice doesn't duplicate rows — it updates existing
        ones in place."""
        call_command("setup_schedules", stdout=StringIO())
        first_count = Schedule.objects.count()
        call_command("setup_schedules", stdout=StringIO())
        self.assertEqual(Schedule.objects.count(), first_count)

    def test_each_schedule_points_at_the_right_task_func(self):
        Schedule.objects.all().delete()
        call_command("setup_schedules", stdout=StringIO())
        digest = Schedule.objects.get(name="weekly-email-digest")
        self.assertEqual(digest.func, "apps.core.tasks.send_weekly_digests")
        self.assertEqual(digest.schedule_type, Schedule.WEEKLY)
        expire = Schedule.objects.get(name="daily-booking-expiration")
        self.assertEqual(expire.func, "apps.events.tasks.expire_old_bookings")
        self.assertEqual(expire.schedule_type, Schedule.DAILY)
        remind = Schedule.objects.get(name="daily-verification-reminder")
        self.assertEqual(remind.func, "apps.core.tasks.remind_unverified_users")


# ---------------------------------------------------------------------------
# apps.core.geocoding
# ---------------------------------------------------------------------------


def _addr(**kwargs):
    defaults = {
        "street": "123 Seneca St",
        "city": "Oil City",
        "state": "PA",
        "zip_code": "16301",
    }
    defaults.update(kwargs)
    return Address.objects.create(**defaults)


class GeocodeAddressTest(TestCase):
    @mock.patch("apps.core.geocoding.httpx.get")
    def test_successful_lookup_sets_lat_lng(self, mock_get):
        mock_get.return_value = mock.Mock(
            json=mock.Mock(return_value=[
                {"lat": "41.434", "lon": "-79.7025"},
            ]),
        )
        addr = _addr()
        ok = geocode_address(addr)
        self.assertTrue(ok)
        addr.refresh_from_db()
        self.assertEqual(str(addr.latitude), "41.434000")
        self.assertEqual(str(addr.longitude), "-79.702500")
        # The Nominatim query was constructed from the address parts.
        call = mock_get.call_args
        self.assertEqual(call.args[0],
                         "https://nominatim.openstreetmap.org/search")
        self.assertIn("Oil City", call.kwargs["params"]["q"])

    @mock.patch("apps.core.geocoding.httpx.get")
    def test_no_results_returns_false_and_leaves_address_unchanged(self, mock_get):
        mock_get.return_value = mock.Mock(json=mock.Mock(return_value=[]))
        addr = _addr()
        ok = geocode_address(addr)
        self.assertFalse(ok)
        addr.refresh_from_db()
        self.assertIsNone(addr.latitude)

    @mock.patch("apps.core.geocoding.httpx.get")
    def test_http_exception_returns_false_silently(self, mock_get):
        mock_get.side_effect = Exception("network blip")
        addr = _addr()
        self.assertFalse(geocode_address(addr))

    def test_empty_address_returns_false_without_calling_api(self):
        """An Address with no street/city/state/zip can't be geocoded.
        We short-circuit before making an HTTP call."""
        addr = Address.objects.create()  # all fields blank
        with mock.patch("apps.core.geocoding.httpx.get") as mock_get:
            self.assertFalse(geocode_address(addr))
            mock_get.assert_not_called()


@mock.patch("apps.core.geocoding.time.sleep")  # skip the 1.1s rate-limit nap
class GeocodeAllPendingTest(TestCase):
    @mock.patch("apps.core.geocoding.geocode_address")
    def test_iterates_pending_addresses_and_returns_tally(
        self, mock_geocode, _mock_sleep,
    ):
        # Two pending (no lat), one already geocoded.
        a, b = _addr(city="A"), _addr(city="B")
        c = _addr(city="C")
        c.latitude = 1.0
        c.longitude = 2.0
        c.save()
        # First succeeds, second fails.
        mock_geocode.side_effect = [True, False]
        success, total = geocode_all_pending()
        self.assertEqual((success, total), (1, 2))
        # Only the two pending addresses were touched.
        self.assertEqual(mock_geocode.call_count, 2)

    @mock.patch("apps.core.geocoding.geocode_address")
    def test_no_pending_addresses_returns_zero(
        self, mock_geocode, _mock_sleep,
    ):
        # The only address already has coordinates.
        a = _addr()
        a.latitude, a.longitude = 1.0, 2.0
        a.save()
        success, total = geocode_all_pending()
        self.assertEqual((success, total), (0, 0))
        mock_geocode.assert_not_called()


# ---------------------------------------------------------------------------
# geocode_addresses management command
# ---------------------------------------------------------------------------


class GeocodeAddressesCommandTest(TestCase):
    def test_no_pending_addresses_short_circuits(self):
        a = _addr()
        a.latitude, a.longitude = 1.0, 2.0
        a.save()
        out = StringIO()
        call_command("geocode_addresses", stdout=out)
        self.assertIn("All addresses have coordinates", out.getvalue())

    def test_dry_run_lists_addresses_without_calling_geocoder(self):
        _addr(street="Dry Run Lane", city="Franklin")
        with mock.patch(
            "apps.core.geocoding.geocode_all_pending",
        ) as mock_geocode:
            out = StringIO()
            call_command("geocode_addresses", "--dry-run", stdout=out)
            mock_geocode.assert_not_called()
        text = out.getvalue()
        self.assertIn("Would geocode 1", text)
        self.assertIn("Dry Run Lane", text)

    @mock.patch("apps.core.geocoding.geocode_all_pending")
    def test_default_run_calls_geocode_all_pending(self, mock_geocode):
        mock_geocode.return_value = (2, 3)  # success, total
        _addr(city="A")
        _addr(city="B")
        _addr(city="C")
        out = StringIO()
        call_command("geocode_addresses", stdout=out)
        mock_geocode.assert_called_once()
        self.assertIn("Geocoded 2 of 3", out.getvalue())
