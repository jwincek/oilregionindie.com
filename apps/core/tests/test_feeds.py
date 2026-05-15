"""
Tests for apps.core.feeds — RSS feeds at /feeds/events/ and /feeds/blog/.

Two layers:
  - Unit: instantiate the Feed class and call items()/item_*() methods
    directly. This is what catches a regression in the description
    assembly or pubdate field choice.
  - Integration: GET the feed URL and assert on the rendered XML
    (Django's syndication framework does the actual rendering).
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.feeds import BlogFeed, UpcomingEventsFeed
from apps.events.models import Event
from apps.events.tests.helpers import make_event
from apps.venues.tests.helpers import make_venue


# ---------------------------------------------------------------------------
# UpcomingEventsFeed — unit
# ---------------------------------------------------------------------------


class UpcomingEventsFeedUnitTest(TestCase):
    def test_items_returns_published_upcoming_in_chronological_order(self):
        venue = make_venue()
        far = make_event(title="Far", venue=venue,
                         start_datetime=timezone.now() + timedelta(days=30))
        near = make_event(title="Near", venue=venue,
                          start_datetime=timezone.now() + timedelta(days=3))
        items = list(UpcomingEventsFeed().items())
        self.assertEqual(items, [near, far])

    def test_items_excludes_past_events(self):
        venue = make_venue()
        past = make_event(title="Past", venue=venue,
                          start_datetime=timezone.now() - timedelta(days=3))
        future = make_event(title="Future", venue=venue,
                            start_datetime=timezone.now() + timedelta(days=3))
        items = list(UpcomingEventsFeed().items())
        self.assertNotIn(past, items)
        self.assertIn(future, items)

    def test_items_excludes_unpublished(self):
        venue = make_venue()
        draft = make_event(title="Draft", venue=venue, is_published=False,
                           start_datetime=timezone.now() + timedelta(days=3))
        live = make_event(title="Live", venue=venue,
                          start_datetime=timezone.now() + timedelta(days=3))
        items = list(UpcomingEventsFeed().items())
        self.assertIn(live, items)
        self.assertNotIn(draft, items)

    def test_items_caps_at_20(self):
        venue = make_venue()
        for i in range(25):
            make_event(title=f"E{i}", venue=venue,
                       start_datetime=timezone.now() + timedelta(days=i + 1))
        items = list(UpcomingEventsFeed().items())
        self.assertEqual(len(items), 20)

    def test_item_title_returns_event_title(self):
        e = make_event(title="My Show", venue=make_venue())
        self.assertEqual(UpcomingEventsFeed().item_title(e), "My Show")

    def test_item_link_returns_absolute_url(self):
        e = make_event(title="X", venue=make_venue())
        self.assertEqual(UpcomingEventsFeed().item_link(e), e.get_absolute_url())

    def test_item_pubdate_returns_created_at(self):
        e = make_event(title="X", venue=make_venue())
        self.assertEqual(UpcomingEventsFeed().item_pubdate(e), e.created_at)

    def test_item_description_for_free_event_with_venue(self):
        venue = make_venue(name="The Spot", city="Oil City")
        e = make_event(
            title="Free Show", venue=venue, is_free=True,
            event_type=Event.EventType.CONCERT,
            start_datetime=datetime(2026, 7, 4, 19, 0, tzinfo=dt_timezone.utc),
        )
        desc = UpcomingEventsFeed().item_description(e)
        self.assertIn("Concert", desc)
        self.assertIn("at The Spot, Oil City", desc)
        self.assertIn("Free", desc)
        # The datetime is formatted humanly.
        self.assertRegex(desc, r"[A-Z][a-z]+day,\s+[A-Z][a-z]+ \d+ at \d+:\d+ [AP]M")

    def test_item_description_for_paid_event_includes_price(self):
        venue = make_venue()
        e = make_event(
            title="Paid Show", venue=venue, is_free=False,
            ticket_price_cents=2500,
            start_datetime=timezone.now() + timedelta(days=1),
        )
        desc = UpcomingEventsFeed().item_description(e)
        self.assertIn("$25.00", desc)
        self.assertNotIn("Free", desc)

    def test_item_description_handles_event_without_venue(self):
        """Online-only or yet-to-be-booked events have venue=None;
        description should skip the 'at <venue>' clause without crashing.
        (The datetime format itself includes the word 'at', so we check
        for the specific venue-name pattern instead.)"""
        e = make_event(title="Virtual", venue=None,
                       start_datetime=timezone.now() + timedelta(days=1))
        desc = UpcomingEventsFeed().item_description(e)
        # The "at <venue name>, <city>" clause is missing — no comma
        # appears in the (non-existent) venue clause.
        self.assertNotIn("at The Spot", desc)
        self.assertIn("Concert", desc)
        # Datetime is still present.
        self.assertRegex(desc, r"\d+:\d+ [AP]M")

    @override_settings(WAGTAIL_SITE_NAME="Acme Hub")
    def test_feed_title_uses_configured_site_name(self):
        self.assertIn("Acme Hub", UpcomingEventsFeed().title)


# ---------------------------------------------------------------------------
# UpcomingEventsFeed — integration via the URL
# ---------------------------------------------------------------------------


class UpcomingEventsFeedIntegrationTest(TestCase):
    def test_feed_url_returns_200_with_xml_content_type(self):
        make_event(title="Some Show",
                   start_datetime=timezone.now() + timedelta(days=5),
                   venue=make_venue())
        r = self.client.get(reverse("events_feed"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("xml", r["Content-Type"])
        # The event title appears in the rendered XML.
        self.assertIn(b"Some Show", r.content)

    def test_empty_feed_still_returns_200(self):
        r = self.client.get(reverse("events_feed"))
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# BlogFeed — unit (mocked BlogPost queryset)
# ---------------------------------------------------------------------------


class BlogFeedUnitTest(TestCase):
    def _fake_post(self, **kwargs):
        defaults = {
            "title": "Post Title",
            "subtitle": "Post Subtitle",
            "search_description": "",
            "url": "/blog/some-post/",
            "first_published_at": timezone.now(),
        }
        defaults.update(kwargs)
        return mock.Mock(**defaults)

    def test_items_returns_live_blogpost_query(self):
        """BlogFeed.items() pulls BlogPost.objects.live() — patch the
        manager so we don't need to create a full Wagtail page tree
        for this unit test."""
        from apps.pages.models import BlogPost
        fake_posts = [self._fake_post(title="P1"), self._fake_post(title="P2")]

        # Patch BlogPost.objects.live() to return our fakes via a chain
        # that mimics live().order_by()[...].
        ordered = mock.MagicMock()
        ordered.__getitem__ = lambda self, key: fake_posts
        live_qs = mock.MagicMock()
        live_qs.order_by.return_value = ordered
        with mock.patch.object(BlogPost.objects, "live", return_value=live_qs):
            items = BlogFeed().items()
        self.assertEqual(items, fake_posts)

    def test_item_title(self):
        post = self._fake_post(title="Headline")
        self.assertEqual(BlogFeed().item_title(post), "Headline")

    def test_item_description_prefers_subtitle(self):
        post = self._fake_post(subtitle="Subtitle wins",
                               search_description="not this")
        self.assertEqual(BlogFeed().item_description(post), "Subtitle wins")

    def test_item_description_falls_back_to_search_description(self):
        post = self._fake_post(subtitle="",
                               search_description="SEO summary")
        self.assertEqual(BlogFeed().item_description(post), "SEO summary")

    def test_item_description_falls_back_to_empty_string(self):
        post = self._fake_post(subtitle="", search_description="")
        self.assertEqual(BlogFeed().item_description(post), "")

    def test_item_link_returns_post_url(self):
        post = self._fake_post(url="/blog/announcement/")
        self.assertEqual(BlogFeed().item_link(post), "/blog/announcement/")

    def test_item_pubdate_returns_first_published_at(self):
        when = timezone.now()
        post = self._fake_post(first_published_at=when)
        self.assertEqual(BlogFeed().item_pubdate(post), when)

    @override_settings(WAGTAIL_SITE_NAME="Acme Hub")
    def test_feed_title_uses_configured_site_name(self):
        self.assertIn("Acme Hub", BlogFeed().title)


# ---------------------------------------------------------------------------
# BlogFeed — integration via the URL (empty result is fine)
# ---------------------------------------------------------------------------


class BlogFeedIntegrationTest(TestCase):
    def test_feed_url_returns_200_with_xml_content_type(self):
        """No published posts in the test DB → empty feed still serves
        successfully with the right content type."""
        r = self.client.get(reverse("blog_feed"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("xml", r["Content-Type"])
