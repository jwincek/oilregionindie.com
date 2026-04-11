from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

urlpatterns = [
    # Django admin (keep but rarely used; Wagtail admin is primary)
    path("django-admin/", admin.site.urls),
    # Wagtail admin
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    # Authentication
    path("accounts/", include("allauth.urls")),
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
