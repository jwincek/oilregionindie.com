import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from wagtail.fields import RichTextField

from apps.creators.models import CreatorProfile


class Product(models.Model):
    """Something a creator sells: digital music, artwork, jewelry, merch."""

    class ProductType(models.TextChoices):
        DIGITAL_MUSIC = "digital_music", "Digital Music"
        PHYSICAL_MUSIC = "physical_music", "Physical Music"
        ARTWORK = "artwork", "Artwork"
        JEWELRY = "jewelry", "Jewelry"
        MERCH = "merch", "Merch"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(
        CreatorProfile, on_delete=models.CASCADE, related_name="products"
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = RichTextField(blank=True)
    product_type = models.CharField(
        max_length=20, choices=ProductType.choices, default=ProductType.OTHER
    )

    # Pricing
    price_cents = models.PositiveIntegerField(help_text="Price in cents (e.g., 1000 = $10.00)")
    currency = models.CharField(max_length=3, default="USD")

    # Digital delivery
    is_digital = models.BooleanField(default=False)
    file = models.FileField(upload_to="commerce/downloads/", blank=True)

    # Inventory (null = unlimited, for digital products)
    inventory_count = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Leave blank for unlimited (digital products)",
    )

    is_active = models.BooleanField(default=True)
    shipping_cents = models.PositiveIntegerField(
        default=0,
        help_text="Flat-rate shipping cost in cents (0 = free shipping)",
    )
    shipping_note = models.TextField(blank=True, help_text="Shipping info for physical items")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["creator", "slug"],
                name="unique_product_slug_per_creator",
            ),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse(
            "commerce:product_detail",
            kwargs={"creator_slug": self.creator.slug, "product_slug": self.slug},
        )

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Product.objects.filter(
                creator=self.creator, slug=slug
            ).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def price_display(self):
        return f"${self.price_cents / 100:.2f}"

    @property
    def shipping_display(self):
        if self.is_digital or self.shipping_cents == 0:
            return "Free shipping" if not self.is_digital else None
        return f"${self.shipping_cents / 100:.2f} shipping"

    @property
    def in_stock(self):
        if self.inventory_count is None:
            return True
        return self.inventory_count > 0


class ProductImage(models.Model):
    """Product photo — owned by a single product."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="commerce/products/")
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.alt_text or f"Image for {self.product.title}"


class ProductGroup(models.Model):
    """
    A group of related products — either a collection (items sold individually
    with a bundle discount) or a set (items only sold together).
    """

    class GroupType(models.TextChoices):
        COLLECTION = "collection", "Collection"
        SET = "set", "Set"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(
        CreatorProfile, on_delete=models.CASCADE, related_name="product_groups",
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = RichTextField(blank=True)
    group_type = models.CharField(
        max_length=20, choices=GroupType.choices, default=GroupType.COLLECTION,
    )
    bundle_price_cents = models.IntegerField(
        help_text="Price for the entire group",
    )
    image = models.ImageField(upload_to="commerce/groups/", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while ProductGroup.objects.filter(
                creator=self.creator, slug=slug
            ).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("commerce:group_detail", kwargs={
            "creator_slug": self.creator.slug,
            "group_slug": self.slug,
        })

    @property
    def bundle_price_display(self):
        return f"${self.bundle_price_cents / 100:.2f}"

    @property
    def individual_total_cents(self):
        """Sum of individual item prices."""
        return sum(item.product.price_cents for item in self.items.select_related("product").all())

    @property
    def individual_total_display(self):
        return f"${self.individual_total_cents / 100:.2f}"

    @property
    def savings_cents(self):
        return self.individual_total_cents - self.bundle_price_cents

    @property
    def savings_display(self):
        savings = self.savings_cents
        if savings > 0:
            return f"${savings / 100:.2f}"
        return None

    @property
    def is_collection(self):
        return self.group_type == self.GroupType.COLLECTION

    @property
    def is_set(self):
        return self.group_type == self.GroupType.SET


class ProductGroupItem(models.Model):
    """A product within a group, with ordering."""

    group = models.ForeignKey(
        ProductGroup, on_delete=models.CASCADE, related_name="items",
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="group_memberships",
    )
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "product"],
                name="unique_product_per_group",
            ),
        ]

    def __str__(self):
        return f"{self.product.title} in {self.group.title}"


class Order(models.Model):
    """
    A purchase transaction. Contains one or more OrderItems.
    Tracks the buyer, Stripe session, and overall status.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FULFILLED = "fulfilled", "Fulfilled"
        PARTIALLY_FULFILLED = "partially_fulfilled", "Partially Fulfilled"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer_email = models.EmailField()
    buyer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    # Stripe references
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_payment_id = models.CharField(max_length=255, blank=True)

    status = models.CharField(
        max_length=25, choices=Status.choices, default=Status.PENDING
    )

    # Shipping (physical items)
    shipping_address = models.JSONField(null=True, blank=True)

    # Totals (denormalized for quick access; authoritative values live on items)
    total_cents = models.PositiveIntegerField(default=0)
    platform_fee_cents = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.id} ({self.get_status_display()})"

    def recalculate_totals(self):
        """Recalculate total and platform fee from items."""
        items = self.items.all()
        self.total_cents = sum(item.line_total_cents for item in items)
        self.platform_fee_cents = sum(item.platform_fee_cents for item in items)
        self.save(update_fields=["total_cents", "platform_fee_cents"])


class OrderItem(models.Model):
    """A single line item within an order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    creator = models.ForeignKey(
        CreatorProfile, on_delete=models.PROTECT, related_name="order_items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="order_items"
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price_cents = models.PositiveIntegerField(
        help_text="Price per unit at time of purchase (snapshot)",
    )
    platform_fee_cents = models.PositiveIntegerField(default=0)

    # Stripe transfer for this item's creator
    stripe_transfer_id = models.CharField(max_length=255, blank=True)

    # Fulfillment
    is_fulfilled = models.BooleanField(default=False)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    tracking_number = models.CharField(max_length=255, blank=True)
    download_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order__created_at"]

    def __str__(self):
        return f"{self.quantity}x {self.product.title} in Order {self.order_id}"

    @property
    def line_total_cents(self):
        return self.unit_price_cents * self.quantity
