"""
Tests for apps.core.views — the cross-app surfaces (follow, like,
notifications, search, preferences, reports, feedback, dashboard) plus
the availability-management HTMX endpoints and the post-signup welcome
interstitial.
"""

import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.community.models import CommunityPost
from apps.core.models import (
    AvailabilityType, Notification, ProfileAvailability, Report, UserProfile,
)
from apps.creators.tests.helpers import make_creator, make_user
from apps.events.tests.helpers import make_event
from apps.venues.tests.helpers import make_venue

User = get_user_model()


# ---------------------------------------------------------------------------
# suspended + welcome (smallest surfaces)
# ---------------------------------------------------------------------------


class SuspendedViewTest(TestCase):
    def test_renders_for_anyone(self):
        r = self.client.get(reverse("suspended"))
        self.assertEqual(r.status_code, 200)


class WelcomeViewTest(TestCase):
    def test_login_required(self):
        r = self.client.get(reverse("welcome"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)

    def test_user_without_creator_profile_sees_welcome(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("welcome"))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "core/welcome.html")

    def test_user_with_creator_profile_redirects_to_edit(self):
        """Saves a click for returning creators who hit /welcome/ again."""
        user = make_user()
        make_creator(user=user)
        self.client.force_login(user)
        r = self.client.get(reverse("welcome"))
        self.assertRedirects(r, reverse("creators:edit"))


# ---------------------------------------------------------------------------
# Follow / Unfollow
# ---------------------------------------------------------------------------


class FollowCreatorViewTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.fan = make_user()
        self.creator = make_creator(user=self.creator_user)

    def url(self):
        return reverse("follow_creator", kwargs={"slug": self.creator.slug})

    def test_login_required(self):
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 302)

    def test_get_not_allowed(self):
        self.client.force_login(self.fan)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 405)

    def test_404_for_unpublished_creator(self):
        self.creator.publish_status = "draft"
        self.creator.save()
        self.client.force_login(self.fan)
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 404)

    def test_first_follow_creates_notification_and_redirects(self):
        self.client.force_login(self.fan)
        r = self.client.post(self.url())
        self.assertRedirects(r, self.creator.get_absolute_url())
        # M2M relationship recorded.
        self.assertTrue(
            self.fan.profile.followed_creators.filter(pk=self.creator.pk).exists()
        )
        # Notification fired to the followed creator.
        notif = Notification.objects.get(recipient=self.creator_user)
        self.assertEqual(notif.actor, self.fan)
        self.assertEqual(notif.notification_type,
                         Notification.NotificationType.FOLLOW)

    def test_second_follow_unfollows_and_does_not_re_notify(self):
        self.client.force_login(self.fan)
        # Follow once.
        self.client.post(self.url())
        # Follow again → toggles off.
        self.client.post(self.url())
        self.assertFalse(
            self.fan.profile.followed_creators.filter(pk=self.creator.pk).exists()
        )
        # Only the original notification — unfollow doesn't notify again.
        self.assertEqual(Notification.objects.count(), 1)

    def test_htmx_request_returns_follow_button_partial(self):
        self.client.force_login(self.fan)
        r = self.client.post(self.url(), HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "includes/_follow_button.html")


