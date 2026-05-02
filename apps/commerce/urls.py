from django.urls import path

from . import views

app_name = "commerce"

urlpatterns = [
    # Creator product management
    path("my-products/", views.my_products, name="my_products"),
    path("my-products/add/", views.create_product, name="create_product"),
    path("my-products/<uuid:pk>/edit/", views.edit_product, name="edit_product"),
    path("my-products/<uuid:pk>/images/", views.product_images, name="product_images"),
    path("my-products/<uuid:pk>/images/add/", views.add_product_image, name="add_product_image"),
    path("my-products/<uuid:pk>/images/<int:image_pk>/delete/", views.delete_product_image, name="delete_product_image"),
    path("my-products/<uuid:pk>/mark-sold/", views.mark_sold, name="mark_sold"),
    path("my-products/<uuid:pk>/restock/", views.restock, name="restock"),
    path("my-sales/", views.my_sales, name="my_sales"),
    # Product groups
    path("groups/add/", views.create_group, name="create_group"),
    path("groups/<uuid:pk>/edit/", views.edit_group, name="edit_group"),
    path("groups/<uuid:pk>/items/", views.group_items, name="group_items"),
    path("groups/<uuid:pk>/items/add/", views.add_group_item, name="add_group_item"),
    path("groups/<uuid:pk>/items/<int:item_pk>/remove/", views.remove_group_item, name="remove_group_item"),
    # Stripe Connect onboarding
    path("connect/", views.connect_onboarding, name="connect_onboarding"),
    path("connect/return/", views.connect_return, name="connect_return"),
    path("connect/dashboard/", views.stripe_dashboard, name="stripe_dashboard"),
    # Checkout
    path("checkout/<uuid:product_id>/", views.create_checkout, name="create_checkout"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    # Stripe webhook
    path("webhooks/stripe/", views.stripe_webhook, name="stripe_webhook"),
    # Public pages (must be last — catches slugs)
    path("<slug:creator_slug>/group/<slug:group_slug>/", views.group_detail, name="group_detail"),
    path("<slug:creator_slug>/<slug:product_slug>/", views.product_detail, name="product_detail"),
]
