from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.listing, name="listing"),
    path("past/", views.past, name="past"),
    path("create/", views.create, name="create"),
    # Booking requests
    path("bookings/", views.booking_inbox, name="booking_inbox"),
    path("bookings/<uuid:pk>/", views.booking_detail, name="booking_detail"),
    path("bookings/<uuid:pk>/respond/", views.booking_respond, name="booking_respond"),
    path("bookings/<uuid:pk>/withdraw/", views.booking_withdraw, name="booking_withdraw"),
    path("bookings/new/<str:direction>/<slug:profile_slug>/", views.booking_create, name="booking_create"),
    # Events (slug-based — must be last)
    path("<slug:slug>/", views.detail, name="detail"),
    path("<slug:slug>/edit/", views.edit, name="edit"),
]
