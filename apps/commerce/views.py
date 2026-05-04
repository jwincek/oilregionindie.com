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

from django.contrib import messages

from apps.creators.models import CreatorProfile

from . import stripe_service
from .forms import ProductForm, ProductGroupForm, ProductImageForm
from .models import Order, OrderItem, Product, ProductGroup, ProductGroupItem, ProductImage

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
        shipping = product.shipping_cents if not product.is_digital else 0
        subtotal = product.price_cents * quantity + shipping
        item_fee = int(product.price_cents * quantity * fee_percent / 100)

        order = Order.objects.create(
            buyer_email=buyer_email or "",
            buyer_user=request.user if request.user.is_authenticated else None,
            stripe_checkout_session_id=session.id,
            total_cents=subtotal,
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


@login_required
def download(request, item_pk):
    """Serve a digital product file to a buyer who has purchased it."""
    from django.http import FileResponse

    item = get_object_or_404(
        OrderItem.objects.select_related("order", "product"),
        pk=item_pk,
        is_fulfilled=True,
    )

    # Verify the user owns this order
    if item.order.buyer_user != request.user:
        from django.http import Http404
        raise Http404

    if not item.product.is_digital or not item.product.file:
        from django.http import Http404
        raise Http404

    # Increment download count
    item.download_count += 1
    item.save(update_fields=["download_count"])

    return FileResponse(
        item.product.file.open("rb"),
        as_attachment=True,
        filename=item.product.file.name.split("/")[-1],
    )


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


# ---------------------------------------------------------------------------
# Creator product management
# ---------------------------------------------------------------------------


@login_required
def my_products(request):
    """List the current creator's products."""
    if not hasattr(request.user, "creator_profile"):
        messages.info(request, "Create a creator profile first to manage products.")
        return redirect("creators:setup")
    profile = request.user.creator_profile
    products = profile.products.order_by("-created_at")
    groups = profile.product_groups.prefetch_related("items").order_by("-created_at")
    return render(request, "commerce/my_products.html", {
        "profile": profile,
        "products": products,
        "groups": groups,
    })


@login_required
def create_product(request):
    """Create a new product."""
    if not hasattr(request.user, "creator_profile"):
        return redirect("creators:setup")
    profile = request.user.creator_profile

    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.creator = profile
            product.save()
            messages.success(request, f'"{product.title}" created.')
            return redirect("commerce:my_products")
    else:
        form = ProductForm()

    return render(request, "commerce/product_form.html", {
        "form": form,
        "profile": profile,
    })


@login_required
def edit_product(request, pk):
    """Edit an existing product."""
    if not hasattr(request.user, "creator_profile"):
        return redirect("creators:setup")
    profile = request.user.creator_profile
    product = get_object_or_404(Product, pk=pk, creator=profile)

    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f'"{product.title}" updated.')
            return redirect("commerce:my_products")
    else:
        form = ProductForm(instance=product)

    return render(request, "commerce/product_form.html", {
        "form": form,
        "profile": profile,
        "product": product,
    })


@login_required
def my_sales(request):
    """Show orders containing the current creator's products."""
    if not hasattr(request.user, "creator_profile"):
        return redirect("creators:setup")
    profile = request.user.creator_profile
    items = OrderItem.objects.filter(
        creator=profile,
        order__status__in=[Order.Status.PAID, Order.Status.FULFILLED, Order.Status.PARTIALLY_FULFILLED],
    ).select_related("order", "product").order_by("-order__created_at")

    return render(request, "commerce/my_sales.html", {
        "profile": profile,
        "items": items,
    })


@login_required
def order_detail(request, pk):
    """Creator view of a specific order's items."""
    if not hasattr(request.user, "creator_profile"):
        return redirect("creators:setup")
    profile = request.user.creator_profile

    order = get_object_or_404(Order, pk=pk)
    items = order.items.filter(creator=profile).select_related("product")
    if not items.exists():
        from django.http import Http404
        raise Http404

    return render(request, "commerce/order_detail.html", {
        "order": order,
        "items": items,
        "profile": profile,
    })


