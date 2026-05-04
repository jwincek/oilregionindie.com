"""
RSS feeds for the Oil Region Creative Hub.
"""

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.utils import timezone

from apps.events.models import Event


class UpcomingEventsFeed(Feed):
    title = "Upcoming Events — Oil Region Creative Hub"
    description = "Concerts, art shows, maker markets, and more."
    link = "/events/"

    def __init__(self):
        super().__init__()
        site_name = getattr(settings, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub")
        self.title = f"Upcoming Events — {site_name}"

    def items(self):
        return Event.objects.filter(
            is_published=True,
            start_datetime__gte=timezone.now(),
        ).select_related("venue").order_by("start_datetime")[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        parts = [item.get_event_type_display()]
        if item.venue:
            parts.append(f"at {item.venue.name}, {item.venue.city}")
        parts.append(item.start_datetime.strftime("%A, %B %d at %I:%M %p"))
        if item.is_free:
            parts.append("Free")
        elif item.ticket_price_cents:
            parts.append(item.ticket_price_display)
        return " — ".join(parts)

    def item_link(self, item):
        return item.get_absolute_url()

    def item_pubdate(self, item):
        return item.created_at


class BlogFeed(Feed):
    title = "Blog — Oil Region Creative Hub"
    description = "News, creator spotlights, and updates."
    link = "/blog/"

    def __init__(self):
        super().__init__()
        site_name = getattr(settings, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub")
        self.title = f"Blog — {site_name}"

    def items(self):
        from apps.pages.models import BlogPost
        return BlogPost.objects.live().order_by("-first_published_at")[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.subtitle or item.search_description or ""

    def item_link(self, item):
        return item.url

    def item_pubdate(self, item):
        return item.first_published_at
