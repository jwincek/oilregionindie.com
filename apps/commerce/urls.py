from django.urls import path

from . import views

app_name = "commerce"

urlpatterns = [
    # Stripe Connect onboarding
    path("connect/", views.connect_onboarding, name="connect_onboarding"),
    path("connect/return/", views.connect_return, name="connect_return"),
    path("connect/dashboard/", views.stripe_dashboard, name="stripe_dashboard"),
    # Checkout
    path("checkout/<uuid:product_id>/", views.create_checkout, name="create_checkout"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    # Stripe webhook
    path("webhooks/stripe/", views.stripe_webhook, name="stripe_webhook"),
    # Product detail
    path("<slug:creator_slug>/<slug:product_slug>/", views.product_detail, name="product_detail"),
]