class FollowVenueViewTest(TestCase):
    def setUp(self):
        self.venue_user = make_user()
        self.fan = make_user()
        self.venue = make_venue(user=self.venue_user)

    def url(self):
        return reverse("follow_venue", kwargs={"slug": self.venue.slug})

    def test_follow_creates_notification(self):
        self.client.force_login(self.fan)
        r = self.client.post(self.url())
        self.assertRedirects(r, self.venue.get_absolute_url())
        notif = Notification.objects.get(recipient=self.venue_user)
        self.assertEqual(notif.actor, self.fan)
        self.assertEqual(notif.notification_type,
                         Notification.NotificationType.FOLLOW)
        self.assertIn(self.venue.name, notif.message)

    def test_unfollow_removes_relationship(self):
        self.fan.profile.followed_venues.add(self.venue)
        self.client.force_login(self.fan)
        self.client.post(self.url())
        self.assertFalse(
            self.fan.profile.followed_venues.filter(pk=self.venue.pk).exists()
        )

    def test_htmx_returns_partial(self):
        self.client.force_login(self.fan)
        r = self.client.post(self.url(), HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(r, "includes/_follow_button.html")


# ---------------------------------------------------------------------------
# Availability HTMX (list / add / edit / delete)
# ---------------------------------------------------------------------------


class AvailabilityViewsTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.stranger = make_user()
        self.creator = make_creator(user=self.owner)
        # AvailabilityType seeded once for the whole class.
        self.avail_type = AvailabilityType.objects.create(
            name="Test Available",
            slug="test-available",
            applies_to=AvailabilityType.AppliesTo.CREATOR,
        )

    def url_list(self):
        return reverse("availability_list", kwargs={
            "profile_type": "creator", "slug": self.creator.slug,
        })

    def url_add(self):
        return reverse("add_availability", kwargs={
            "profile_type": "creator", "slug": self.creator.slug,
        })

    def url_edit(self, pk):
        return reverse("edit_availability", kwargs={
            "profile_type": "creator", "slug": self.creator.slug, "pk": pk,
        })

    def url_delete(self, pk):
        return reverse("delete_availability", kwargs={
            "profile_type": "creator", "slug": self.creator.slug, "pk": pk,
        })

    def test_list_403_for_non_owner(self):
        self.client.force_login(self.stranger)
        r = self.client.get(self.url_list())
        self.assertEqual(r.status_code, 403)

    def test_list_renders_for_owner(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.url_list())
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "includes/_availability_list.html")

    def test_add_get_renders_form(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.url_add())
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "includes/_availability_form.html")

    def test_add_post_creates_availability_and_returns_list_partial(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url_add(), {
            "availability_type": self.avail_type.pk,
            "is_active": True,
            "note": "Weekends only",
        })
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "includes/_availability_list.html")
        avail = ProfileAvailability.objects.get(creator=self.creator)
        self.assertEqual(avail.note, "Weekends only")
        self.assertIsNone(avail.venue)

    def test_add_403_for_non_owner(self):
        self.client.force_login(self.stranger)
        r = self.client.post(self.url_add(), {
            "availability_type": self.avail_type.pk, "is_active": True,
        })
        self.assertEqual(r.status_code, 403)

    def test_add_to_venue_profile_sets_venue_field(self):
        venue = make_venue(user=self.owner, name="MyVenue")
        avail_type = AvailabilityType.objects.create(
            name="Venue avail", slug="venue-avail",
            applies_to=AvailabilityType.AppliesTo.VENUE,
        )
        self.client.force_login(self.owner)
        self.client.post(reverse("add_availability", kwargs={
            "profile_type": "venue", "slug": venue.slug,
        }), {"availability_type": avail_type.pk, "is_active": True})
        avail = ProfileAvailability.objects.get(venue=venue)
        self.assertIsNone(avail.creator)

    def test_edit_updates_existing_availability(self):
        avail = ProfileAvailability.objects.create(
            creator=self.creator, availability_type=self.avail_type,
            note="Initial note",
        )
        self.client.force_login(self.owner)
        r = self.client.post(self.url_edit(avail.pk), {
            "availability_type": self.avail_type.pk,
            "is_active": False,
            "note": "Updated note",
        })
        self.assertEqual(r.status_code, 200)
        avail.refresh_from_db()
        self.assertEqual(avail.note, "Updated note")
        self.assertFalse(avail.is_active)

    def test_edit_403_for_non_owner(self):
        avail = ProfileAvailability.objects.create(
            creator=self.creator, availability_type=self.avail_type,
        )
        self.client.force_login(self.stranger)
        r = self.client.get(self.url_edit(avail.pk))
        self.assertEqual(r.status_code, 403)

    def test_delete_removes_availability(self):
        avail = ProfileAvailability.objects.create(
            creator=self.creator, availability_type=self.avail_type,
        )
        self.client.force_login(self.owner)
        r = self.client.post(self.url_delete(avail.pk))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(
            ProfileAvailability.objects.filter(pk=avail.pk).exists()
        )

    def test_delete_403_for_non_owner(self):
        avail = ProfileAvailability.objects.create(
            creator=self.creator, availability_type=self.avail_type,
        )
        self.client.force_login(self.stranger)
        r = self.client.post(self.url_delete(avail.pk))
        self.assertEqual(r.status_code, 403)


