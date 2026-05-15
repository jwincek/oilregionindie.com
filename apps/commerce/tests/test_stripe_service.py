"""
Tests for apps.commerce.stripe_service — the thin wrapper around the
`stripe` library.

The view layer tests already exercise these functions by mocking them
at their import path inside `apps.commerce.views`. These tests cover
the *implementations* themselves by mocking the underlying `stripe`
library calls and asserting on the kwargs we hand to Stripe + on the
field extraction from the response.
"""

from unittest import mock

from django.test import TestCase, override_settings

from apps.commerce import stripe_service
from apps.commerce.models import Product

from .helpers import make_payable_creator, make_product


# ---------------------------------------------------------------------------
# create_connect_account
# ---------------------------------------------------------------------------


class CreateConnectAccountTest(TestCase):
    @mock.patch("apps.commerce.stripe_service.stripe.Account.create")
    def test_creates_express_account_with_capabilities_and_metadata(self, mock_create):
        mock_create.return_value = mock.Mock(id="acct_freshly_created")
        creator = make_payable_creator()
        # Wipe the prebaked id so we can see the function's return value
        # against a known Stripe mock id.
        creator.stripe_account_id = ""
        creator.save()

        account_id = stripe_service.create_connect_account(creator)

        self.assertEqual(account_id, "acct_freshly_created")
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["type"], "express")
        self.assertEqual(
            kwargs["capabilities"],
            {
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
        )
        self.assertEqual(kwargs["metadata"]["platform"], "oilregion_hub")
        self.assertEqual(kwargs["metadata"]["profile_id"], str(creator.id))


# ---------------------------------------------------------------------------
# create_onboarding_link
# ---------------------------------------------------------------------------


class CreateOnboardingLinkTest(TestCase):
    @mock.patch("apps.commerce.stripe_service.stripe.AccountLink.create")
    def test_builds_account_link_for_onboarding(self, mock_create):
        mock_create.return_value = mock.Mock(
            url="https://connect.stripe.com/onboarding/xyz",
        )
        url = stripe_service.create_onboarding_link(
            "acct_abc", "https://example.com/return/", "https://example.com/refresh/",
        )
        self.assertEqual(url, "https://connect.stripe.com/onboarding/xyz")
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["account"], "acct_abc")
        self.assertEqual(kwargs["return_url"], "https://example.com/return/")
        self.assertEqual(kwargs["refresh_url"], "https://example.com/refresh/")
        self.assertEqual(kwargs["type"], "account_onboarding")


# ---------------------------------------------------------------------------
# check_account_status
# ---------------------------------------------------------------------------


class CheckAccountStatusTest(TestCase):
    @mock.patch("apps.commerce.stripe_service.stripe.Account.retrieve")
    def test_returns_dict_with_the_three_status_flags(self, mock_retrieve):
        mock_retrieve.return_value = mock.Mock(
            charges_enabled=True,
            payouts_enabled=False,
            details_submitted=True,
        )
        status = stripe_service.check_account_status("acct_abc")
        self.assertEqual(status, {
            "charges_enabled": True,
            "payouts_enabled": False,
            "details_submitted": True,
        })
        mock_retrieve.assert_called_once_with("acct_abc")


# ---------------------------------------------------------------------------
# create_login_link
# ---------------------------------------------------------------------------


class CreateLoginLinkTest(TestCase):
    @mock.patch("apps.commerce.stripe_service.stripe.Account.create_login_link")
    def test_returns_dashboard_url(self, mock_create_link):
        mock_create_link.return_value = mock.Mock(
            url="https://connect.stripe.com/express/dashboard",
        )
        url = stripe_service.create_login_link("acct_xyz")
        self.assertEqual(url, "https://connect.stripe.com/express/dashboard")
        mock_create_link.assert_called_once_with("acct_xyz")


# ---------------------------------------------------------------------------
# construct_webhook_event
# ---------------------------------------------------------------------------


class ConstructWebhookEventTest(TestCase):
    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_value")
    @mock.patch("apps.commerce.stripe_service.stripe.Webhook.construct_event")
    def test_passes_payload_signature_and_secret_through(self, mock_construct):
        mock_construct.return_value = {"type": "test.event"}
        result = stripe_service.construct_webhook_event(
            b'{"hello": "world"}', "t=1,v1=sig",
        )
        self.assertEqual(result, {"type": "test.event"})
        mock_construct.assert_called_once_with(
            b'{"hello": "world"}', "t=1,v1=sig", "whsec_test_value",
        )


# ---------------------------------------------------------------------------
# create_checkout_session
# ---------------------------------------------------------------------------


