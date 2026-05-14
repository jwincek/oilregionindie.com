"""
Tests for apps.community.views — index, detail, create, edit, delete, reply.

Coverage target: every branch in views.py, including the filter
permutations on the index, the parent__isnull=True guard that prevents
treating replies as top-level posts, the author-only edit/delete
permission gate, and the reply notification side effect (with the
self-reply silencing branch).
"""

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.community.models import CommunityPost, Tag
from apps.core.models import BlockedWord, Notification

User = get_user_model()


def make_user(*, password="pw", **kwargs):
    """Create a unique user. UserProfile is auto-created via signal."""
    uid = uuid.uuid4().hex[:8]
    defaults = {"username": f"u_{uid}", "email": f"u_{uid}@example.com"}
    defaults.update(kwargs)
    user = User(**defaults)
    user.set_password(password)
    user.save()
    return user


def make_post(author=None, *, parent=None, **kwargs):
    if author is None:
        author = make_user()
    defaults = {
        "author": author,
        "body": "Body text",
        "post_type": CommunityPost.PostType.DISCUSSION,
    }
    defaults.update(kwargs)
    if parent is not None:
        defaults["parent"] = parent
    return CommunityPost.objects.create(**defaults)


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------


class CommunityIndexTest(TestCase):
    def test_anonymous_can_browse_index(self):
        make_post(title="Public post")
        r = self.client.get(reverse("community:index"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Public post")

    def test_replies_are_hidden_from_index(self):
        """Replies (parent__isnull=False) should not show in the top-level
        feed — only their parents do."""
        parent = make_post(title="Original")
        make_post(parent=parent, body="A reply", title="Reply title")
        r = self.client.get(reverse("community:index"))
        self.assertContains(r, "Original")
        self.assertNotContains(r, "Reply title")

    def test_filter_by_post_type(self):
        make_post(title="Disco discussion",
                  post_type=CommunityPost.PostType.DISCUSSION)
        make_post(title="An announcement",
                  post_type=CommunityPost.PostType.ANNOUNCEMENT)
        r = self.client.get(reverse("community:index"), {"type": "announcement"})
        self.assertContains(r, "An announcement")
        self.assertNotContains(r, "Disco discussion")

    def test_filter_by_tag(self):
        booking_tag = Tag.objects.create(name="Booking", slug="booking")
        Tag.objects.create(name="Gear", slug="gear")
        booking_post = make_post(title="Looking to book")
        booking_post.tags.add(booking_tag)
        make_post(title="Gear question")  # untagged
        r = self.client.get(reverse("community:index"), {"tag": "booking"})
        self.assertContains(r, "Looking to book")
        self.assertNotContains(r, "Gear question")

    def test_search_query_matches_title_or_body(self):
        make_post(title="Found in title", body="something else")
        make_post(title="Other", body="found in body")
        make_post(title="Unrelated", body="nope")
        r = self.client.get(reverse("community:index"), {"q": "found"})
        self.assertContains(r, "Found in title")
        self.assertContains(r, "Other")
        self.assertNotContains(r, "Unrelated")

    def test_htmx_request_returns_partial_template(self):
        make_post(title="X")
        r = self.client.get(reverse("community:index"), HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        # The partial doesn't extend base.html, so the response shouldn't
        # contain the site nav / footer markers.
        self.assertNotContains(r, "<!DOCTYPE html>")


# ---------------------------------------------------------------------------
# detail
# ---------------------------------------------------------------------------


class CommunityDetailTest(TestCase):
    def test_detail_renders_for_valid_post(self):
        post = make_post(title="Hello world")
        r = self.client.get(reverse("community:detail", kwargs={"pk": post.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Hello world")

    def test_detail_404_for_unknown_post(self):
        r = self.client.get(
            reverse("community:detail", kwargs={"pk": uuid.uuid4()}),
        )
        self.assertEqual(r.status_code, 404)

    def test_detail_404_for_a_reply_pk(self):
        """A reply's pk is not a valid top-level detail URL — the view
        filters parent__isnull=True so deep-linking a reply 404s."""
        parent = make_post()
        reply = make_post(parent=parent)
        r = self.client.get(reverse("community:detail", kwargs={"pk": reply.pk}))
        self.assertEqual(r.status_code, 404)

    def test_reply_form_is_none_for_anonymous(self):
        """The context's reply_form should be None unless authenticated —
        the template uses this to gate the reply UI."""
        post = make_post()
        r = self.client.get(reverse("community:detail", kwargs={"pk": post.pk}))
        self.assertIsNone(r.context["reply_form"])

    def test_user_liked_flag_reflects_state(self):
        author = make_user()
        viewer = make_user()
        post = make_post(author)
        post.liked_by.add(viewer)
        self.client.force_login(viewer)
        r = self.client.get(reverse("community:detail", kwargs={"pk": post.pk}))
        self.assertTrue(r.context["user_liked"])
        # And False for a different viewer who hasn't liked it.
        other = make_user()
        self.client.force_login(other)
        r = self.client.get(reverse("community:detail", kwargs={"pk": post.pk}))
        self.assertFalse(r.context["user_liked"])


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class CommunityCreateTest(TestCase):
    def test_login_required(self):
        r = self.client.get(reverse("community:create"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)

    def test_get_renders_form(self):
        self.client.force_login(make_user())
        r = self.client.get(reverse("community:create"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("form", r.context)

    def test_post_creates_post_and_redirects_to_detail(self):
        author = make_user()
        self.client.force_login(author)
        r = self.client.post(reverse("community:create"), {
            "title": "Fresh post",
            "body": "Body content here",
            "post_type": CommunityPost.PostType.DISCUSSION,
        })
        post = CommunityPost.objects.get(title="Fresh post")
        self.assertEqual(post.author, author)
        self.assertRedirects(r, reverse("community:detail", kwargs={"pk": post.pk}))

    def test_blocked_word_in_body_rejects_post(self):
        BlockedWord.objects.create(word="forbiddenphrase")
        self.client.force_login(make_user())
        r = self.client.post(reverse("community:create"), {
            "title": "Title",
            "body": "This body contains a forbiddenphrase here.",
            "post_type": CommunityPost.PostType.DISCUSSION,
        })
        self.assertEqual(r.status_code, 200)  # form re-renders with errors
        self.assertFalse(CommunityPost.objects.filter(title="Title").exists())

    def test_tags_are_saved_via_form_m2m(self):
        tag_a = Tag.objects.create(name="Gear", slug="gear")
        tag_b = Tag.objects.create(name="Booking", slug="booking")
        self.client.force_login(make_user())
        self.client.post(reverse("community:create"), {
            "title": "Tagged",
            "body": "Body",
            "post_type": CommunityPost.PostType.DISCUSSION,
            "tags": [tag_a.pk, tag_b.pk],
        })
        post = CommunityPost.objects.get(title="Tagged")
        self.assertSetEqual(set(post.tags.all()), {tag_a, tag_b})


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


class CommunityEditTest(TestCase):
    def test_login_required(self):
        post = make_post()
        r = self.client.get(reverse("community:edit", kwargs={"pk": post.pk}))
        self.assertEqual(r.status_code, 302)

    def test_non_author_gets_403(self):
        post = make_post()
        self.client.force_login(make_user())  # someone else
        r = self.client.get(reverse("community:edit", kwargs={"pk": post.pk}))
        self.assertEqual(r.status_code, 403)

    def test_author_can_load_edit_form(self):
        author = make_user()
        post = make_post(author=author)
        self.client.force_login(author)
        r = self.client.get(reverse("community:edit", kwargs={"pk": post.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["post"], post)

    def test_author_can_save_edit(self):
        author = make_user()
        post = make_post(author=author, title="Old", body="Old body")
        self.client.force_login(author)
        r = self.client.post(reverse("community:edit", kwargs={"pk": post.pk}), {
            "title": "New title",
            "body": "New body",
            "post_type": post.post_type,
        })
        post.refresh_from_db()
        self.assertEqual(post.title, "New title")
        self.assertEqual(post.body, "New body")
        self.assertRedirects(r, reverse("community:detail", kwargs={"pk": post.pk}))

    def test_edit_404s_for_a_reply_pk(self):
        """edit() filters parent__isnull=True; replies are edited as their
        own kind of post, not via this view."""
        author = make_user()
        parent = make_post(author=author)
        reply = make_post(author=author, parent=parent)
        self.client.force_login(author)
        r = self.client.get(reverse("community:edit", kwargs={"pk": reply.pk}))
        self.assertEqual(r.status_code, 404)

    def test_invalid_edit_post_re_renders_form(self):
        """When the edit POST body fails validation (e.g., contains a
        blocked word), the view re-renders with errors rather than
        redirecting — and the original post stays unchanged."""
        BlockedWord.objects.create(word="forbiddenedit")
        author = make_user()
        post = make_post(author=author, title="Original", body="Original body")
        self.client.force_login(author)
        r = self.client.post(reverse("community:edit", kwargs={"pk": post.pk}), {
            "title": "Edited",
            "body": "Contains forbiddenedit somewhere",
            "post_type": post.post_type,
        })
        self.assertEqual(r.status_code, 200)
        post.refresh_from_db()
        self.assertEqual(post.title, "Original")
        self.assertEqual(post.body, "Original body")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class CommunityDeleteTest(TestCase):
    def test_login_required(self):
        post = make_post()
        r = self.client.post(reverse("community:delete", kwargs={"pk": post.pk}))
        self.assertEqual(r.status_code, 302)

    def test_get_is_disallowed(self):
        """delete is @require_POST."""
        author = make_user()
        post = make_post(author=author)
        self.client.force_login(author)
        r = self.client.get(reverse("community:delete", kwargs={"pk": post.pk}))
        self.assertEqual(r.status_code, 405)

    def test_non_author_gets_403(self):
        post = make_post()
        self.client.force_login(make_user())
        r = self.client.post(reverse("community:delete", kwargs={"pk": post.pk}))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(CommunityPost.objects.filter(pk=post.pk).exists())

    def test_author_deletes_top_level_post_and_lands_on_index(self):
        author = make_user()
        post = make_post(author=author)
        self.client.force_login(author)
        r = self.client.post(reverse("community:delete", kwargs={"pk": post.pk}))
        self.assertRedirects(r, reverse("community:index"))
        self.assertFalse(CommunityPost.objects.filter(pk=post.pk).exists())

    def test_author_deletes_reply_and_lands_on_parent_detail(self):
        author = make_user()
        parent = make_post(author=author)
        reply = make_post(author=author, parent=parent)
        self.client.force_login(author)
        r = self.client.post(reverse("community:delete", kwargs={"pk": reply.pk}))
        self.assertRedirects(r, reverse("community:detail", kwargs={"pk": parent.pk}))
        self.assertFalse(CommunityPost.objects.filter(pk=reply.pk).exists())


# ---------------------------------------------------------------------------
# reply
# ---------------------------------------------------------------------------


class CommunityReplyTest(TestCase):
    def test_login_required(self):
        post = make_post()
        r = self.client.post(reverse("community:reply", kwargs={"pk": post.pk}),
                             {"body": "hi"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)

    def test_cannot_reply_to_a_reply(self):
        """The reply view filters parent__isnull=True so threads stay
        flat — a reply's pk doesn't accept further replies."""
        parent = make_post()
        first_reply = make_post(parent=parent)
        self.client.force_login(make_user())
        r = self.client.post(
            reverse("community:reply", kwargs={"pk": first_reply.pk}),
            {"body": "nested attempt"},
        )
        self.assertEqual(r.status_code, 404)

    def test_reply_inherits_parents_post_type(self):
        parent = make_post(post_type=CommunityPost.PostType.OPPORTUNITY)
        replier = make_user()
        self.client.force_login(replier)
        self.client.post(reverse("community:reply", kwargs={"pk": parent.pk}),
                         {"body": "I'm interested"})
        reply = CommunityPost.objects.get(parent=parent)
        self.assertEqual(reply.post_type, CommunityPost.PostType.OPPORTUNITY)
        self.assertEqual(reply.author, replier)

    def test_reply_creates_notification_for_parent_author(self):
        op = make_user()
        parent = make_post(author=op, title="My question")
        replier = make_user()
        self.client.force_login(replier)
        self.client.post(reverse("community:reply", kwargs={"pk": parent.pk}),
                         {"body": "answer"})
        n = Notification.objects.get(recipient=op)
        self.assertEqual(n.actor, replier)
        self.assertEqual(n.notification_type, Notification.NotificationType.REPLY)
        self.assertIn("My question", n.message)
        self.assertEqual(n.url, f"/community/{parent.pk}/")

    def test_self_reply_does_not_notify(self):
        """Replying to your own post shouldn't notify yourself."""
        author = make_user()
        parent = make_post(author=author)
        self.client.force_login(author)
        self.client.post(reverse("community:reply", kwargs={"pk": parent.pk}),
                         {"body": "talking to myself"})
        self.assertEqual(Notification.objects.filter(recipient=author).count(), 0)

    def test_invalid_reply_body_creates_no_reply(self):
        """A blocked-word body is rejected by ReplyForm; the view still
        redirects to the parent (which is the bare-minimum UX), but no
        reply row is created and no notification fires."""
        BlockedWord.objects.create(word="blockedterm")
        op = make_user()
        parent = make_post(author=op)
        self.client.force_login(make_user())
        self.client.post(reverse("community:reply", kwargs={"pk": parent.pk}),
                         {"body": "this contains blockedterm"})
        self.assertFalse(CommunityPost.objects.filter(parent=parent).exists())
        self.assertFalse(Notification.objects.exists())
