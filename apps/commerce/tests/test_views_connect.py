"""
Tests for Stripe Connect onboarding views:
connect_setup, connect_onboarding, connect_return, stripe_dashboard.

All stripe_service calls are mocked at the apps.commerce.views import
boundary so tests don't depend on the Stripe library or network.
"""

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.creators.tests.helpers import make_creator, make_user


def _new_creator_without_stripe(user=None):
    """Creator who hasn't started Stripe onboarding."""
    return make_creator(user=user or make_user())


# ---------------------------------------------------------------------------
# connect_setup
# ---------------------------------------------------------------------------


class ConnectSetupViewTest(TestCase):
    def test_login_required(self):
        r = self.client.get(reverse("commerce:connect_setup"))
        self.assertEqual(r.status_code, 302)

    def test_user_without_creator_profile_404s(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("commerce:connect_setup"))
        self.assertEqual(r.status_code, 404)

    def test_renders_for_creator_before_stripe(self):
        owner = make_user()
        _new_creator_without_stripe(user=owner)
        self.client.force_login(owner)
        r = self.client.get(reverse("commerce:connect_setup"))
        self.assertEqual(r.status_code, 200)
        # No stripe_account_id yet → no status lookup attempted.
        self.assertIsNone(r.context["account_status"])

    @mock.patch("apps.commerce.views.stripe_service.check_account_status")
    def test_account_status_fetched_when_stripe_id_present(self, mock_check):
        mock_check.return_value = {
            "details_submitted": True, "charges_enabled": True,
        }
        owner = make_user()
        creator = _new_creator_without_stripe(user=owner)
        creator.stripe_account_id = "acct_fake_123"
        creator.save()
        self.client.force_login(owner)
        r = self.client.get(reverse("commerce:connect_setup"))
        mock_check.assert_called_once_with("acct_fake_123")
        self.assertEqual(r.context["account_status"]["details_submitted"], True)

    @mock.patch("apps.commerce.views.stripe_service.check_account_status")
    def test_stripe_status_failure_falls_through_silently(self, mock_check):
        """Stripe outage shouldn't prevent the setup page from rendering."""
        mock_check.side_effect = Exception("Stripe API down")
        owner = make_user()
        creator = _new_creator_without_stripe(user=owner)
        creator.stripe_account_id = "acct_fake"
        creator.save()
        self.client.force_login(owner)
        r = self.client.get(reverse("commerce:connect_setup"))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["account_status"])


# ---------------------------------------------------------------------------
# connect_onboarding
# ---------------------------------------------------------------------------


class ConnectOnboardingViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = _new_creator_without_stripe(user=self.owner)
        self.client.force_login(self.owner)

    @mock.patch("apps.commerce.views.stripe_service.create_onboarding_link")
    @mock.patch("apps.commerce.views.stripe_service.create_connect_account")
    def test_creates_account_then_redirects_to_onboarding_link(
        self, mock_create_account, mock_create_link,
    ):
        """First-time onboarding: create_connect_account fires, the
        returned id is persisted, then a redirect to the onboarding URL."""
        mock_create_account.return_value = "acct_newly_created"
        mock_create_link.return_value = "https://connect.stripe.com/onboarding/abc"
        r = self.client.get(reverse("commerce:connect_onboarding"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, "https://connect.stripe.com/onboarding/abc")
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.stripe_account_id, "acct_newly_created")
        # The persisted id was used to mint the link.
        mock_create_link.assert_called_once()
        self.assertEqual(mock_create_link.call_args.args[0], "acct_newly_created")

    @mock.patch("apps.commerce.views.stripe_service.create_onboarding_link")
    @mock.patch("apps.commerce.views.stripe_service.create_connect_account")
    def test_skips_account_creation_when_id_already_set(
        self, mock_create_account, mock_create_link,
    ):
        self.creator.stripe_account_id = "acct_existing"
        self.creator.save()
        mock_create_link.return_value = "https://connect.stripe.com/onboarding/resume"
        r = self.client.get(reverse("commerce:connect_onboarding"))
        self.assertEqual(r.status_code, 302)
        mock_create_account.assert_not_called()
        self.assertEqual(mock_create_link.call_args.args[0], "acct_existing")

    @mock.patch("apps.commerce.views.stripe_service.create_connect_account")
    def test_stripe_failure_redirects_back_to_setup_with_error_message(
        self, mock_create,
    ):
        mock_create.side_effect = Exception("Stripe configuration error")
        r = self.client.get(reverse("commerce:connect_onboarding"))
        self.assertRedirects(r, reverse("commerce:connect_setup"))


# ---------------------------------------------------------------------------
# connect_return
# ---------------------------------------------------------------------------


class ConnectReturnViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = _new_creator_without_stripe(user=self.owner)
        self.creator.stripe_account_id = "acct_returning"
        self.creator.save()
        self.client.force_login(self.owner)

    @mock.patch("apps.commerce.views.stripe_service.check_account_status")
    def test_completed_onboarding_flips_stripe_onboarded_flag(self, mock_check):
        mock_check.return_value = {
            "details_submitted": True, "charges_enabled": True,
        }
        r = self.client.get(reverse("commerce:connect_return"))
        self.assertEqual(r.status_code, 200)
        self.creator.refresh_from_db()
        self.assertTrue(self.creator.stripe_onboarded)

    @mock.patch("apps.commerce.views.stripe_service.check_account_status")
    def test_incomplete_onboarding_leaves_flag_off(self, mock_check):
        mock_check.return_value = {
            "details_submitted": False, "charges_enabled": False,
        }
        self.client.get(reverse("commerce:connect_return"))
        self.creator.refresh_from_db()
        self.assertFalse(self.creator.stripe_onboarded)

    @mock.patch("apps.commerce.views.stripe_service.check_account_status")
    def test_status_check_exception_silenced(self, mock_check):
        mock_check.side_effect = Exception("API down")
        r = self.client.get(reverse("commerce:connect_return"))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["account_status"])


# ---------------------------------------------------------------------------
# stripe_dashboard
# ---------------------------------------------------------------------------


class StripeDashboardViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = _new_creator_without_stripe(user=self.owner)
        self.client.force_login(self.owner)

    def test_user_without_stripe_id_redirects_to_setup(self):
        r = self.client.get(reverse("commerce:stripe_dashboard"))
        self.assertRedirects(r, reverse("commerce:connect_setup"))

    @mock.patch("apps.commerce.views.stripe_service.create_login_link")
    def test_redirects_to_stripe_dashboard_url(self, mock_link):
        self.creator.stripe_account_id = "acct_xyz"
        self.creator.save()
        mock_link.return_value = "https://connect.stripe.com/express/dashboard"
        r = self.client.get(reverse("commerce:stripe_dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, "https://connect.stripe.com/express/dashboard")
        mock_link.assert_called_once_with("acct_xyz")

    @mock.patch("apps.commerce.views.stripe_service.create_login_link")
    def test_link_failure_redirects_back_to_setup(self, mock_link):
        self.creator.stripe_account_id = "acct_xyz"
        self.creator.save()
        mock_link.side_effect = Exception("Stripe error")
        r = self.client.get(reverse("commerce:stripe_dashboard"))
        self.assertRedirects(r, reverse("commerce:connect_setup"))
