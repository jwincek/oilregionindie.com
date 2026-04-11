import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.creators.models import CreatorProfile

from . import stripe_service
from .models import Order, OrderItem, Product

logger = logging.getLogger(__name__)


@require_GET
def product_detail(request, creator_slug, product_slug):
    """Product detail page."""
    product = get_object_or_404(
        Product.objects.select_related("creator"),
        creator__slug=creator_slug,
        slug=product_slug,
        is_active=True,
    )
    return render(request, "commerce/product_detail.html", {"product": product})


@require_POST
def create_checkout(request, product_id):
    """Create a Stripe Checkout Session and redirect to it."""
    product = get_object_or_404(Product, id=product_id, is_active=True)

    if not product.creator.can_accept_payments:
        return render(request, "commerce/payment_unavailable.html", {"product": product})

    if not product.in_stock:
        return render(request, "commerce/out_of_stock.html", {"product": product})

    quantity = int(request.POST.get("quantity", 1))
    buyer_email = request.user.email if request.user.is_authenticated else None

    success_url = request.build_absolute_uri(
        reverse("commerce:checkout_success") + "?session_id={CHECKOUT_SESSION_ID}"
    )
    cancel_url = request.build_absolute_uri(product.get_absolute_url())

    try:
        session = stripe_service.create_checkout_session(
            product=product,
            quantity=quantity,
            success_url=success_url,
            cancel_url=cancel_url,
            buyer_email=buyer_email,
        )

        # Create pending order with item
        fee_percent = settings.STRIPE_PLATFORM_FEE_PERCENT
        item_fee = int(product.price_cents * quantity * fee_percent / 100)

        order = Order.objects.create(
            buyer_email=buyer_email or "",
            buyer_user=request.user if request.user.is_authenticated else None,
            stripe_checkout_session_id=session.id,
            total_cents=product.price_cents * quantity,
            platform_fee_cents=item_fee,
            status=Order.Status.PENDING,
        )
        OrderItem.objects.create(
            order=order,
            creator=product.creator,
            product=product,
            quantity=quantity,
            unit_price_cents=product.price_cents,
            platform_fee_cents=item_fee,
        )

        return redirect(session.url)

    except Exception:
        logger.exception("Failed to create checkout session")
        return render(request, "commerce/checkout_error.html", {"product": product})


@require_GET
def checkout_success(request):
    """Post-checkout success page."""
    session_id = request.GET.get("session_id")
    order = None
    if session_id:
        order = Order.objects.filter(stripe_checkout_session_id=session_id).first()
    return render(request, "commerce/checkout_success.html", {"order": order})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Handle Stripe webhook events."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        event = stripe_service.construct_webhook_event(payload, sig_header)
    except Exception:
        logger.exception("Webhook signature verification failed")
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        _handle_checkout_completed(session)
    elif event["type"] == "payment_intent.payment_failed":
        intent = event["data"]["object"]
        _handle_payment_failed(intent)

    return HttpResponse(status=200)


def _handle_checkout_completed(session):
    """Mark order as paid after successful checkout."""
    order = Order.objects.prefetch_related("items__product").filter(
        stripe_checkout_session_id=session["id"]
    ).first()
    if order:
        order.status = Order.Status.PAID
        order.stripe_payment_id = session.get("payment_intent", "")
        order.buyer_email = session.get("customer_details", {}).get("email", order.buyer_email)

        # Store shipping address for physical items
        shipping = session.get("shipping_details")
        if shipping:
            order.shipping_address = shipping

        order.save()

        # Process each item: auto-fulfill digital, decrement inventory for physical
        all_fulfilled = True
        for item in order.items.select_related("product").all():
            product = item.product

            if product.is_digital:
                item.is_fulfilled = True
                item.fulfilled_at = timezone.now()
                item.save(update_fields=["is_fulfilled", "fulfilled_at"])
            else:
                all_fulfilled = False

            if product.inventory_count is not None:
                product.inventory_count = max(0, product.inventory_count - item.quantity)
                product.save(update_fields=["inventory_count"])

        if all_fulfilled:
            order.status = Order.Status.FULFILLED
        order.save(update_fields=["status"])
        logger.info("Order %s marked as %s", order.id, order.status)


def _handle_payment_failed(intent):
    """Mark order as failed."""
    orders = Order.objects.filter(stripe_payment_id=intent["id"])
    orders.update(status=Order.Status.FAILED)


# --- Stripe Connect onboarding ---

@login_required
def connect_onboarding(request):
    """Start Stripe Connect onboarding for a creator."""
    profile = get_object_or_404(CreatorProfile, user=request.user)

    if not profile.stripe_account_id:
        account_id = stripe_service.create_connect_account(profile)
        profile.stripe_account_id = account_id
        profile.save(update_fields=["stripe_account_id"])

    return_url = request.build_absolute_uri(reverse("commerce:connect_return"))
    refresh_url = request.build_absolute_uri(reverse("commerce:connect_onboarding"))

    onboarding_url = stripe_service.create_onboarding_link(
        profile.stripe_account_id, return_url, refresh_url
    )
    return redirect(onboarding_url)


@login_required
def connect_return(request):
    """Return URL after Stripe Connect onboarding."""
    profile = get_object_or_404(CreatorProfile, user=request.user)

    if profile.stripe_account_id:
        status = stripe_service.check_account_status(profile.stripe_account_id)
        if status["details_submitted"] and status["charges_enabled"]:
            profile.stripe_onboarded = True
            profile.save(update_fields=["stripe_onboarded"])

    return render(request, "commerce/connect_return.html", {"profile": profile})


@login_required
def stripe_dashboard(request):
    """Redirect creator to their Stripe Express dashboard."""
    profile = get_object_or_404(CreatorProfile, user=request.user)

    if not profile.stripe_account_id:
        return redirect("commerce:connect_onboarding")

    dashboard_url = stripe_service.create_login_link(profile.stripe_account_id)
    return redirect(dashboard_url)
