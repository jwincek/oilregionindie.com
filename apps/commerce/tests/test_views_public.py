"""
Tests for the public-facing commerce surfaces:

  product_detail / group_detail   — buyer entry points
  create_checkout                  — kicks off Stripe Checkout
  checkout_success                 — post-purchase landing
  download                         — digital-product file delivery
  stripe_webhook                   — Stripe → us, with
                                     _handle_checkout_completed and
                                     _handle_payment_failed branches

Stripe is mocked at the apps.commerce.stripe_service boundary so
tests don't depend on the Stripe library being importable or on
network access. The mocking layer is in apps.commerce.views (which
imports `from . import stripe_service`), so we patch
`apps.commerce.views.stripe_service.<fn>`.
"""

import json
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.commerce.models import Order, OrderItem, Product

from .helpers import (
    make_group, make_group_item, make_order, make_order_item, make_payable_creator,
    make_product, make_user,
)


# ---------------------------------------------------------------------------
# product_detail
# ---------------------------------------------------------------------------


class ProductDetailViewTest(TestCase):
    def test_active_product_renders(self):
        product = make_product(title="Test Album")
        r = self.client.get(reverse("commerce:product_detail", kwargs={
            "creator_slug": product.creator.slug, "product_slug": product.slug,
        }))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Test Album")

    def test_inactive_product_404s(self):
        product = make_product(is_active=False)
        r = self.client.get(reverse("commerce:product_detail", kwargs={
            "creator_slug": product.creator.slug, "product_slug": product.slug,
        }))
        self.assertEqual(r.status_code, 404)

    def test_wrong_creator_slug_404s(self):
        product = make_product()
        r = self.client.get(reverse("commerce:product_detail", kwargs={
            "creator_slug": "not-the-real-slug", "product_slug": product.slug,
        }))
        self.assertEqual(r.status_code, 404)


# ---------------------------------------------------------------------------
# group_detail
# ---------------------------------------------------------------------------


class GroupDetailViewTest(TestCase):
    def test_active_group_renders(self):
        group = make_group(title="The Album Bundle")
        r = self.client.get(reverse("commerce:group_detail", kwargs={
            "creator_slug": group.creator.slug, "group_slug": group.slug,
        }))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "The Album Bundle")

    def test_inactive_group_404s(self):
        group = make_group(is_active=False)
        r = self.client.get(reverse("commerce:group_detail", kwargs={
            "creator_slug": group.creator.slug, "group_slug": group.slug,
        }))
        self.assertEqual(r.status_code, 404)


# ---------------------------------------------------------------------------
# create_checkout
# ---------------------------------------------------------------------------


