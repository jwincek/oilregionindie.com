from django.contrib import admin

from .models import Order, OrderItem, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ["image", "alt_text", "sort_order"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["title", "creator", "product_type", "price_display", "is_active", "in_stock"]
    list_filter = ["is_active", "product_type", "is_digital"]
    search_fields = ["title", "description", "creator__display_name"]
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ProductImageInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ["product", "creator", "quantity", "unit_price_cents", "platform_fee_cents", "is_fulfilled"]
    readonly_fields = ["stripe_transfer_id", "download_count"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "buyer_email", "total_cents", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["buyer_email", "stripe_payment_id", "stripe_checkout_session_id"]
    readonly_fields = [
        "stripe_payment_id", "stripe_checkout_session_id",
    ]
    inlines = [OrderItemInline]
    date_hierarchy = "created_at"
