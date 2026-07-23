"""
Posting-hygiene throttles + dedup (issue #86): the DB-query helpers and
their enforcement on the content-creation views.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.community.models import CommunityPost
from apps.core.models import Report
from apps.core.throttle import (
    effective_limit, is_duplicate, is_new_account, too_many_recent,
)
from apps.creators.tests.helpers import make_user


def _age(user, **delta):
    user.date_joined = timezone.now() - timedelta(**delta)
    user.save(update_fields=["date_joined"])
    return user


class ThrottleHelperTest(TestCase):
    def test_is_new_account(self):
        self.assertTrue(is_new_account(make_user()))
        self.assertFalse(is_new_account(_age(make_user(), days=3)))

    def test_effective_limit_switches_on_account_age(self):
        self.assertEqual(effective_limit(make_user(), 5, 2), 2)
        self.assertEqual(effective_limit(_age(make_user(), days=3), 5, 2), 5)

    def test_too_many_recent_counts_within_window(self):
        u = make_user()
        for i in range(3):
            CommunityPost.objects.create(author=u, body=f"b{i}")
        self.assertTrue(too_many_recent(CommunityPost, timedelta(minutes=5), 3, author=u))
        self.assertFalse(too_many_recent(CommunityPost, timedelta(minutes=5), 4, author=u))

    def test_too_many_recent_ignores_rows_outside_window(self):
        u = make_user()
        p = CommunityPost.objects.create(author=u, body="old")
        CommunityPost.objects.filter(pk=p.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        self.assertFalse(too_many_recent(CommunityPost, timedelta(minutes=5), 1, author=u))

    def test_is_duplicate_matches_same_fields_only(self):
        u = make_user()
        CommunityPost.objects.create(author=u, body="hello world")
        self.assertTrue(
            is_duplicate(CommunityPost, timedelta(minutes=30), author=u, body="hello world")
        )
        self.assertFalse(
            is_duplicate(CommunityPost, timedelta(minutes=30), author=u, body="different")
        )


class CommunityCreateThrottleTest(TestCase):
    def setUp(self):
        self.user = make_user()  # brand-new account -> strict cap (2)
        self.client.force_login(self.user)
        self.url = reverse("community:create")

    def _post(self, body):
        return self.client.post(
            self.url, {"body": body, "post_type": "discussion", "title": ""}
        )

    def test_new_account_capped_at_strict_limit(self):
        self._post("first post")
        self._post("second post")
        self._post("third post")  # blocked: count 2 >= new-account limit 2
        self.assertEqual(CommunityPost.objects.filter(author=self.user).count(), 2)

    def test_duplicate_body_blocked(self):
        self._post("same exact body")
        self._post("same exact body")
        self.assertEqual(
            CommunityPost.objects.filter(author=self.user, body="same exact body").count(), 1
        )

    def test_aged_account_gets_higher_limit(self):
        _age(self.user, days=3)
        for i in range(3):  # more than the new-account cap of 2
            self._post(f"aged post {i}")
        self.assertEqual(CommunityPost.objects.filter(author=self.user).count(), 3)


class ReportThrottleTest(TestCase):
    def setUp(self):
        self.user = make_user()  # new account -> report cap 5/hr
        self.client.force_login(self.user)
        self.url = reverse("report_content")

    def _report(self, i):
        return self.client.post(self.url, {
            "content_type": "profile", "content_id": f"x{i}",
            "content_url": "/", "reason": "spam",
        })

    def test_reports_throttled_after_limit(self):
        for i in range(5):
            self._report(i)
        self._report(6)  # blocked
        self.assertEqual(Report.objects.filter(reporter=self.user).count(), 5)