class CreateCheckoutViewTest(TestCase):
    def setUp(self):
        self.creator = make_payable_creator()
        self.product = make_product(creator=self.creator, price_cents=2500)

    def url(self):
        return reverse("commerce:create_checkout", kwargs={
            "product_id": self.product.id,
        })

    def test_get_not_allowed(self):
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 405)

    def test_inactive_product_404s(self):
        self.product.is_active = False
        self.product.save()
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 404)

    def test_unpayable_creator_shows_payment_unavailable(self):
        """A creator who hasn't completed Stripe onboarding can't take
        payments — the buyer sees a 'payments unavailable' page rather
        than hitting Stripe."""
        non_payable = make_product(price_cents=100)  # uses default unconfigured creator
        r = self.client.post(reverse("commerce:create_checkout", kwargs={
            "product_id": non_payable.id,
        }))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "commerce/payment_unavailable.html")

    def test_out_of_stock_product_shows_out_of_stock_page(self):
        self.product.inventory_count = 0
        self.product.save()
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "commerce/out_of_stock.html")

    @mock.patch("apps.commerce.views.stripe_service.create_checkout_session")
    def test_successful_checkout_creates_pending_order_and_redirects(self, mock_create):
        mock_session = mock.Mock(id="cs_fake_123",
                                 url="https://checkout.stripe.com/cs_fake_123")
        mock_create.return_value = mock_session

        buyer = make_user(email="buyer@example.com")
        self.client.force_login(buyer)
        r = self.client.post(self.url(), {"quantity": 2})

        # Redirected to Stripe.
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, "https://checkout.stripe.com/cs_fake_123")

        # Pending order + item created with the right totals.
        order = Order.objects.get(stripe_checkout_session_id="cs_fake_123")
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.buyer_user, buyer)
        self.assertEqual(order.total_cents, 5000)  # 2 × 2500, no shipping
        item = OrderItem.objects.get(order=order)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.product, self.product)

        # stripe_service was called with our success/cancel URLs.
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["product"], self.product)
        self.assertEqual(kwargs["quantity"], 2)
        self.assertEqual(kwargs["buyer_email"], "buyer@example.com")

    @mock.patch("apps.commerce.views.stripe_service.create_checkout_session")
    def test_anonymous_buyer_passes_no_buyer_email(self, mock_create):
        mock_create.return_value = mock.Mock(id="cs_fake", url="https://stripe/x")
        self.client.post(self.url(), {"quantity": 1})
        self.assertIsNone(mock_create.call_args.kwargs["buyer_email"])

    @mock.patch("apps.commerce.views.stripe_service.create_checkout_session")
    def test_stripe_failure_renders_error_template(self, mock_create):
        mock_create.side_effect = Exception("Stripe down")
        r = self.client.post(self.url(), {"quantity": 1})
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "commerce/checkout_error.html")
        # No order was created.
        self.assertEqual(Order.objects.count(), 0)

    @mock.patch("apps.commerce.views.stripe_service.create_checkout_session")
    def test_physical_product_includes_shipping_in_total(self, mock_create):
        mock_create.return_value = mock.Mock(id="cs_x", url="https://x")
        self.product.shipping_cents = 500
        self.product.save()
        self.client.post(self.url(), {"quantity": 1})
        order = Order.objects.get()
        self.assertEqual(order.total_cents, 2500 + 500)


# ---------------------------------------------------------------------------
# checkout_success
# ---------------------------------------------------------------------------


class CheckoutSuccessViewTest(TestCase):
    def test_renders_without_session_id(self):
        r = self.client.get(reverse("commerce:checkout_success"))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["order"])

    def test_finds_order_by_session_id(self):
        order = make_order(stripe_checkout_session_id="cs_real")
        r = self.client.get(reverse("commerce:checkout_success"),
                            {"session_id": "cs_real"})
        self.assertEqual(r.context["order"], order)

    def test_unknown_session_id_returns_none(self):
        r = self.client.get(reverse("commerce:checkout_success"),
                            {"session_id": "cs_bogus"})
        self.assertIsNone(r.context["order"])


# ---------------------------------------------------------------------------
# download (digital product fulfillment)
# ---------------------------------------------------------------------------


class DownloadViewTest(TestCase):
    def setUp(self):
        self.buyer = make_user(email="buyer@example.com")
        self.creator = make_payable_creator()

    def test_login_required(self):
        product = make_product(creator=self.creator, is_digital=True)
        order = make_order(buyer_user=self.buyer)
        item = make_order_item(order, product, is_fulfilled=True)
        r = self.client.get(reverse("commerce:download",
                                    kwargs={"item_pk": item.pk}))
        self.assertEqual(r.status_code, 302)

    def test_unfulfilled_item_404s(self):
        product = make_product(creator=self.creator, is_digital=True)
        order = make_order(buyer_user=self.buyer)
        item = make_order_item(order, product, is_fulfilled=False)
        self.client.force_login(self.buyer)
        r = self.client.get(reverse("commerce:download",
                                    kwargs={"item_pk": item.pk}))
        self.assertEqual(r.status_code, 404)

    def test_wrong_user_404s(self):
        product = make_product(creator=self.creator, is_digital=True)
        order = make_order(buyer_user=self.buyer)
        item = make_order_item(order, product, is_fulfilled=True)
        self.client.force_login(make_user())  # not the buyer
        r = self.client.get(reverse("commerce:download",
                                    kwargs={"item_pk": item.pk}))
        self.assertEqual(r.status_code, 404)

    def test_physical_product_404s_even_for_buyer(self):
        product = make_product(creator=self.creator, is_digital=False)
        order = make_order(buyer_user=self.buyer)
        item = make_order_item(order, product, is_fulfilled=True)
        self.client.force_login(self.buyer)
        r = self.client.get(reverse("commerce:download",
                                    kwargs={"item_pk": item.pk}))
        self.assertEqual(r.status_code, 404)


