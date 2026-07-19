"""
Download delivery and refund revocation.

Two download routes exist: the logged-in buyer route (uuid pk) and the
signed-token route delivered by the fulfillment email — the only path a
guest buyer has, since guest orders have no ``buyer_user`` to log in as.
Refunds must revoke both routes.
"""
import re
import tempfile
from unittest import mock

from django.core import mail, signing
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.commerce.models import Order
from apps.commerce.views import DOWNLOAD_TOKEN_SALT, download_token

from .helpers import (
    make_order, make_order_item, make_payable_creator, make_product, make_user,
)

MEDIA_TMP = tempfile.mkdtemp()


def make_digital_item(buyer_user=None, fulfilled=True):
    creator = make_payable_creator()
    product = make_product(creator=creator, is_digital=True)
    product.file.save("guide.pdf", ContentFile(b"pdf-bytes"), save=True)
    order = make_order(
        buyer_user=buyer_user,
        status=Order.Status.FULFILLED if fulfilled else Order.Status.PENDING,
        stripe_payment_id="pi_refund_me",
    )
    item = make_order_item(order, product, is_fulfilled=fulfilled)
    return order, item


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class TokenDownloadTest(TestCase):
    def test_guest_can_download_via_signed_token(self):
        _, item = make_digital_item(buyer_user=None)
        url = reverse("commerce:download_token", args=[download_token(item.pk)])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), b"pdf-bytes")
        item.refresh_from_db()
        self.assertEqual(item.download_count, 1)

    def test_tampered_token_is_404(self):
        _, item = make_digital_item()
        bad = signing.dumps(str(item.pk), salt="wrong-salt")
        r = self.client.get(reverse("commerce:download_token", args=[bad]))
        self.assertEqual(r.status_code, 404)

    def test_unfulfilled_item_is_404(self):
        _, item = make_digital_item(fulfilled=False)
        url = reverse("commerce:download_token", args=[download_token(item.pk)])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_uuid_route_still_requires_login(self):
        _, item = make_digital_item()
        r = self.client.get(reverse("commerce:download", args=[item.pk]))
        self.assertEqual(r.status_code, 302)  # to login

    def test_logged_in_owner_still_downloads(self):
        user = make_user()
        _, item = make_digital_item(buyer_user=user)
        self.client.force_login(user)
        r = self.client.get(reverse("commerce:download", args=[item.pk]))
        self.assertEqual(r.status_code, 200)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class RefundWebhookTest(TestCase):
    def url(self):
        return reverse("commerce:stripe_webhook")

    def _post_refund(self, mock_construct, refunded=True, payment_intent="pi_refund_me"):
        mock_construct.return_value = {
            "type": "charge.refunded",
            "data": {"object": {
                "id": "ch_test",
                "refunded": refunded,
                "payment_intent": payment_intent,
            }},
        }
        return self.client.post(self.url(), b"{}", content_type="application/json")

    @mock.patch("apps.commerce.views.stripe_service.construct_webhook_event")
    def test_full_refund_marks_order_and_revokes_both_routes(self, mock_construct):
        user = make_user()
        order, item = make_digital_item(buyer_user=user)
        token_url = reverse("commerce:download_token", args=[download_token(item.pk)])

        r = self._post_refund(mock_construct)
        self.assertEqual(r.status_code, 200)

        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(order.status, Order.Status.REFUNDED)
        self.assertFalse(item.is_fulfilled)

        # Token route revoked
        self.assertEqual(self.client.get(token_url).status_code, 404)
        # Logged-in route revoked
        self.client.force_login(user)
        r = self.client.get(reverse("commerce:download", args=[item.pk]))
        self.assertEqual(r.status_code, 404)

    @mock.patch("apps.commerce.views.stripe_service.construct_webhook_event")
    def test_partial_refund_leaves_order_untouched(self, mock_construct):
        order, item = make_digital_item()
        self._post_refund(mock_construct, refunded=False)
        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(order.status, Order.Status.FULFILLED)
        self.assertTrue(item.is_fulfilled)

    @mock.patch("apps.commerce.views.stripe_service.construct_webhook_event")
    def test_unknown_payment_intent_is_a_no_op_200(self, mock_construct):
        r = self._post_refund(mock_construct, payment_intent="pi_nobody")
        self.assertEqual(r.status_code, 200)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class FulfillmentEmailTest(TestCase):
    def url(self):
        return reverse("commerce:stripe_webhook")

    @mock.patch("apps.commerce.views.stripe_service.construct_webhook_event")
    def test_digital_checkout_emails_working_download_link(self, mock_construct):
        creator = make_payable_creator()
        product = make_product(creator=creator, is_digital=True)
        product.file.save("track.mp3", ContentFile(b"audio"), save=True)
        order = make_order(
            buyer_user=None,
            stripe_checkout_session_id="cs_guest_digital",
            status=Order.Status.PENDING,
        )
        make_order_item(order, product)

        mock_construct.return_value = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_guest_digital",
                "payment_intent": "pi_guest",
                "customer_details": {"email": "guest@example.com"},
            }},
        }
        self.client.post(self.url(), b"{}", content_type="application/json")

        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn(product.title, body)
        link = re.search(r"https?://[^/\s]+(/\S*/download/t/\S+)", body)
        self.assertIsNotNone(link)
        # The emailed link must actually work, logged out.
        r = self.client.get(link.group(1))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), b"audio")

    @mock.patch("apps.commerce.views.stripe_service.construct_webhook_event")
    def test_physical_only_order_sends_no_download_email(self, mock_construct):
        creator = make_payable_creator()
        product = make_product(creator=creator, is_digital=False, inventory_count=3)
        order = make_order(stripe_checkout_session_id="cs_physical")
        make_order_item(order, product)

        mock_construct.return_value = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_physical",
                "payment_intent": "pi_p",
                "customer_details": {"email": "buyer@example.com"},
            }},
        }
        self.client.post(self.url(), b"{}", content_type="application/json")
        self.assertEqual(len(mail.outbox), 0)
