"""
User-to-user blocking (issue #89): the helper, the toggle views, and
enforcement at the follow / booking / notification boundaries.
"""
from django.test import TestCase
from django.urls import reverse

from apps.community.models import CommunityPost
from apps.core.blocks import is_blocked_between
from apps.core.models import Notification
from apps.creators.tests.helpers import make_creator, make_user
from apps.events.models import BookingRequest
from apps.venues.tests.helpers import make_venue


class IsBlockedBetweenTest(TestCase):
    def test_block_is_bidirectional_in_effect(self):
        a, b = make_user(), make_user()
        a.profile.blocked_users.add(b)
        self.assertTrue(is_blocked_between(a, b))
        self.assertTrue(is_blocked_between(b, a))  # one-sided intent, two-sided effect

    def test_no_block_is_false(self):
        self.assertFalse(is_blocked_between(make_user(), make_user()))

    def test_same_user_is_false(self):
        u = make_user()
        u.profile.blocked_users.add(u)  # nonsensical but must not report a self-block
        self.assertFalse(is_blocked_between(u, u))


class BlockToggleViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.creator = make_creator(user=self.owner)
        self.blocker = make_user()
        self.client.force_login(self.blocker)
        self.url = reverse("block_creator", kwargs={"slug": self.creator.slug})

    def test_block_then_unblock(self):
        self.client.post(self.url)
        self.assertTrue(self.blocker.profile.blocked_users.filter(pk=self.owner.pk).exists())
        self.client.post(self.url)
        self.assertFalse(self.blocker.profile.blocked_users.filter(pk=self.owner.pk).exists())

    def test_cannot_block_yourself(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url)
        self.assertEqual(r.status_code, 404)

    def test_htmx_returns_partial(self):
        r = self.client.post(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "unblock")

    def test_blocking_severs_existing_follow(self):
        self.blocker.profile.followed_creators.add(self.creator)
        self.client.post(self.url)
        self.assertFalse(
            self.blocker.profile.followed_creators.filter(pk=self.creator.pk).exists()
        )


class FollowBlockedTest(TestCase):
    def test_cannot_follow_across_a_block(self):
        owner = make_user()
        creator = make_creator(user=owner)
        fan = make_user()
        owner.profile.blocked_users.add(fan)
        self.client.force_login(fan)
        self.client.post(reverse("follow_creator", kwargs={"slug": creator.slug}))
        self.assertFalse(fan.profile.followed_creators.filter(pk=creator.pk).exists())


class BookingBlockedTest(TestCase):
    def test_blocked_sender_cannot_book(self):
        owner = make_user()
        venue = make_venue(user=owner)
        sender = make_user()
        make_creator(user=sender)  # sender needs a creator profile to book a venue
        owner.profile.blocked_users.add(sender)
        self.client.force_login(sender)
        r = self.client.post(
            reverse("events:booking_create",
                    kwargs={"direction": "to-venue", "profile_slug": venue.slug}),
            {"event_type": "concert", "preferred_dates": "August", "message": "hi"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertFalse(
            BookingRequest.objects.filter(initiated_by=sender).exists()
        )


class ReplyNotificationBlockedTest(TestCase):
    def test_blocked_reply_creates_no_notification(self):
        author = make_user()
        post = CommunityPost.objects.create(author=author, body="original")
        replier = make_user()
        author.profile.blocked_users.add(replier)
        self.client.force_login(replier)
        self.client.post(
            reverse("community:reply", kwargs={"pk": post.pk}),
            {"body": "a reply"},
        )
        # The reply itself is allowed (public content); the notification is not.
        self.assertTrue(CommunityPost.objects.filter(parent=post, author=replier).exists())
        self.assertFalse(
            Notification.objects.filter(
                recipient=author, notification_type=Notification.NotificationType.REPLY
            ).exists()
        )
