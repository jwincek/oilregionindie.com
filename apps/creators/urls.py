from django.urls import path

from . import views

app_name = "creators"

urlpatterns = [
    path("", views.directory, name="directory"),
    path("setup/", views.setup, name="setup"),
    path("edit/", views.edit, name="edit"),
    # Media (HTMX)
    path("media/", views.media_items, name="media_items"),
    path("media/add/", views.add_media, name="add_media"),
    path("media/<uuid:pk>/edit/", views.edit_media, name="edit_media"),
    path("media/<uuid:pk>/delete/", views.delete_media, name="delete_media"),
    # Social links (HTMX)
    path("social-links/", views.social_links, name="social_links"),
    path("social-links/add/", views.add_social_link, name="add_social_link"),
    path("social-links/<int:pk>/edit/", views.edit_social_link, name="edit_social_link"),
    path("social-links/<int:pk>/delete/", views.delete_social_link, name="delete_social_link"),
    # Detail (must be last — catches slugs)
    path("<slug:slug>/", views.detail, name="detail"),
]