# ---------------------------------------------------------------------------
# toggle_like
# ---------------------------------------------------------------------------


class ToggleLikeViewTest(TestCase):
    def setUp(self):
        self.author = make_user()
        self.fan = make_user()
        self.post = CommunityPost.objects.create(
            author=self.author, title="A post", body="Body",
        )

    def url(self, pk=None):
        return reverse("toggle_like", kwargs={"pk": pk or self.post.pk})

    def test_login_required(self):
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 302)

    def test_first_like_adds_user_and_notifies_author(self):
        self.client.force_login(self.fan)
        self.client.post(self.url())
        self.assertTrue(self.post.liked_by.filter(pk=self.fan.pk).exists())
        n = Notification.objects.get(recipient=self.author)
        self.assertEqual(n.notification_type,
                         Notification.NotificationType.LIKE)
        self.assertIn("A post", n.message)

    def test_self_like_does_not_notify(self):
        self.client.force_login(self.author)
        self.client.post(self.url())
        self.assertEqual(
            Notification.objects.filter(recipient=self.author).count(), 0
        )

    def test_second_like_unlikes(self):
        self.post.liked_by.add(self.fan)
        self.client.force_login(self.fan)
        self.client.post(self.url())
        self.assertFalse(self.post.liked_by.filter(pk=self.fan.pk).exists())

    def test_htmx_returns_like_button_partial(self):
        self.client.force_login(self.fan)
        r = self.client.post(self.url(), HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(r, "community/_like_button.html")

    def test_non_htmx_redirects_to_post_detail(self):
        self.client.force_login(self.fan)
        r = self.client.post(self.url())
        self.assertRedirects(r, reverse("community:detail",
                                        kwargs={"pk": self.post.pk}))

    def test_liking_a_reply_redirects_to_parent(self):
        """Likes on replies should land the user back on the parent
        post's detail page, not the reply's pk (which 404s)."""
        reply = CommunityPost.objects.create(
            author=make_user(), parent=self.post, body="Reply body",
        )
        self.client.force_login(self.fan)
        r = self.client.post(self.url(reply.pk))
        self.assertRedirects(r, reverse("community:detail",
                                        kwargs={"pk": self.post.pk}))


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationInboxViewTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.actor = make_user()

    def _make_notif(self, **kw):
        defaults = {
            "recipient": self.user, "actor": self.actor,
            "notification_type": Notification.NotificationType.FOLLOW,
            "message": "Test", "url": "/",
        }
        defaults.update(kw)
        return Notification.objects.create(**defaults)

    def test_login_required(self):
        r = self.client.get(reverse("notifications"))
        self.assertEqual(r.status_code, 302)

    def test_view_marks_unread_as_read(self):
        self._make_notif(is_read=False)
        self._make_notif(is_read=False)
        self._make_notif(is_read=True)
        self.client.force_login(self.user)
        r = self.client.get(reverse("notifications"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["unread_count"], 2)
        # All notifications now marked read.
        self.assertEqual(
            self.user.notifications.filter(is_read=False).count(), 0
        )

    def test_caps_at_50_results(self):
        for i in range(55):
            self._make_notif(message=f"n{i}")
        self.client.force_login(self.user)
        r = self.client.get(reverse("notifications"))
        self.assertEqual(len(r.context["notifications"]), 50)


class MarkAllReadViewTest(TestCase):
    def setUp(self):
        self.user = make_user()
        actor = make_user()
        Notification.objects.create(
            recipient=self.user, actor=actor,
            notification_type=Notification.NotificationType.FOLLOW,
            message="x", url="/", is_read=False,
        )

    def test_get_not_allowed(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("mark_all_read"))
        self.assertEqual(r.status_code, 405)

    def test_post_marks_all_as_read_and_redirects(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("mark_all_read"))
        self.assertRedirects(r, reverse("notifications"))
        self.assertEqual(
            self.user.notifications.filter(is_read=False).count(), 0
        )

    def test_htmx_returns_empty_body(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("mark_all_read"), HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"")


# ---------------------------------------------------------------------------
# preferences + delete_account
# ---------------------------------------------------------------------------


class PreferencesViewTest(TestCase):
    def test_login_required(self):
        r = self.client.get(reverse("preferences"))
        self.assertEqual(r.status_code, 302)

    def test_get_renders_with_user_profile(self):
        user = make_user()
        self.client.force_login(user)
        r = self.client.get(reverse("preferences"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["profile"], user.profile)

    def test_post_saves_email_digest_off(self):
        user = make_user()
        user.profile.email_digest = True
        user.profile.save()
        self.client.force_login(user)
        # Omitting the checkbox in POST → digest off.
        r = self.client.post(reverse("preferences"), {})
        self.assertRedirects(r, reverse("preferences"))
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.email_digest)

    def test_post_saves_email_digest_on(self):
        user = make_user()
        user.profile.email_digest = False
        user.profile.save()
        self.client.force_login(user)
        r = self.client.post(reverse("preferences"),
                             {"email_digest": "on"})
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.email_digest)


class DeleteAccountViewTest(TestCase):
    def test_get_not_allowed(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("delete_account"))
        self.assertEqual(r.status_code, 405)

    def test_missing_confirmation_redirects_back_to_preferences(self):
        user = make_user()
        self.client.force_login(user)
        r = self.client.post(reverse("delete_account"), {"confirm": "no"})
        self.assertRedirects(r, reverse("preferences"))
        # User still exists.
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_correct_confirmation_deletes_user_and_renders_farewell(self):
        user = make_user()
        self.client.force_login(user)
        r = self.client.post(reverse("delete_account"), {"confirm": "DELETE"})
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "core/account_deleted.html")
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_account_deletion_preserves_reports_as_anonymous(self):
        """A user's prior reports must survive account deletion — the
        recent migration switched Report.reporter to nullable with
        on_delete=SET_NULL so moderation history isn't lost when the
        reporter walks away. Without this, deleting a user would
        cascade-delete every Report they ever filed."""
        user = make_user()
        report = Report.objects.create(
            reporter=user,
            content_type=Report.ContentType.PROFILE,
            content_id="abc-123",
            reason="Spam profile",
        )
        self.client.force_login(user)
        self.client.post(reverse("delete_account"), {"confirm": "DELETE"})

        # User row gone, report still exists with reporter=NULL.
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        report.refresh_from_db()
        self.assertIsNone(report.reporter)
        self.assertEqual(report.content_id, "abc-123")
        self.assertEqual(report.reason, "Spam profile")


