"""
Tests for apps.core.digest — the weekly digest pipeline:

  compile_digest(user_profile, since)   gathers recent activity
  send_digest(user_profile, since)      compiles + renders + emails
  send_all_digests(since)                fans out to opted-in profiles

Test goals:
  - Verify the three None-returning short circuits in compile_digest
    (no follows; no activity in any of the three buckets).
  - Verify the queryset filters: new events come from followed venues
    OR feature followed creators; community posts come from followed
    creators' user accounts; upcoming-events bucket respects the
    14-day window.
  - Verify send_digest's defaulting (since=None → 7 days ago) and
    email assembly via mail.outbox.
  - Verify send_all_digests's email_digest opt-out and the
    sent/skipped count return shape.
"""

from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.community.models import CommunityPost
from apps.core.digest import compile_digest, send_all_digests, send_digest
from apps.core.models import UserProfile
from apps.creators.tests.helpers import make_creator, make_user
from apps.events.tests.helpers import make_event, make_event_slot
from apps.venues.tests.helpers import make_venue


# ---------------------------------------------------------------------------
# compile_digest
# ---------------------------------------------------------------------------


class CompileDigestTest(TestCase):
    def setUp(self):
        self.fan = make_user()
        self.fan_profile = self.fan.profile
        self.creator_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.venue = make_venue()
        self.since = timezone.now() - timedelta(days=7)

    # ---- None short-circuits ----

    def test_returns_none_when_user_follows_nothing(self):
        self.assertIsNone(compile_digest(self.fan_profile, self.since))

    def test_returns_none_when_followed_but_no_new_activity(self):
        """Followed someone, but nothing new in the window AND no
        upcoming events at followed venues → still nothing to send."""
        self.fan_profile.followed_creators.add(self.creator)
        self.fan_profile.followed_venues.add(self.venue)
        self.assertIsNone(compile_digest(self.fan_profile, self.since))

    # ---- new events from follows ----

    def test_includes_new_event_at_followed_venue(self):
        self.fan_profile.followed_venues.add(self.venue)
        event = make_event(
            title="Fresh Show", venue=self.venue,
            start_datetime=timezone.now() + timedelta(days=20),  # outside upcoming window
        )
        activity = compile_digest(self.fan_profile, self.since)
        self.assertIn(event, activity["new_events"])

    def test_includes_new_event_featuring_followed_creator(self):
        """An event the followed creator is on the lineup of counts as
        new activity, even if its venue isn't followed."""
        self.fan_profile.followed_creators.add(self.creator)
        event = make_event(
            title="Lineup Show",
            start_datetime=timezone.now() + timedelta(days=20),
        )
        make_event_slot(event, self.creator)
        activity = compile_digest(self.fan_profile, self.since)
        self.assertIn(event, activity["new_events"])

    def test_excludes_old_events_outside_since_window(self):
        self.fan_profile.followed_venues.add(self.venue)
        # Created 30 days ago — older than the 7-day since window.
        old_event = make_event(title="Old Event", venue=self.venue)
        from apps.events.models import Event
        Event.objects.filter(pk=old_event.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )
        # Also need at least one upcoming so we get a non-None result.
        upcoming = make_event(
            title="Upcoming", venue=self.venue,
            start_datetime=timezone.now() + timedelta(days=3),
        )
        activity = compile_digest(self.fan_profile, self.since)
        self.assertNotIn(old_event, activity["new_events"])
        # The upcoming event was also created recently → in new_events too.
        self.assertIn(upcoming, activity["new_events"])

    def test_excludes_unpublished_events(self):
        self.fan_profile.followed_venues.add(self.venue)
        draft = make_event(title="Draft", venue=self.venue, is_published=False,
                           start_datetime=timezone.now() + timedelta(days=3))
        published = make_event(title="Live", venue=self.venue,
                               start_datetime=timezone.now() + timedelta(days=3))
        activity = compile_digest(self.fan_profile, self.since)
        self.assertIn(published, activity["new_events"])
        self.assertNotIn(draft, activity["new_events"])

    # ---- community posts from follows ----

    def test_includes_community_post_from_followed_creator(self):
        self.fan_profile.followed_creators.add(self.creator)
        post = CommunityPost.objects.create(
            author=self.creator_user, title="Fresh Post", body="Body",
        )
        activity = compile_digest(self.fan_profile, self.since)
        self.assertIn(post, activity["new_posts"])

    def test_excludes_replies_from_new_posts_bucket(self):
        """Only top-level posts count — replies aren't standalone digest
        items."""
        self.fan_profile.followed_creators.add(self.creator)
        parent = CommunityPost.objects.create(
            author=self.creator_user, title="Parent", body="b",
        )
        reply = CommunityPost.objects.create(
            author=self.creator_user, body="reply", parent=parent,
        )
        activity = compile_digest(self.fan_profile, self.since)
        self.assertIn(parent, activity["new_posts"])
        self.assertNotIn(reply, activity["new_posts"])

    def test_excludes_old_posts(self):
        self.fan_profile.followed_creators.add(self.creator)
        new_post = CommunityPost.objects.create(
            author=self.creator_user, title="New", body="b",
        )
        old_post = CommunityPost.objects.create(
            author=self.creator_user, title="Old", body="b",
        )
        CommunityPost.objects.filter(pk=old_post.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )
        activity = compile_digest(self.fan_profile, self.since)
        self.assertIn(new_post, activity["new_posts"])
        self.assertNotIn(old_post, activity["new_posts"])

    def test_excludes_posts_from_unfollowed_authors(self):
        self.fan_profile.followed_creators.add(self.creator)
        # Post from someone else — not followed.
        other_user = make_user()
        make_creator(user=other_user)
        CommunityPost.objects.create(
            author=other_user, title="Stranger Post", body="b",
        )
        # And one from the followed creator to clear the None gate.
        own_post = CommunityPost.objects.create(
            author=self.creator_user, title="Own", body="b",
        )
        activity = compile_digest(self.fan_profile, self.since)
        post_titles = [p.title for p in activity["new_posts"]]
        self.assertIn("Own", post_titles)
        self.assertNotIn("Stranger Post", post_titles)

    # ---- upcoming events ----

    def test_upcoming_events_within_14_day_window(self):
        self.fan_profile.followed_venues.add(self.venue)
        soon = make_event(title="Soon", venue=self.venue,
                          start_datetime=timezone.now() + timedelta(days=5))
        too_far = make_event(title="Too Far", venue=self.venue,
                             start_datetime=timezone.now() + timedelta(days=30))
        activity = compile_digest(self.fan_profile, self.since)
        self.assertIn(soon, activity["upcoming_events"])
        self.assertNotIn(too_far, activity["upcoming_events"])

    def test_upcoming_excludes_past_events(self):
        self.fan_profile.followed_venues.add(self.venue)
        past = make_event(title="Past", venue=self.venue,
                          start_datetime=timezone.now() - timedelta(days=3))
        # Also need a real upcoming so compile_digest doesn't return None.
        future = make_event(title="Future", venue=self.venue,
                            start_datetime=timezone.now() + timedelta(days=3))
        activity = compile_digest(self.fan_profile, self.since)
        self.assertIn(future, activity["upcoming_events"])
        self.assertNotIn(past, activity["upcoming_events"])

    def test_activity_includes_followed_lists_for_template(self):
        """The dict surfaces the follow lists themselves so the template
        can render a 'Following N creators' line."""
        self.fan_profile.followed_creators.add(self.creator)
        CommunityPost.objects.create(
            author=self.creator_user, title="Post", body="b",
        )
        activity = compile_digest(self.fan_profile, self.since)
        self.assertIn(self.creator, list(activity["followed_creators"]))
        # Follow venue too and verify it appears in the dict.
        self.fan_profile.followed_venues.add(self.venue)
        activity = compile_digest(self.fan_profile, self.since)
        self.assertIn(self.venue, list(activity["followed_venues"]))