@login_required
@require_POST
def mark_shipped(request, item_pk):
    """Mark an order item as shipped with optional tracking number."""
    if not hasattr(request.user, "creator_profile"):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    item = get_object_or_404(OrderItem, pk=item_pk, creator=request.user.creator_profile)
    tracking = request.POST.get("tracking_number", "").strip()

    item.is_fulfilled = True
    item.fulfilled_at = timezone.now()
    item.tracking_number = tracking
    item.save(update_fields=["is_fulfilled", "fulfilled_at", "tracking_number"])

    # Check if all items in the order are fulfilled
    order = item.order
    if not order.items.filter(is_fulfilled=False).exists():
        order.status = Order.Status.FULFILLED
        order.save(update_fields=["status"])

    # Notify the buyer
    if order.buyer_email:
        from django.core.mail import send_mail
        site_name = getattr(settings, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub")
        tracking_line = f"\nTracking number: {tracking}\n" if tracking else ""
        send_mail(
            subject=f"[{site_name}] Your order has shipped!",
            message=(
                f"Good news — {item.product.title} from {item.creator.display_name} has shipped!\n"
                f"{tracking_line}\n"
                f"If you have questions, contact the creator directly.\n\n"
                f"{site_name}"
            ),
            from_email=None,
            recipient_list=[order.buyer_email],
            fail_silently=True,
        )

    messages.success(request, f'"{item.product.title}" marked as shipped.')
    return redirect("commerce:order_detail", pk=order.pk)


# ---------------------------------------------------------------------------
# Product image management (HTMX)
# ---------------------------------------------------------------------------


def _get_owned_product(request, pk):
    """Get a product the current user owns."""
    if not hasattr(request.user, "creator_profile"):
        return None
    return get_object_or_404(Product, pk=pk, creator=request.user.creator_profile)


@login_required
def product_images(request, pk):
    """List product images (HTMX partial)."""
    product = _get_owned_product(request, pk)
    if not product:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    return render(request, "commerce/_product_images.html", {
        "product": product,
        "images": product.images.all(),
    })


@login_required
def add_product_image(request, pk):
    """Add an image to a product via HTMX."""
    product = _get_owned_product(request, pk)
    if not product:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == "POST":
        form = ProductImageForm(request.POST, request.FILES)
        if form.is_valid():
            img = form.save(commit=False)
            img.product = product
            img.save()
            return render(request, "commerce/_product_images.html", {
                "product": product,
                "images": product.images.all(),
            })
    else:
        next_order = product.images.count()
        form = ProductImageForm(initial={"sort_order": next_order})

    return render(request, "commerce/_product_image_form.html", {
        "form": form,
        "product": product,
    })


@login_required
@require_POST
def delete_product_image(request, pk, image_pk):
    """Delete a product image via HTMX."""
    product = _get_owned_product(request, pk)
    if not product:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    img = get_object_or_404(ProductImage, pk=image_pk, product=product)
    img.delete()
    return render(request, "commerce/_product_images.html", {
        "product": product,
        "images": product.images.all(),
    })


@login_required
@require_POST
def mark_sold(request, pk):
    """Mark a product as sold out (set inventory to 0)."""
    product = _get_owned_product(request, pk)
    if not product:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    product.inventory_count = 0
    product.save(update_fields=["inventory_count", "updated_at"])
    messages.success(request, f'"{product.title}" marked as sold out.')
    return redirect("commerce:my_products")


@login_required
@require_POST
def restock(request, pk):
    """Restock a product (set inventory to a specified amount, or unlimited)."""
    product = _get_owned_product(request, pk)
    if not product:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    quantity = request.POST.get("quantity", "").strip()
    if quantity == "" or quantity == "unlimited":
        product.inventory_count = None
    else:
        try:
            product.inventory_count = max(0, int(quantity))
        except ValueError:
            product.inventory_count = None
    product.save(update_fields=["inventory_count", "updated_at"])
    messages.success(request, f'"{product.title}" inventory updated.')
    return redirect("commerce:my_products")


# ---------------------------------------------------------------------------
# Product groups (collections & sets)
# ---------------------------------------------------------------------------


@require_GET
def group_detail(request, creator_slug, group_slug):
    """Public product group page."""
    group = get_object_or_404(
        ProductGroup.objects.select_related("creator").prefetch_related(
            "items__product__images"
        ),
        creator__slug=creator_slug,
        slug=group_slug,
        is_active=True,
    )
    return render(request, "commerce/group_detail.html", {"group": group})


@login_required
def create_group(request):
    """Create a product group."""
    if not hasattr(request.user, "creator_profile"):
        return redirect("creators:setup")
    profile = request.user.creator_profile

    if request.method == "POST":
        form = ProductGroupForm(request.POST, request.FILES, creator=profile)
        if form.is_valid():
            group = form.save()
            messages.success(request, f'Group "{group.title}" created. Now add products to it.')
            return redirect("commerce:edit_group", pk=group.pk)
    else:
        form = ProductGroupForm(creator=profile)

    return render(request, "commerce/group_form.html", {
        "form": form,
        "profile": profile,
    })


@login_required
def edit_group(request, pk):
    """Edit a product group."""
    if not hasattr(request.user, "creator_profile"):
        return redirect("creators:setup")
    profile = request.user.creator_profile
    group = get_object_or_404(ProductGroup, pk=pk, creator=profile)

    if request.method == "POST":
        form = ProductGroupForm(request.POST, request.FILES, instance=group, creator=profile)
        if form.is_valid():
            form.save()
            messages.success(request, f'Group "{group.title}" updated.')
            return redirect("commerce:my_products")
    else:
        form = ProductGroupForm(instance=group, creator=profile)

    return render(request, "commerce/group_form.html", {
        "form": form,
        "profile": profile,
        "group": group,
    })


@login_required
def group_items(request, pk):
    """List items in a product group (HTMX partial)."""
    if not hasattr(request.user, "creator_profile"):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    group = get_object_or_404(ProductGroup, pk=pk, creator=request.user.creator_profile)
    return render(request, "commerce/_group_items.html", {
        "group": group,
        "items": group.items.select_related("product").all(),
        "available_products": request.user.creator_profile.products.exclude(
            pk__in=group.items.values_list("product_id", flat=True)
        ).order_by("title"),
    })


@login_required
@require_POST
def add_group_item(request, pk):
    """Add a product to a group via HTMX."""
    if not hasattr(request.user, "creator_profile"):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    group = get_object_or_404(ProductGroup, pk=pk, creator=request.user.creator_profile)
    product_id = request.POST.get("product_id")
    if product_id:
        product = get_object_or_404(Product, pk=product_id, creator=request.user.creator_profile)
        next_order = group.items.count()
        ProductGroupItem.objects.get_or_create(
            group=group, product=product,
            defaults={"sort_order": next_order},
        )
    return render(request, "commerce/_group_items.html", {
        "group": group,
        "items": group.items.select_related("product").all(),
        "available_products": request.user.creator_profile.products.exclude(
            pk__in=group.items.values_list("product_id", flat=True)
        ).order_by("title"),
    })


@login_required
@require_POST
def remove_group_item(request, pk, item_pk):
    """Remove a product from a group via HTMX."""
    if not hasattr(request.user, "creator_profile"):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    group = get_object_or_404(ProductGroup, pk=pk, creator=request.user.creator_profile)
    item = get_object_or_404(ProductGroupItem, pk=item_pk, group=group)
    item.delete()
    return render(request, "commerce/_group_items.html", {
        "group": group,
        "items": group.items.select_related("product").all(),
        "available_products": request.user.creator_profile.products.exclude(
            pk__in=group.items.values_list("product_id", flat=True)
        ).order_by("title"),
    })


# --- Stripe Connect onboarding ---


@login_required
def connect_setup(request):
    """Pre-onboarding page — explains payments before redirecting to Stripe."""
    profile = get_object_or_404(CreatorProfile, user=request.user)
    platform_fee = settings.STRIPE_PLATFORM_FEE_PERCENT

    # Check current status if they've started onboarding
    account_status = None
    if profile.stripe_account_id:
        try:
            account_status = stripe_service.check_account_status(profile.stripe_account_id)
        except Exception:
            account_status = None

    return render(request, "commerce/connect_setup.html", {
        "profile": profile,
        "platform_fee": platform_fee,
        "account_status": account_status,
    })


@login_required
def connect_onboarding(request):
    """Start or resume Stripe Connect onboarding."""
    profile = get_object_or_404(CreatorProfile, user=request.user)

    try:
        if not profile.stripe_account_id:
            account_id = stripe_service.create_connect_account(profile)
            profile.stripe_account_id = account_id
            profile.save(update_fields=["stripe_account_id"])

        return_url = request.build_absolute_uri(reverse("commerce:connect_return"))
        refresh_url = request.build_absolute_uri(reverse("commerce:connect_setup"))

        onboarding_url = stripe_service.create_onboarding_link(
            profile.stripe_account_id, return_url, refresh_url
        )
        return redirect(onboarding_url)

    except Exception:
        logger.exception("Stripe Connect onboarding failed")
        messages.error(
            request,
            "Unable to connect to Stripe right now. Please check that Stripe is configured correctly and try again."
        )
        return redirect("commerce:connect_setup")


@login_required
def connect_return(request):
    """Return URL after Stripe Connect onboarding."""
    profile = get_object_or_404(CreatorProfile, user=request.user)

    account_status = None
    if profile.stripe_account_id:
        try:
            account_status = stripe_service.check_account_status(profile.stripe_account_id)
            if account_status["details_submitted"] and account_status["charges_enabled"]:
                profile.stripe_onboarded = True
                profile.save(update_fields=["stripe_onboarded"])
        except Exception:
            logger.exception("Failed to check Stripe account status")
            account_status = None

    return render(request, "commerce/connect_return.html", {
        "profile": profile,
        "account_status": account_status,
    })


@login_required
def stripe_dashboard(request):
    """Redirect creator to their Stripe Express dashboard."""
    profile = get_object_or_404(CreatorProfile, user=request.user)

    if not profile.stripe_account_id:
        return redirect("commerce:connect_setup")

    try:
        dashboard_url = stripe_service.create_login_link(profile.stripe_account_id)
        return redirect(dashboard_url)
    except Exception:
        logger.exception("Failed to create Stripe dashboard link")
        messages.error(request, "Unable to access the Stripe dashboard right now. Please try again.")
        return redirect("commerce:connect_setup")