# ---------------------------------------------------------------------------
# Global search
# ---------------------------------------------------------------------------


class SearchViewTest(TestCase):
    def test_empty_query_renders_with_empty_results(self):
        r = self.client.get(reverse("search"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["total"], 0)
        self.assertEqual(r.context["query"], "")

    def test_finds_creator_by_display_name(self):
        make_creator(user=make_user(), display_name="Querystring Quartet")
        r = self.client.get(reverse("search"), {"q": "Querystring"})
        self.assertGreaterEqual(len(r.context["results"]["creators"]), 1)
        self.assertGreaterEqual(r.context["total"], 1)

    def test_finds_venue_by_name(self):
        make_venue(user=make_user(), name="Singular Stage")
        r = self.client.get(reverse("search"), {"q": "Singular"})
        self.assertGreaterEqual(len(r.context["results"]["venues"]), 1)

    def test_finds_event_by_title(self):
        make_event(title="Uniquely Titled Concert")
        r = self.client.get(reverse("search"), {"q": "Uniquely Titled"})
        self.assertGreaterEqual(len(r.context["results"]["events"]), 1)

    def test_finds_community_post(self):
        CommunityPost.objects.create(
            author=make_user(),
            title="Rare-word post",
            body="Some body",
        )
        r = self.client.get(reverse("search"), {"q": "Rare-word"})
        self.assertGreaterEqual(len(r.context["results"]["posts"]), 1)


# ---------------------------------------------------------------------------
# Reports / Feedback
# ---------------------------------------------------------------------------


class ReportContentViewTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def test_login_required(self):
        self.client.logout()
        r = self.client.post(reverse("report_content"))
        self.assertEqual(r.status_code, 302)

    def test_missing_reason_does_not_create_report(self):
        r = self.client.post(reverse("report_content"), {
            "content_type": "profile", "content_id": "abc",
            "reason": "",   # blank — should be rejected
        })
        self.assertEqual(Report.objects.count(), 0)

    def test_valid_report_is_stored_and_user_redirected(self):
        r = self.client.post(reverse("report_content"), {
            "content_type": "profile",
            "content_id": "abc-123",
            "content_url": "/creators/example/",
            "reason": "Impersonation",
        })
        # The redirect target is whatever content_url the form posted —
        # not a URL we expect to resolve in tests.
        self.assertRedirects(r, "/creators/example/",
                             fetch_redirect_response=False)
        report = Report.objects.get(reporter=self.user)
        self.assertEqual(report.content_type, "profile")
        self.assertEqual(report.reason, "Impersonation")

    @override_settings(
        ADMINS=[("Admin", "admin@example.com")],
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_admin_email_sent_when_admins_configured(self):
        mail.outbox.clear()
        self.client.post(reverse("report_content"), {
            "content_type": "post", "content_id": "p1",
            "content_url": "/community/p1/",
            "reason": "Spam",
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("admin@example.com", mail.outbox[0].to)
        self.assertIn("Spam", mail.outbox[0].body)


class SubmitFeedbackViewTest(TestCase):
    def test_missing_body_redirects_with_error(self):
        r = self.client.post(reverse("submit_feedback"), {
            "feedback_type": "bug", "body": "",
        })
        self.assertRedirects(r, "/feedback/", fetch_redirect_response=False)
        self.assertEqual(Report.objects.count(), 0)

    def test_anonymous_feedback_creates_report_with_null_reporter(self):
        r = self.client.post(reverse("submit_feedback"), {
            "feedback_type": "general", "body": "anonymous note",
            "email": "anon@example.com",
        })
        self.assertRedirects(r, "/feedback/", fetch_redirect_response=False)
        report = Report.objects.get()
        self.assertIsNone(report.reporter)
        self.assertIn("anonymous note", report.reason)
        self.assertIn("anon@example.com", report.reason)

    def test_authenticated_feedback_attaches_reporter(self):
        user = make_user()
        self.client.force_login(user)
        self.client.post(reverse("submit_feedback"), {
            "feedback_type": "feature", "body": "a feature request",
        })
        report = Report.objects.get()
        self.assertEqual(report.reporter, user)

    @override_settings(
        ADMINS=[("Admin", "admin@example.com")],
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_admin_email_sent(self):
        mail.outbox.clear()
        self.client.post(reverse("submit_feedback"), {
            "feedback_type": "bug", "body": "broken thing",
        })
        self.assertEqual(len(mail.outbox), 1)


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------


class AdminDashboardViewTest(TestCase):
    def test_login_required(self):
        r = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(r.status_code, 302)

    def test_non_staff_user_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(r.status_code, 403)

    def test_staff_user_sees_metrics(self):
        staff = make_user()
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)
        r = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(r.status_code, 200)
        # Context must expose the metric dictionary the template reads.
        self.assertIn("metrics", r.context)
        self.assertIn("total_users", r.context["metrics"])
        self.assertIn("open_reports", r.context["metrics"])
