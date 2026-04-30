from django.urls import path

from . import views

app_name = "commerce"

urlpatterns = [
    # Creator product management
    path("my-products/", views.my_products, name="my_products"),
    path("my-products/add/", views.create_product, name="create_product"),
    path("my-products/<uuid:pk>/edit/", views.edit_product, name="edit_product"),
    path("my-sales/", views.my_sales, name="my_sales"),
    # Stripe Connect onboarding
    path("connect/", views.connect_onboarding, name="connect_onboarding"),
    path("connect/return/", views.connect_return, name="connect_return"),
    path("connect/dashboard/", views.stripe_dashboard, name="stripe_dashboard"),
    # Checkout
    path("checkout/<uuid:product_id>/", views.create_checkout, name="create_checkout"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    # Stripe webhook
    path("webhooks/stripe/", views.stripe_webhook, name="stripe_webhook"),
    # Product detail (must be last — catches slugs)
    path("<slug:creator_slug>/<slug:product_slug>/", views.product_detail, name="product_detail"),
]
