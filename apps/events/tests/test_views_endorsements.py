"""
Tests for the endorsement views in apps.events.views.

Endorsements are public testimonials between a creator and a venue —
either side can publish one, and a notification is sent to the other
party. The endorse view enforces a uniqueness constraint (one per
(creator, venue, author) tuple) and only allows publication by people
on either side of the relationship.
"""

from django.test import TestCase
from django.urls import reverse

from apps.core.models import Notification
from apps.events.models import Endorsement

from .helpers import make_creator, make_user, make_venue


class EndorseViewTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.venue = make_venue(user=self.venue_user)

    def url(self):
        return reverse("events:endorse", kwargs={
            "creator_slug": self.creator.slug, "venue_slug": self.venue.slug,
        })

    def test_login_required(self):
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 302)

    def test_unrelated_user_gets_403(self):
        """Only the creator side or the venue side may publish."""
        self.client.force_login(make_user())
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 403)

    def test_creator_side_get_renders_form(self):
        self.client.force_login(self.creator_user)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["is_creator_side"])

    def test_venue_side_get_renders_form(self):
        self.client.force_login(self.venue_user)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context["is_creator_side"])

    def test_creator_side_post_creates_endorsement_and_notifies_venue(self):
        self.client.force_login(self.creator_user)
        r = self.client.post(self.url(), {
            "body": "Best room in the region. Always pays on time.",
        })
        self.assertRedirects(r, self.venue.get_absolute_url())
        endorsement = Endorsement.objects.get(
            creator=self.creator, venue=self.venue, author=self.creator_user,
        )
        # Notification fired to the OTHER party (the venue owner).
        notif = Notification.objects.get(recipient=self.venue_user)
        self.assertEqual(notif.actor, self.creator_user)
        self.assertIn(self.creator.display_name, notif.message)

    def test_venue_side_post_creates_endorsement_and_notifies_creator(self):
        self.client.force_login(self.venue_user)
        r = self.client.post(self.url(), {
            "body": "Brought the house down. Total pros.",
        })
        self.assertRedirects(r, self.creator.get_absolute_url())
        endorsement = Endorsement.objects.get(
            creator=self.creator, venue=self.venue, author=self.venue_user,
        )
        # Notification fired to the CREATOR side.
        notif = Notification.objects.get(recipient=self.creator_user)
        self.assertEqual(notif.actor, self.venue_user)

    def test_duplicate_endorsement_redirects_with_info(self):
        """The view checks for existing endorsement before saving and
        redirects with an info message rather than violating the DB
        uniqueness constraint."""
        Endorsement.objects.create(
            creator=self.creator, venue=self.venue, author=self.creator_user,
            body="Existing endorsement",
        )
        self.client.force_login(self.creator_user)
        r = self.client.post(self.url(), {"body": "Trying again"})
        # Existing redirects to venue (since the author is the creator side).
        self.assertRedirects(r, self.venue.get_absolute_url())
        # No second row.
        self.assertEqual(
            Endorsement.objects.filter(
                creator=self.creator, venue=self.venue, author=self.creator_user,
            ).count(),
            1,
        )

    def test_404_for_unpublished_creator(self):
        self.creator.publish_status = "draft"
        self.creator.save()
        self.client.force_login(self.venue_user)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 404)


class EditEndorsementViewTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.venue = make_venue(user=self.venue_user)
        self.endorsement = Endorsement.objects.create(
            creator=self.creator, venue=self.venue, author=self.creator_user,
            body="Initial endorsement",
        )

    def url(self):
        return reverse("events:edit_endorsement",
                       kwargs={"pk": self.endorsement.pk})

    def test_author_can_edit(self):
        self.client.force_login(self.creator_user)
        r = self.client.post(self.url(), {"body": "Updated body"})
        self.endorsement.refresh_from_db()
        self.assertEqual(self.endorsement.body, "Updated body")
        self.assertRedirects(r, self.creator.get_absolute_url())

    def test_non_author_gets_404(self):
        """The view filters author=request.user, so other users 404."""
        self.client.force_login(self.venue_user)
        r = self.client.post(self.url(), {"body": "Sneaky edit"})
        self.assertEqual(r.status_code, 404)
        self.endorsement.refresh_from_db()
        self.assertEqual(self.endorsement.body, "Initial endorsement")


class DeleteEndorsementViewTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.venue = make_venue(user=self.venue_user)
        self.endorsement = Endorsement.objects.create(
            creator=self.creator, venue=self.venue, author=self.creator_user,
            body="To be deleted",
        )

    def url(self):
        return reverse("events:delete_endorsement",
                       kwargs={"pk": self.endorsement.pk})

    def test_get_disallowed(self):
        self.client.force_login(self.creator_user)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 405)

    def test_author_can_delete(self):
        self.client.force_login(self.creator_user)
        r = self.client.post(self.url())
        self.assertRedirects(r, self.creator.get_absolute_url())
        self.assertFalse(Endorsement.objects.filter(pk=self.endorsement.pk).exists())

    def test_non_author_404s(self):
        self.client.force_login(self.venue_user)
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Endorsement.objects.filter(pk=self.endorsement.pk).exists())
