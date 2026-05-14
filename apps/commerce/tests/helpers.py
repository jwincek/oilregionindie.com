"""
Shared test helpers for the commerce app.
"""

from apps.commerce.models import (
    Order, OrderItem, Product, ProductGroup, ProductGroupItem,
)
from apps.creators.tests.helpers import make_creator, make_user  # noqa: F401


def make_product(
    creator=None,
    title="Test Product",
    price_cents=1000,
    is_active=True,
    is_digital=False,
    inventory_count=None,
    shipping_cents=0,
    **kwargs,
):
    if creator is None:
        creator = make_creator(user=make_user())
    return Product.objects.create(
        creator=creator,
        title=title,
        price_cents=price_cents,
        is_active=is_active,
        is_digital=is_digital,
        inventory_count=inventory_count,
        shipping_cents=shipping_cents,
        product_type=kwargs.pop("product_type", Product.ProductType.OTHER),
        **kwargs,
    )


def make_payable_creator(user=None, **kwargs):
    """
    A creator who has finished Stripe onboarding — `can_accept_payments`
    returns True. Used by checkout tests.
    """
    if user is None:
        user = make_user()
    return make_creator(
        user=user,
        stripe_account_id="acct_test_fake",
        stripe_onboarded=True,
        **kwargs,
    )


def make_order(
    buyer_user=None,
    buyer_email="buyer@example.com",
    status=Order.Status.PENDING,
    stripe_checkout_session_id="cs_test_fake",
    total_cents=1000,
    **kwargs,
):
    return Order.objects.create(
        buyer_user=buyer_user,
        buyer_email=buyer_email,
        status=status,
        stripe_checkout_session_id=stripe_checkout_session_id,
        total_cents=total_cents,
        **kwargs,
    )


def make_order_item(order, product, quantity=1, **kwargs):
    return OrderItem.objects.create(
        order=order,
        creator=product.creator,
        product=product,
        quantity=quantity,
        unit_price_cents=product.price_cents,
        platform_fee_cents=kwargs.pop("platform_fee_cents", 0),
        **kwargs,
    )


def make_group(creator=None, title="Test Group", group_type="collection", **kwargs):
    if creator is None:
        creator = make_creator(user=make_user())
    return ProductGroup.objects.create(
        creator=creator,
        title=title,
        group_type=group_type,
        bundle_price_cents=kwargs.pop("bundle_price_cents", 5000),
        **kwargs,
    )


def make_group_item(group, product, **kwargs):
    return ProductGroupItem.objects.create(
        group=group, product=product,
        sort_order=kwargs.pop("sort_order", 0),
        **kwargs,
    )
