from django.contrib.sitemaps import Sitemap
from django.utils import timezone

from apps.creators.models import CreatorProfile
from apps.venues.models import VenueProfile
from apps.events.models import Event


class CreatorSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return CreatorProfile.objects.filter(publish_status="published")

    def lastmod(self, obj):
        return obj.updated_at


class VenueSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return VenueProfile.objects.filter(publish_status="published")

    def lastmod(self, obj):
        return obj.updated_at


class EventSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return Event.objects.filter(
            is_published=True,
            start_datetime__gte=timezone.now(),
        )

    def lastmod(self, obj):
        return obj.updated_at


sitemaps = {
    "creators": CreatorSitemap,
    "venues": VenueSitemap,
    "events": EventSitemap,
}
