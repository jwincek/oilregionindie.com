from django.urls import path

from . import views

app_name = "venues"

urlpatterns = [
    path("", views.directory, name="directory"),
    path("setup/", views.setup, name="setup"),
    path("<slug:slug>/", views.detail, name="detail"),
    path("<slug:slug>/edit/", views.edit, name="edit"),
    path("<slug:slug>/submit-for-review/", views.submit_for_review, name="submit_for_review"),
    path("<slug:slug>/events/", views.profile_events, name="profile_events"),
    # Social links (HTMX)
    path("<slug:slug>/social-links/", views.social_links, name="social_links"),
    path("<slug:slug>/social-links/add/", views.add_social_link, name="add_social_link"),
    path("<slug:slug>/social-links/<int:pk>/edit/", views.edit_social_link, name="edit_social_link"),
    path("<slug:slug>/social-links/<int:pk>/delete/", views.delete_social_link, name="delete_social_link"),
    # Contacts (HTMX)
    path("<slug:slug>/contacts/", views.contacts, name="contacts"),
    path("<slug:slug>/contacts/add/", views.add_contact, name="add_contact"),
    path("<slug:slug>/contacts/<int:pk>/edit/", views.edit_contact, name="edit_contact"),
    path("<slug:slug>/contacts/<int:pk>/delete/", views.delete_contact, name="delete_contact"),
]
