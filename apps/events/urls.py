from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.listing, name="listing"),
    path("past/", views.past, name="past"),
    path("create/", views.create, name="create"),
    path("<slug:slug>/", views.detail, name="detail"),
    path("<slug:slug>/edit/", views.edit, name="edit"),
]
