"""
Tests for creator-facing commerce views — product/order management
plus the HTMX image and inventory endpoints.
"""

import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.commerce.models import (
    Order, OrderItem, Product, ProductImage,
)

from .helpers import (
    make_order, make_order_item, make_payable_creator, make_product, make_user,
)

User = get_user_model()


def _tiny_png():
    """Smallest valid PNG via Pillow — Django's ImageField uses Pillow to
    verify uploads, so a hand-rolled byte blob isn't reliable."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="PNG")
    return SimpleUploadedFile("test.png", buf.getvalue(),
                              content_type="image/png")


# ---------------------------------------------------------------------------
# my_products
# ---------------------------------------------------------------------------


class MyProductsViewTest(TestCase):
    def test_login_required(self):
        r = self.client.get(reverse("commerce:my_products"))
        self.assertEqual(r.status_code, 302)

    def test_user_without_creator_profile_redirects_to_setup(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("commerce:my_products"))
        self.assertRedirects(r, reverse("creators:setup"),
                             fetch_redirect_response=False)

    def test_creator_sees_their_products(self):
        owner = make_user()
        creator = make_payable_creator(user=owner)
        mine = make_product(creator=creator, title="Mine")
        # Another creator's product shouldn't appear.
        other = make_payable_creator()
        make_product(creator=other, title="NotMine")
        self.client.force_login(owner)
        r = self.client.get(reverse("commerce:my_products"))
        self.assertEqual(r.status_code, 200)
        self.assertIn(mine, r.context["products"])
        self.assertContains(r, "Mine")


# ---------------------------------------------------------------------------
# create_product
# ---------------------------------------------------------------------------


class CreateProductViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.client.force_login(self.owner)

    def test_user_without_creator_profile_redirects(self):
        other = make_user()
        self.client.force_login(other)
        r = self.client.get(reverse("commerce:create_product"))
        self.assertRedirects(r, reverse("creators:setup"),
                             fetch_redirect_response=False)

    def test_get_renders_form(self):
        r = self.client.get(reverse("commerce:create_product"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("form", r.context)

    def test_post_creates_product_with_correct_creator(self):
        r = self.client.post(reverse("commerce:create_product"), {
            "title": "New Album",
            "description": "An album",
            "product_type": Product.ProductType.DIGITAL_MUSIC,
            "price_dollars": "10.00",
            "shipping_dollars": "0",
            "is_active": "on",
            "is_digital": "on",
        })
        self.assertRedirects(r, reverse("commerce:my_products"))
        product = Product.objects.get(title="New Album")
        self.assertEqual(product.creator, self.creator)


# ---------------------------------------------------------------------------
# edit_product
# ---------------------------------------------------------------------------


class EditProductViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.product = make_product(creator=self.creator, title="Original")
        self.client.force_login(self.owner)

    def test_owner_can_load_form(self):
        r = self.client.get(reverse("commerce:edit_product",
                                    kwargs={"pk": self.product.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["product"], self.product)

    def test_other_creator_404s(self):
        other_owner = make_user()
        make_payable_creator(user=other_owner)
        self.client.force_login(other_owner)
        r = self.client.get(reverse("commerce:edit_product",
                                    kwargs={"pk": self.product.pk}))
        self.assertEqual(r.status_code, 404)

    def test_post_updates_product(self):
        r = self.client.post(reverse("commerce:edit_product",
                                     kwargs={"pk": self.product.pk}), {
            "title": "Updated",
            "description": "New desc",
            "product_type": self.product.product_type,
            "price_dollars": "20.00",
            "shipping_dollars": "0",
            "is_active": "on",
        })
        self.assertRedirects(r, reverse("commerce:my_products"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.title, "Updated")
        self.assertEqual(self.product.price_cents, 2000)


# ---------------------------------------------------------------------------
# my_sales + order_detail
# ---------------------------------------------------------------------------


class MySalesViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.product = make_product(creator=self.creator)

    def test_no_creator_profile_redirects(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("commerce:my_sales"))
        self.assertRedirects(r, reverse("creators:setup"),
                             fetch_redirect_response=False)

    def test_shows_only_paid_or_fulfilled_orders(self):
        paid = make_order(status=Order.Status.PAID)
        make_order_item(paid, self.product)
        # Pending shouldn't appear.
        pending = make_order(status=Order.Status.PENDING,
                             stripe_checkout_session_id="cs_p")
        make_order_item(pending, self.product)

        self.client.force_login(self.owner)
        r = self.client.get(reverse("commerce:my_sales"))
        item_orders = [i.order for i in r.context["items"]]
        self.assertIn(paid, item_orders)
        self.assertNotIn(pending, item_orders)


class OrderDetailViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.product = make_product(creator=self.creator)

    def test_no_creator_profile_redirects(self):
        self.client.force_login(make_user())
        order = make_order(status=Order.Status.PAID)
        r = self.client.get(reverse("commerce:order_detail",
                                    kwargs={"pk": order.pk}))
        self.assertRedirects(r, reverse("creators:setup"),
                             fetch_redirect_response=False)

    def test_order_with_creators_item_renders(self):
        order = make_order(status=Order.Status.PAID)
        make_order_item(order, self.product)
        self.client.force_login(self.owner)
        r = self.client.get(reverse("commerce:order_detail",
                                    kwargs={"pk": order.pk}))
        self.assertEqual(r.status_code, 200)

    def test_order_with_no_items_for_this_creator_404s(self):
        """Defensive: a creator viewing an order URL that contains only
        OTHER creators' items gets a 404, not a leak of order data."""
        order = make_order(status=Order.Status.PAID)
        other_creator = make_payable_creator()
        make_order_item(order, make_product(creator=other_creator))
        self.client.force_login(self.owner)
        r = self.client.get(reverse("commerce:order_detail",
                                    kwargs={"pk": order.pk}))
        self.assertEqual(r.status_code, 404)


