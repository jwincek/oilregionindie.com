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
    path("bookings/<uuid:pk>/feedback/", views.booking_feedback, name="booking_feedback"),
    # Endorsements
    path("endorse/<slug:creator_slug>/<slug:venue_slug>/", views.endorse, name="endorse"),
    path("endorsement/<uuid:pk>/delete/", views.delete_endorsement, name="delete_endorsement"),
    # Events (slug-based — must be last)
    path("<slug:slug>/", views.detail, name="detail"),
    path("<slug:slug>/edit/", views.edit, name="edit"),
    # Lineup management (HTMX)
    path("<slug:slug>/lineup/", views.lineup, name="lineup"),
    path("<slug:slug>/lineup/add/", views.add_slot, name="add_slot"),
    path("<slug:slug>/lineup/<uuid:pk>/edit/", views.edit_slot, name="edit_slot"),
    path("<slug:slug>/lineup/<uuid:pk>/delete/", views.delete_slot, name="delete_slot"),
]
