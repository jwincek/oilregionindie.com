"""
Moderation audit log (issue #93): the durable, append-only record of
safety actions that lets routine change-history be pruned safely.
"""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import ModerationEvent
from apps.creators.tests.helpers import make_creator, make_user


class ModerationLogHelperTest(TestCase):
    def test_log_records_event(self):
        user = make_user()
        e = ModerationEvent.log(
            ModerationEvent.EventType.REPORT_FILED, actor=user, target="profile:x"
        )
        self.assertEqual(e.event_type, "report_filed")
        self.assertEqual(e.actor, user)

    def test_anonymous_actor_stored_as_null(self):
        from django.contrib.auth.models import AnonymousUser
        e = ModerationEvent.log(
            ModerationEvent.EventType.REMOVAL_REQUESTED, actor=AnonymousUser(), target="v:x"
        )
        self.assertIsNone(e.actor)

    def test_log_survives_actor_deletion(self):
        """The record must outlive the account so a bad actor can't erase it."""
        user = make_user()
        e = ModerationEvent.log(
            ModerationEvent.EventType.USER_BLOCKED, actor=user, target="someone"
        )
        user.delete()
        e.refresh_from_db()
        self.assertIsNone(e.actor)          # SET_NULL, not cascade
        self.assertEqual(e.target, "someone")  # free-text target survives


class ModerationLogWiringTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_report_is_logged(self):
        self.client.force_login(make_user())
        self.client.post(reverse("report_content"), {
            "content_type": "profile", "content_id": "abc",
            "content_url": "/", "reason": "spam",
        })
        self.assertTrue(
            ModerationEvent.objects.filter(event_type="report_filed").exists()
        )

    def test_removal_request_is_logged_anonymously(self):
        creator = make_creator()
        self.client.post(
            reverse("request_removal", kwargs={"profile_type": "creator", "slug": creator.slug}),
            {"reason": "this is me and I never agreed"},
        )
        e = ModerationEvent.objects.get(event_type="removal_requested")
        self.assertIsNone(e.actor)
        self.assertEqual(e.target, f"creator:{creator.slug}")

    def test_block_and_unblock_are_logged(self):
        owner = make_user()
        creator = make_creator(user=owner)
        blocker = make_user()
        self.client.force_login(blocker)
        url = reverse("block_creator", kwargs={"slug": creator.slug})
        self.client.post(url)
        self.client.post(url)  # unblock
        types = set(ModerationEvent.objects.values_list("event_type", flat=True))
        self.assertIn("user_blocked", types)
        self.assertIn("user_unblocked", types)