# ---------------------------------------------------------------------------
# mark_shipped
# ---------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MarkShippedViewTest(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.product = make_product(creator=self.creator)
        self.order = make_order(buyer_email="buyer@example.com",
                                status=Order.Status.PAID)
        self.item = make_order_item(self.order, self.product, quantity=1)

    def test_non_creator_user_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.post(reverse("commerce:mark_shipped",
                                     kwargs={"item_pk": self.item.pk}))
        self.assertEqual(r.status_code, 403)

    def test_other_creator_404s(self):
        other_owner = make_user()
        make_payable_creator(user=other_owner)
        self.client.force_login(other_owner)
        r = self.client.post(reverse("commerce:mark_shipped",
                                     kwargs={"item_pk": self.item.pk}))
        self.assertEqual(r.status_code, 404)

    def test_marks_shipped_emails_buyer_and_sets_tracking(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("commerce:mark_shipped",
                                     kwargs={"item_pk": self.item.pk}),
                             {"tracking_number": "TRK-123"})
        self.assertRedirects(r, reverse("commerce:order_detail",
                                        kwargs={"pk": self.order.pk}))
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_fulfilled)
        self.assertEqual(self.item.tracking_number, "TRK-123")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("TRK-123", mail.outbox[0].body)
        # When all items in the order are fulfilled, order moves to
        # FULFILLED (it's the only item, so that should fire).
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.FULFILLED)

    def test_marks_shipped_without_tracking(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("commerce:mark_shipped",
                                 kwargs={"item_pk": self.item.pk}))
        self.item.refresh_from_db()
        self.assertEqual(self.item.tracking_number, "")
        # Email body should not include a "Tracking number:" line.
        self.assertNotIn("Tracking number:", mail.outbox[0].body)


# ---------------------------------------------------------------------------
# Product image HTMX endpoints
# ---------------------------------------------------------------------------


class ProductImagesViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.product = make_product(creator=self.creator)

    def test_non_creator_user_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("commerce:product_images",
                                    kwargs={"pk": self.product.pk}))
        self.assertEqual(r.status_code, 403)

    def test_get_renders_partial(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("commerce:product_images",
                                    kwargs={"pk": self.product.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "commerce/_product_images.html")


class AddProductImageViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.product = make_product(creator=self.creator)

    def test_get_renders_form(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("commerce:add_product_image",
                                    kwargs={"pk": self.product.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "commerce/_product_image_form.html")

    def test_post_creates_image_and_returns_list(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("commerce:add_product_image",
                                     kwargs={"pk": self.product.pk}), {
            "image": _tiny_png(),
            "alt_text": "Cover art",
            "sort_order": 0,
        })
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "commerce/_product_images.html")
        self.assertEqual(self.product.images.count(), 1)

    def test_non_creator_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("commerce:add_product_image",
                                    kwargs={"pk": self.product.pk}))
        self.assertEqual(r.status_code, 403)


class DeleteProductImageViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.product = make_product(creator=self.creator)
        self.image = ProductImage.objects.create(
            product=self.product, image=_tiny_png(), alt_text="x",
        )

    def test_get_not_allowed(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("commerce:delete_product_image",
                                    kwargs={"pk": self.product.pk,
                                            "image_pk": self.image.pk}))
        self.assertEqual(r.status_code, 405)

    def test_owner_deletes_image(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("commerce:delete_product_image",
                                     kwargs={"pk": self.product.pk,
                                             "image_pk": self.image.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ProductImage.objects.filter(pk=self.image.pk).exists())

    def test_non_creator_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.post(reverse("commerce:delete_product_image",
                                     kwargs={"pk": self.product.pk,
                                             "image_pk": self.image.pk}))
        self.assertEqual(r.status_code, 403)


# ---------------------------------------------------------------------------
# mark_sold + restock
# ---------------------------------------------------------------------------


class MarkSoldRestockViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.product = make_product(creator=self.creator, inventory_count=10)
        self.client.force_login(self.owner)

    def test_mark_sold_sets_inventory_to_zero(self):
        r = self.client.post(reverse("commerce:mark_sold",
                                     kwargs={"pk": self.product.pk}))
        self.assertRedirects(r, reverse("commerce:my_products"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_count, 0)

    def test_mark_sold_non_creator_403(self):
        self.client.force_login(make_user())
        r = self.client.post(reverse("commerce:mark_sold",
                                     kwargs={"pk": self.product.pk}))
        self.assertEqual(r.status_code, 403)

    def test_restock_with_numeric_quantity(self):
        self.client.post(reverse("commerce:restock",
                                 kwargs={"pk": self.product.pk}),
                         {"quantity": "42"})
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_count, 42)

    def test_restock_with_negative_quantity_clamps_to_zero(self):
        self.client.post(reverse("commerce:restock",
                                 kwargs={"pk": self.product.pk}),
                         {"quantity": "-5"})
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_count, 0)

    def test_restock_with_unlimited_sets_none(self):
        self.client.post(reverse("commerce:restock",
                                 kwargs={"pk": self.product.pk}),
                         {"quantity": "unlimited"})
        self.product.refresh_from_db()
        self.assertIsNone(self.product.inventory_count)

    def test_restock_with_blank_sets_none(self):
        self.client.post(reverse("commerce:restock",
                                 kwargs={"pk": self.product.pk}),
                         {"quantity": ""})
        self.product.refresh_from_db()
        self.assertIsNone(self.product.inventory_count)

    def test_restock_with_garbage_quantity_sets_none(self):
        """Non-numeric input shouldn't blow up — the view catches
        ValueError and falls through to None (unlimited)."""
        self.client.post(reverse("commerce:restock",
                                 kwargs={"pk": self.product.pk}),
                         {"quantity": "lots"})
        self.product.refresh_from_db()
        self.assertIsNone(self.product.inventory_count)

    def test_restock_non_creator_403(self):
        self.client.force_login(make_user())
        r = self.client.post(reverse("commerce:restock",
                                     kwargs={"pk": self.product.pk}))
        self.assertEqual(r.status_code, 403)
