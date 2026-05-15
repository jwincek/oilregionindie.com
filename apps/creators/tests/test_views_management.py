"""
Tests for creator-management views beyond directory/detail/setup/edit:

  profile_events       — HTMX partial showing upcoming/past events
                         a creator is on the lineup for.
  stats                — creator analytics dashboard (daily views,
                         30-day totals, follower count).
  submit_for_review    — state transition with admin notification.
  bulk_upload_media    — multi-file POST that creates MediaItem rows.
"""

import io
from datetime import date, timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ProfileView
from apps.creators.models import CreatorProfile, MediaItem
from apps.events.tests.helpers import make_event, make_event_slot
from apps.venues.tests.helpers import make_venue

from .helpers import make_creator, make_user


def _tiny_image(name="pic.png"):
    """Real PNG from Pillow — ImageField uses Pillow to validate uploads."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


# ---------------------------------------------------------------------------
# profile_events
# ---------------------------------------------------------------------------


class CreatorProfileEventsViewTest(TestCase):
    def setUp(self):
        self.creator = make_creator(user=make_user(),
                                    display_name="Spotlight Creator")
        self.venue = make_venue()

    def url(self, slug=None):
        return reverse("creators:profile_events",
                       kwargs={"slug": slug or self.creator.slug})

    def test_404_for_unpublished_creator(self):
        draft = make_creator(user=make_user(), publish_status="draft")
        r = self.client.get(self.url(draft.slug))
        self.assertEqual(r.status_code, 404)

    def test_upcoming_events_default(self):
        upcoming = make_event(
            title="Future Show", venue=self.venue,
            start_datetime=timezone.now() + timedelta(days=7),
        )
        past = make_event(
            title="Past Show", venue=self.venue,
            start_datetime=timezone.now() - timedelta(days=7),
        )
        # Lineup creator on both events.
        make_event_slot(upcoming, self.creator)
        make_event_slot(past, self.creator)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        events = list(r.context["events"])
        self.assertIn(upcoming, events)
        self.assertNotIn(past, events)
        self.assertEqual(r.context["show"], "upcoming")

    def test_past_events_when_show_past(self):
        upcoming = make_event(
            title="Future Show", venue=self.venue,
            start_datetime=timezone.now() + timedelta(days=7),
        )
        past = make_event(
            title="Past Show", venue=self.venue,
            start_datetime=timezone.now() - timedelta(days=7),
        )
        make_event_slot(upcoming, self.creator)
        make_event_slot(past, self.creator)
        r = self.client.get(self.url(), {"show": "past"})
        events = list(r.context["events"])
        self.assertIn(past, events)
        self.assertNotIn(upcoming, events)

    def test_events_from_other_creators_excluded(self):
        """Lineup scoping — only events featuring THIS creator appear."""
        other_creator = make_creator(user=make_user(),
                                     display_name="Someone Else")
        other_event = make_event(venue=self.venue,
                                 start_datetime=timezone.now() + timedelta(days=3))
        make_event_slot(other_event, other_creator)
        r = self.client.get(self.url())
        self.assertNotIn(other_event, list(r.context["events"]))


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


class CreatorStatsViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_creator(user=self.owner)

    def url(self):
        return reverse("creators:stats")

    def test_login_required(self):
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 302)

    def test_user_without_creator_profile_404s(self):
        self.client.force_login(make_user())
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 404)

    def test_empty_state_renders_zero_metrics(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["daily_views"], [])
        self.assertEqual(r.context["total_views_30d"], 0)
        self.assertEqual(r.context["total_views_all"], 0)
        self.assertEqual(r.context["follower_count"], 0)

    def test_aggregates_recent_and_lifetime_view_counts(self):
        today = date.today()
        # Three days within the 30-day window.
        ProfileView.objects.create(creator=self.creator,
                                   date=today, count=5)
        ProfileView.objects.create(creator=self.creator,
                                   date=today - timedelta(days=10), count=3)
        ProfileView.objects.create(creator=self.creator,
                                   date=today - timedelta(days=20), count=2)
        # One outside the 30-day window — counts toward lifetime, not 30d.
        ProfileView.objects.create(creator=self.creator,
                                   date=today - timedelta(days=60), count=100)
        self.client.force_login(self.owner)
        r = self.client.get(self.url())
        self.assertEqual(r.context["total_views_30d"], 10)
        self.assertEqual(r.context["total_views_all"], 110)
        # daily_views is ordered by date ascending.
        dates = [row[0] for row in r.context["daily_views"]]
        self.assertEqual(dates, sorted(dates))

    def test_follower_count_reflects_followers(self):
        from apps.core.models import UserProfile
        for _ in range(3):
            fan = make_user()
            fan.profile.followed_creators.add(self.creator)
        self.client.force_login(self.owner)
        r = self.client.get(self.url())
        self.assertEqual(r.context["follower_count"], 3)


# ---------------------------------------------------------------------------
# submit_for_review
# ---------------------------------------------------------------------------


class CreatorSubmitForReviewViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_creator(user=self.owner, publish_status="draft")

    def url(self):
        return reverse("creators:submit_for_review")

    def test_get_not_allowed(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 405)

    def test_user_without_creator_profile_404s(self):
        self.client.force_login(make_user())
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 404)

    @mock.patch("apps.creators.views.notify_admin_profile_submitted")
    def test_draft_transitions_to_pending_and_notifies_admin(self, mock_notify):
        self.client.force_login(self.owner)
        r = self.client.post(self.url())
        self.assertRedirects(r, reverse("creators:edit"))
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.publish_status, "pending")
        self.assertIsNotNone(self.creator.submitted_at)
        mock_notify.assert_called_once_with(self.creator)

    @mock.patch("apps.creators.views.notify_admin_profile_submitted")
    def test_already_published_no_state_change_no_notify(self, mock_notify):
        self.creator.publish_status = "published"
        self.creator.save()
        self.client.force_login(self.owner)
        self.client.post(self.url())
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.publish_status, "published")
        mock_notify.assert_not_called()

    @mock.patch("apps.creators.views.notify_admin_profile_submitted")
    def test_already_pending_no_state_change_no_notify(self, mock_notify):
        self.creator.publish_status = "pending"
        self.creator.save()
        self.client.force_login(self.owner)
        self.client.post(self.url())
        mock_notify.assert_not_called()


# ---------------------------------------------------------------------------
# bulk_upload_media
# ---------------------------------------------------------------------------


class CreatorBulkUploadMediaViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_creator(user=self.owner)

    def url(self):
        return reverse("creators:bulk_upload_media")

    def test_get_not_allowed(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 405)

    def test_user_without_creator_profile_404s(self):
        self.client.force_login(make_user())
        r = self.client.post(self.url(), {"files": [_tiny_image()]})
        self.assertEqual(r.status_code, 404)

    def test_empty_upload_renders_list_with_error_message(self):
        """No files submitted → render the partial with an error
        message but no rows created (no 500)."""
        self.client.force_login(self.owner)
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "creators/_media_items.html")
        self.assertFalse(MediaItem.objects.filter(creator=self.creator).exists())

    def test_uploads_multiple_files_with_typed_titles(self):
        """Filenames like 'foo_bar-baz.png' become 'Foo Bar Baz' titles.
        Content-type starts-with checks set the media_type."""
        self.client.force_login(self.owner)
        r = self.client.post(self.url(), {
            "files": [
                _tiny_image("first-image.png"),
                _tiny_image("second_image.png"),
            ],
        })
        self.assertEqual(r.status_code, 302)  # non-HTMX: redirect to edit
        items = list(MediaItem.objects.filter(creator=self.creator)
                     .order_by("sort_order"))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "First Image")
        self.assertEqual(items[1].title, "Second Image")
        # sort_order is appended at end (0 and 1 since the creator
        # had no prior items).
        self.assertEqual([i.sort_order for i in items], [0, 1])
        for item in items:
            self.assertEqual(item.media_type, "image")

    def test_htmx_request_returns_partial_not_redirect(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url(), {
            "files": [_tiny_image()],
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "creators/_media_items.html")

    def test_video_content_type_sets_video_media_type(self):
        self.client.force_login(self.owner)
        # SimpleUploadedFile lets us set content_type to anything.
        fake_video = SimpleUploadedFile(
            "clip.mp4", b"\x00\x00\x00 ftypmp42",
            content_type="video/mp4",
        )
        self.client.post(self.url(), {"files": [fake_video]})
        item = MediaItem.objects.get(creator=self.creator)
        self.assertEqual(item.media_type, "video")

    def test_audio_content_type_sets_audio_media_type(self):
        self.client.force_login(self.owner)
        fake_audio = SimpleUploadedFile(
            "song.mp3", b"\xff\xfb\x90\x00",
            content_type="audio/mpeg",
        )
        self.client.post(self.url(), {"files": [fake_audio]})
        item = MediaItem.objects.get(creator=self.creator)
        self.assertEqual(item.media_type, "audio")

    def test_unknown_content_type_defaults_to_image(self):
        """Defensive: an empty/unknown Content-Type header lands in the
        image bucket rather than crashing."""
        self.client.force_login(self.owner)
        odd = SimpleUploadedFile("x", b"\x00\x00",
                                 content_type="application/octet-stream")
        self.client.post(self.url(), {"files": [odd]})
        item = MediaItem.objects.get(creator=self.creator)
        self.assertEqual(item.media_type, "image")

    def test_existing_media_offsets_new_sort_order(self):
        """If the creator already has 3 items, the new uploads start at
        sort_order=3, 4, 5…"""
        from apps.creators.models import MediaItem as M
        for i in range(3):
            M.objects.create(creator=self.creator,
                             title=f"Existing {i}", sort_order=i)
        self.client.force_login(self.owner)
        self.client.post(self.url(), {
            "files": [_tiny_image("a.png"), _tiny_image("b.png")],
        })
        new = list(MediaItem.objects.filter(creator=self.creator,
                                            title__in=["A", "B"])
                   .order_by("sort_order"))
        self.assertEqual([i.sort_order for i in new], [3, 4])