# ---------------------------------------------------------------------------
# send_digest
# ---------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SendDigestTest(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.fan = make_user(email="fan@example.com")
        self.creator_user = make_user()
        self.creator = make_creator(user=self.creator_user,
                                    display_name="Followed Creator")
        self.fan.profile.followed_creators.add(self.creator)

    def test_returns_false_when_no_activity(self):
        result = send_digest(self.fan.profile)
        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_sends_email_when_activity_exists(self):
        CommunityPost.objects.create(
            author=self.creator_user, title="Followed Author Post", body="b",
        )
        result = send_digest(self.fan.profile)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["fan@example.com"])
        self.assertIn("weekly digest", msg.subject.lower())
        # The author's post title should appear in the body.
        self.assertIn("Followed Author Post", msg.body)

    def test_uses_default_since_window_of_7_days_when_omitted(self):
        """An item created 6 days ago should be in the digest; one
        created 8 days ago should not."""
        recent = CommunityPost.objects.create(
            author=self.creator_user, title="Recent", body="b",
        )
        old = CommunityPost.objects.create(
            author=self.creator_user, title="Old", body="b",
        )
        CommunityPost.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=8),
        )
        # Don't pass `since` — exercises the default branch.
        result = send_digest(self.fan.profile)
        self.assertTrue(result)
        body = mail.outbox[0].body
        self.assertIn("Recent", body)
        self.assertNotIn("Old", body)

    @override_settings(WAGTAIL_SITE_NAME="Acme Creative Hub")
    def test_subject_uses_configured_site_name(self):
        CommunityPost.objects.create(
            author=self.creator_user, title="X", body="b",
        )
        send_digest(self.fan.profile)
        self.assertIn("[Acme Creative Hub]", mail.outbox[0].subject)