# ---------------------------------------------------------------------------
# stripe_webhook + handlers
# ---------------------------------------------------------------------------


class StripeWebhookViewTest(TestCase):
    def url(self):
        return reverse("commerce:stripe_webhook")

    @mock.patch("apps.commerce.views.stripe_service.construct_webhook_event")
    def test_signature_failure_returns_400(self, mock_construct):
        mock_construct.side_effect = Exception("bad signature")
        r = self.client.post(self.url(), b"{}",
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)

    @mock.patch("apps.commerce.views.stripe_service.construct_webhook_event")
    def test_unknown_event_type_is_a_no_op_200(self, mock_construct):
        mock_construct.return_value = {
            "type": "customer.created",
            "data": {"object": {}},
        }
        r = self.client.post(self.url(), b"{}",
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)

    @mock.patch("apps.commerce.views.stripe_service.construct_webhook_event")
    def test_checkout_session_completed_marks_paid(self, mock_construct):
        creator = make_payable_creator()
        product = make_product(creator=creator, is_digital=False,
                               inventory_count=5)
        order = make_order(
            stripe_checkout_session_id="cs_complete_me",
            status=Order.Status.PENDING,
        )
        make_order_item(order, product, quantity=2)

        mock_construct.return_value = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_complete_me",
                "payment_intent": "pi_abc",
                "customer_details": {"email": "real-buyer@example.com"},
                "shipping_details": {"address": {"line1": "1 Main St"}},
            }},
        }
        r = self.client.post(self.url(), b"{}",
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.stripe_payment_id, "pi_abc")
        self.assertEqual(order.buyer_email, "real-buyer@example.com")
        self.assertEqual(order.shipping_address["address"]["line1"], "1 Main St")
        # Inventory decremented from 5 by qty=2 → 3.
        product.refresh_from_db()
        self.assertEqual(product.inventory_count, 3)

    @mock.patch("apps.commerce.views.stripe_service.construct_webhook_event")
    def test_checkout_completed_with_digital_only_marks_fulfilled(self, mock_construct):
        """All-digital orders auto-fulfill: the order's status becomes
        FULFILLED after the webhook handler runs."""
        creator = make_payable_creator()
        product = make_product(creator=creator, is_digital=True)
        order = make_order(
            stripe_checkout_session_id="cs_digital",
            status=Order.Status.PENDING,
        )
        make_order_item(order, product, quantity=1)
        mock_construct.return_value = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_digital",
                "payment_intent": "pi_d",
                "customer_details": {},
            }},
        }
        self.client.post(self.url(), b"{}",
                         content_type="application/json")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.FULFILLED)
        # The item is marked fulfilled with a timestamp.
        item = order.items.get()
        self.assertTrue(item.is_fulfilled)
        self.assertIsNotNone(item.fulfilled_at)

    @mock.patch("apps.commerce.views.stripe_service.construct_webhook_event")
    def test_checkout_completed_unknown_session_is_silent_200(self, mock_construct):
        """Webhook for a session we don't have a row for — still 200,
        no crash."""
        mock_construct.return_value = {
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_no_match"}},
        }
        r = self.client.post(self.url(), b"{}",
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)

    @mock.patch("apps.commerce.views.stripe_service.construct_webhook_event")
    def test_payment_failed_marks_order_failed(self, mock_construct):
        order = make_order(
            stripe_checkout_session_id="cs_x",
            status=Order.Status.PAID,
        )
        order.stripe_payment_id = "pi_failed"
        order.save()
        mock_construct.return_value = {
            "type": "payment_intent.payment_failed",
            "data": {"object": {"id": "pi_failed"}},
        }
        self.client.post(self.url(), b"{}",
                         content_type="application/json")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.FAILED)
