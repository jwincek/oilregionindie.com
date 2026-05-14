"""
Tests for product-group views: create_group, edit_group, group_items,
add_group_item, remove_group_item.
"""

from django.test import TestCase
from django.urls import reverse

from apps.commerce.models import ProductGroup, ProductGroupItem

from .helpers import (
    make_group, make_group_item, make_payable_creator, make_product, make_user,
)


class CreateGroupViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.client.force_login(self.owner)

    def test_no_creator_profile_redirects_to_setup(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("commerce:create_group"))
        self.assertRedirects(r, reverse("creators:setup"),
                             fetch_redirect_response=False)

    def test_get_renders_form(self):
        r = self.client.get(reverse("commerce:create_group"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("form", r.context)

    def test_post_creates_group_and_redirects_to_edit(self):
        """Newly-created group lands on edit_group so the user can add
        products to it."""
        r = self.client.post(reverse("commerce:create_group"), {
            "title": "Album Bundle",
            "description": "Buy all three",
            "group_type": ProductGroup.GroupType.COLLECTION,
            "bundle_price_dollars": "25.00",
            "is_active": "on",
        })
        group = ProductGroup.objects.get(title="Album Bundle")
        self.assertRedirects(r, reverse("commerce:edit_group",
                                        kwargs={"pk": group.pk}))
        self.assertEqual(group.creator, self.creator)
        self.assertEqual(group.bundle_price_cents, 2500)


class EditGroupViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.group = make_group(creator=self.creator, title="Original")

    def test_no_creator_profile_redirects(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("commerce:edit_group",
                                    kwargs={"pk": self.group.pk}))
        self.assertRedirects(r, reverse("creators:setup"),
                             fetch_redirect_response=False)

    def test_other_creator_404s(self):
        other = make_user()
        make_payable_creator(user=other)
        self.client.force_login(other)
        r = self.client.get(reverse("commerce:edit_group",
                                    kwargs={"pk": self.group.pk}))
        self.assertEqual(r.status_code, 404)

    def test_owner_loads_form(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("commerce:edit_group",
                                    kwargs={"pk": self.group.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["group"], self.group)

    def test_owner_saves_changes(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("commerce:edit_group",
                                     kwargs={"pk": self.group.pk}), {
            "title": "Updated",
            "description": "New",
            "group_type": ProductGroup.GroupType.COLLECTION,
            "bundle_price_dollars": "30.00",
            "is_active": "on",
        })
        self.assertRedirects(r, reverse("commerce:my_products"))
        self.group.refresh_from_db()
        self.assertEqual(self.group.title, "Updated")
        self.assertEqual(self.group.bundle_price_cents, 3000)


class GroupItemsViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.group = make_group(creator=self.creator)
        self.product = make_product(creator=self.creator, title="A Product")

    def test_non_creator_user_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("commerce:group_items",
                                    kwargs={"pk": self.group.pk}))
        self.assertEqual(r.status_code, 403)

    def test_renders_partial_with_items_and_available_products(self):
        in_group = make_group_item(self.group, self.product)
        # A second, NOT-in-group product should appear in available_products.
        outside = make_product(creator=self.creator, title="Outside Product")
        self.client.force_login(self.owner)
        r = self.client.get(reverse("commerce:group_items",
                                    kwargs={"pk": self.group.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertIn(in_group, r.context["items"])
        self.assertIn(outside, list(r.context["available_products"]))
        # The already-in-group product is excluded from available list.
        self.assertNotIn(self.product, list(r.context["available_products"]))


class AddGroupItemViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.group = make_group(creator=self.creator)
        self.product = make_product(creator=self.creator)
        self.client.force_login(self.owner)

    def test_non_creator_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.post(reverse("commerce:add_group_item",
                                     kwargs={"pk": self.group.pk}),
                             {"product_id": str(self.product.pk)})
        self.assertEqual(r.status_code, 403)

    def test_adds_product_to_group(self):
        r = self.client.post(reverse("commerce:add_group_item",
                                     kwargs={"pk": self.group.pk}),
                             {"product_id": str(self.product.pk)})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            ProductGroupItem.objects.filter(group=self.group,
                                            product=self.product).exists()
        )

    def test_adding_same_product_twice_is_idempotent(self):
        """View uses get_or_create — re-posting the same product doesn't
        create a duplicate ProductGroupItem row."""
        for _ in range(2):
            self.client.post(reverse("commerce:add_group_item",
                                     kwargs={"pk": self.group.pk}),
                             {"product_id": str(self.product.pk)})
        self.assertEqual(
            ProductGroupItem.objects.filter(group=self.group,
                                            product=self.product).count(),
            1,
        )

    def test_blank_product_id_is_no_op_200(self):
        """POST without a product_id falls through to re-rendering the
        partial — no row created, no 500."""
        r = self.client.post(reverse("commerce:add_group_item",
                                     kwargs={"pk": self.group.pk}), {})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ProductGroupItem.objects.count(), 0)

    def test_cannot_add_other_creators_product(self):
        """get_object_or_404 on the product is scoped to creator — adding
        a product from a different creator's catalog 404s."""
        other_owner = make_user()
        other = make_payable_creator(user=other_owner)
        outsider_product = make_product(creator=other)
        r = self.client.post(reverse("commerce:add_group_item",
                                     kwargs={"pk": self.group.pk}),
                             {"product_id": str(outsider_product.pk)})
        self.assertEqual(r.status_code, 404)


class RemoveGroupItemViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_payable_creator(user=self.owner)
        self.group = make_group(creator=self.creator)
        self.product = make_product(creator=self.creator)
        self.item = make_group_item(self.group, self.product)
        self.client.force_login(self.owner)

    def test_non_creator_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.post(reverse("commerce:remove_group_item",
                                     kwargs={"pk": self.group.pk,
                                             "item_pk": self.item.pk}))
        self.assertEqual(r.status_code, 403)

    def test_owner_removes_item(self):
        r = self.client.post(reverse("commerce:remove_group_item",
                                     kwargs={"pk": self.group.pk,
                                             "item_pk": self.item.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(
            ProductGroupItem.objects.filter(pk=self.item.pk).exists()
        )

    def test_other_creators_group_404s(self):
        other = make_user()
        make_payable_creator(user=other)
        self.client.force_login(other)
        r = self.client.post(reverse("commerce:remove_group_item",
                                     kwargs={"pk": self.group.pk,
                                             "item_pk": self.item.pk}))
        self.assertEqual(r.status_code, 404)