# ---------------------------------------------------------------------------
# send_all_digests
# ---------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SendAllDigestsTest(TestCase):
    def setUp(self):
        mail.outbox.clear()

    def test_returns_zero_zero_when_no_profiles_opted_in(self):
        # Default email_digest=True via the model default, but no follows
        # means everyone is skipped.
        for _ in range(3):
            make_user()
        sent, skipped = send_all_digests()
        self.assertEqual(sent, 0)
        # Three profiles with no follows → three "skipped" tallies.
        self.assertEqual(skipped, 3)

    def test_opted_out_profiles_are_excluded_entirely(self):
        """A user with email_digest=False isn't counted as sent OR
        skipped — they're filtered out before iteration."""
        opted_in = make_user()
        opted_out = make_user()
        UserProfile.objects.filter(user=opted_out).update(email_digest=False)
        sent, skipped = send_all_digests()
        self.assertEqual(sent, 0)
        # Only the opted-in user is in skipped count (no follows → no email).
        self.assertEqual(skipped, 1)

    def test_users_with_real_activity_are_in_sent_count(self):
        fan = make_user()
        creator_user = make_user()
        creator = make_creator(user=creator_user)
        fan.profile.followed_creators.add(creator)
        CommunityPost.objects.create(
            author=creator_user, title="Real activity", body="b",
        )
        # A separate user with no follows → goes in skipped.
        no_follow = make_user()
        sent, skipped = send_all_digests()
        self.assertEqual(sent, 1)
        # Two profiles end up in skipped: the creator (no follows of
        # their own) and the no_follow extra. The fan got their email.
        self.assertEqual(skipped, 2)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [fan.email])

    def test_explicit_since_param_passed_through(self):
        """Tighter window → fewer items qualify; wide window → all do."""
        fan = make_user()
        creator_user = make_user()
        creator = make_creator(user=creator_user)
        fan.profile.followed_creators.add(creator)
        # Post created 10 days ago — outside default 7d but inside 30d.
        old_post = CommunityPost.objects.create(
            author=creator_user, title="10 days old", body="b",
        )
        CommunityPost.objects.filter(pk=old_post.pk).update(
            created_at=timezone.now() - timedelta(days=10),
        )
        # Default 7d → no activity → nothing sent.
        sent, _ = send_all_digests()
        self.assertEqual(sent, 0)
        # Wider 30d window → activity is in range → digest goes out.
        sent, _ = send_all_digests(
            since=timezone.now() - timedelta(days=30),
        )
        self.assertEqual(sent, 1)
