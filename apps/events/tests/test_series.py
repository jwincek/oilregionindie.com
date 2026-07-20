"""
EventSeries (issue #45): festivals and pop-up crawls as groupings of
events. Member events keep their own venue/location/lineup/times, and
overlapping times are deliberately allowed — simultaneous sidewalk sets
across a neighborhood are the point, not a conflict.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.events.models import EventSeries

from .helpers import make_event, make_user


def make_series(title="Oil Region Indie Music Festival", **kwargs):
    return EventSeries.objects.create(
        title=title, created_by=kwargs.pop("created_by", make_user()), **kwargs,
    )


class EventSeriesModelTest(TestCase):
    def test_slug_autogenerates_and_deduplicates(self):
        a = make_series()
        b = make_series()
        self.assertEqual(a.slug, "oil-region-indie-music-festival")
        self.assertEqual(b.slug, "oil-region-indie-music-festival-1")

    def test_overlapping_member_events_are_allowed(self):
        series = make_series(title="Porchfest")
        start = timezone.now() + timedelta(days=7)
        make_event(title="Porch A", series=series, start_datetime=start,
                   location_name="Seneca & Center St")
        make_event(title="Porch B", series=series, start_datetime=start,
                   location_name="Two Corners Down")
        self.assertEqual(series.events.count(), 2)


class SeriesPageTest(TestCase):
    def setUp(self):
        self.series = make_series(title="Pop-Up Crawl")
        self.member = make_event(
            title="Dawn Sidewalk Set", series=self.series,
            location_name="Elm St Sidewalk",
        )

    def test_series_page_lists_published_member_events(self):
        r = self.client.get(self.series.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Pop-Up Crawl")
        self.assertContains(r, "Dawn Sidewalk Set")
        self.assertContains(r, "Elm St Sidewalk")

    def test_unpublished_members_are_hidden(self):
        make_event(title="Secret Draft Set", series=self.series, is_published=False)
        r = self.client.get(self.series.get_absolute_url())
        self.assertNotContains(r, "Secret Draft Set")

    def test_event_detail_links_to_series(self):
        r = self.client.get(self.member.get_absolute_url())
        self.assertContains(r, "Part of Pop-Up Crawl")
        self.assertContains(r, self.series.get_absolute_url())