class CreateCheckoutSessionTest(TestCase):
    def setUp(self):
        self.creator = make_payable_creator()
        self.product = make_product(
            creator=self.creator, price_cents=2500,
            is_digital=False, shipping_cents=500,
        )

    def _mock_session(self):
        """Return a mock that stripe.checkout.Session.create returns."""
        return mock.Mock(id="cs_fake", url="https://checkout.stripe.com/cs_fake")

    def test_raises_when_creator_cannot_accept_payments(self):
        """Defensive — the view already gates on can_accept_payments,
        but the service layer asserts it too."""
        self.creator.stripe_onboarded = False
        self.creator.save()
        with self.assertRaises(ValueError):
            stripe_service.create_checkout_session(
                product=self.product, quantity=1,
                success_url="s", cancel_url="c",
            )

    @mock.patch("apps.commerce.stripe_service.stripe.checkout.Session.create")
    @override_settings(STRIPE_PLATFORM_FEE_PERCENT=0)
    def test_digital_product_no_shipping_no_address_collection(self, mock_create):
        mock_create.return_value = self._mock_session()
        digital = make_product(creator=self.creator, is_digital=True,
                               price_cents=1000)
        stripe_service.create_checkout_session(
            product=digital, quantity=1,
            success_url="s", cancel_url="c",
        )
        kwargs = mock_create.call_args.kwargs
        # Digital → exactly one line item (no shipping line).
        self.assertEqual(len(kwargs["line_items"]), 1)
        # No shipping_address_collection for digital products.
        self.assertNotIn("shipping_address_collection", kwargs)

    @mock.patch("apps.commerce.stripe_service.stripe.checkout.Session.create")
    @override_settings(STRIPE_PLATFORM_FEE_PERCENT=0)
    def test_physical_product_with_shipping_adds_shipping_line(self, mock_create):
        mock_create.return_value = self._mock_session()
        stripe_service.create_checkout_session(
            product=self.product, quantity=2,
            success_url="s", cancel_url="c",
        )
        kwargs = mock_create.call_args.kwargs
        # Two line items: product + shipping.
        self.assertEqual(len(kwargs["line_items"]), 2)
        shipping = kwargs["line_items"][1]
        self.assertEqual(shipping["price_data"]["unit_amount"], 500)
        self.assertEqual(shipping["quantity"], 1)
        self.assertIn("Shipping", shipping["price_data"]["product_data"]["name"])
        # Physical → US shipping_address_collection.
        self.assertEqual(
            kwargs["shipping_address_collection"]["allowed_countries"],
            ["US"],
        )

    @mock.patch("apps.commerce.stripe_service.stripe.checkout.Session.create")
    @override_settings(STRIPE_PLATFORM_FEE_PERCENT=0)
    def test_physical_with_zero_shipping_skips_shipping_line(self, mock_create):
        """Free-shipping physical → shipping_cents=0 → no shipping line,
        but still collect address."""
        mock_create.return_value = self._mock_session()
        free_ship = make_product(creator=self.creator, is_digital=False,
                                 shipping_cents=0, price_cents=1000)
        stripe_service.create_checkout_session(
            product=free_ship, quantity=1,
            success_url="s", cancel_url="c",
        )
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(len(kwargs["line_items"]), 1)
        # Address collection still set for physical product.
        self.assertIn("shipping_address_collection", kwargs)

    @mock.patch("apps.commerce.stripe_service.stripe.checkout.Session.create")
    @override_settings(STRIPE_PLATFORM_FEE_PERCENT=10)
    def test_platform_fee_computed_from_setting_and_quantity(self, mock_create):
        mock_create.return_value = self._mock_session()
        # 2500 cents × qty 3 × 10% = 750.
        stripe_service.create_checkout_session(
            product=self.product, quantity=3,
            success_url="s", cancel_url="c",
        )
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(
            kwargs["payment_intent_data"]["application_fee_amount"], 750,
        )
        self.assertEqual(
            kwargs["payment_intent_data"]["transfer_data"]["destination"],
            self.creator.stripe_account_id,
        )

    @mock.patch("apps.commerce.stripe_service.stripe.checkout.Session.create")
    @override_settings(STRIPE_PLATFORM_FEE_PERCENT=0)
    def test_zero_platform_fee_passes_application_fee_amount_zero(self, mock_create):
        mock_create.return_value = self._mock_session()
        stripe_service.create_checkout_session(
            product=self.product, quantity=1,
            success_url="s", cancel_url="c",
        )
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(
            kwargs["payment_intent_data"]["application_fee_amount"], 0,
        )

    @mock.patch("apps.commerce.stripe_service.stripe.checkout.Session.create")
    def test_buyer_email_propagated_when_present(self, mock_create):
        mock_create.return_value = self._mock_session()
        stripe_service.create_checkout_session(
            product=self.product, quantity=1,
            success_url="s", cancel_url="c",
            buyer_email="buyer@example.com",
        )
        self.assertEqual(
            mock_create.call_args.kwargs["customer_email"],
            "buyer@example.com",
        )

    @mock.patch("apps.commerce.stripe_service.stripe.checkout.Session.create")
    def test_no_buyer_email_omits_customer_email_key(self, mock_create):
        mock_create.return_value = self._mock_session()
        stripe_service.create_checkout_session(
            product=self.product, quantity=1,
            success_url="s", cancel_url="c",
            buyer_email=None,
        )
        # The key shouldn't appear at all — Stripe will let the buyer
        # type their email at checkout instead.
        self.assertNotIn("customer_email", mock_create.call_args.kwargs)

    @mock.patch("apps.commerce.stripe_service.stripe.checkout.Session.create")
    def test_session_returned_is_what_stripe_returns(self, mock_create):
        session = self._mock_session()
        mock_create.return_value = session
        result = stripe_service.create_checkout_session(
            product=self.product, quantity=1,
            success_url="s", cancel_url="c",
        )
        self.assertIs(result, session)

    @mock.patch("apps.commerce.stripe_service.stripe.checkout.Session.create")
    def test_metadata_carries_product_and_creator_ids(self, mock_create):
        """Stripe webhook events come back with the metadata we set
        here, so the IDs must round-trip correctly."""
        mock_create.return_value = self._mock_session()
        stripe_service.create_checkout_session(
            product=self.product, quantity=1,
            success_url="s", cancel_url="c",
        )
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(
            kwargs["metadata"]["product_id"], str(self.product.id),
        )
        self.assertEqual(
            kwargs["metadata"]["creator_id"], str(self.creator.id),
        )
        # Also on payment_intent_data.metadata for webhook delivery.
        self.assertEqual(
            kwargs["payment_intent_data"]["metadata"]["product_id"],
            str(self.product.id),
        )
