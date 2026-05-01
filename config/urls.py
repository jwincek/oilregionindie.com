from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import include, path

from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from apps.core.sitemaps import sitemaps

from apps.core.views import (
    add_availability, availability_list, delete_account, delete_availability,
    edit_availability, follow_creator, follow_venue, mark_all_read,
    notification_inbox, preferences, report_content, search,
    submit_feedback, suspended, toggle_like, welcome,
)

urlpatterns = [
    # SEO
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"),
    path("robots.txt", lambda r: HttpResponse(
        "User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n",
        content_type="text/plain",
    )),
    # Django admin (keep but rarely used; Wagtail admin is primary)
    path("django-admin/", admin.site.urls),
    # Wagtail admin
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    # Authentication
    path("accounts/", include("allauth.urls")),
    # Post-signup welcome
    path("welcome/", welcome, name="welcome"),
    # Availability management (HTMX)
    path("availability/<str:profile_type>/<slug:slug>/", availability_list, name="availability_list"),
    path("availability/<str:profile_type>/<slug:slug>/add/", add_availability, name="add_availability"),
    path("availability/<str:profile_type>/<slug:slug>/<uuid:pk>/edit/", edit_availability, name="edit_availability"),
    path("availability/<str:profile_type>/<slug:slug>/<uuid:pk>/delete/", delete_availability, name="delete_availability"),
    # Follow / Like / Notifications
    path("follow/creator/<slug:slug>/", follow_creator, name="follow_creator"),
    path("follow/venue/<slug:slug>/", follow_venue, name="follow_venue"),
    path("like/<uuid:pk>/", toggle_like, name="toggle_like"),
    path("notifications/", notification_inbox, name="notifications"),
    path("notifications/mark-all-read/", mark_all_read, name="mark_all_read"),
    path("preferences/", preferences, name="preferences"),
    path("delete-account/", delete_account, name="delete_account"),
    path("search/", search, name="search"),
    path("report/", report_content, name="report_content"),
    path("submit-feedback/", submit_feedback, name="submit_feedback"),
    path("suspended/", suspended, name="suspended"),
    # Project apps
    path("creators/", include("apps.creators.urls", namespace="creators")),
    path("venues/", include("apps.venues.urls", namespace="venues")),
    path("events/", include("apps.events.urls", namespace="events")),
    path("shop/", include("apps.commerce.urls", namespace="commerce")),
    path("community/", include("apps.community.urls", namespace="community")),
    # Wagtail catch-all (must be last)
    path("", include(wagtail_urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns
