from django.urls import path

from . import views

app_name = "venues"

urlpatterns = [
    path("", views.directory, name="directory"),
    path("setup/", views.setup, name="setup"),
    path("<slug:slug>/", views.detail, name="detail"),
    path("<slug:slug>/edit/", views.edit, name="edit"),
    path("<slug:slug>/submit-for-review/", views.submit_for_review, name="submit_for_review"),
]
