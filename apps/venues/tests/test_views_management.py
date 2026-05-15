"""
Tests for venue-management views beyond directory/detail/setup/edit
(those are in test_views.py): profile_events HTMX partial,
submit_for_review state transitions, and the social-links + contacts
HTMX endpoints.
"""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.venues.models import VenueContact, VenueProfile, VenueSocialLink
from apps.core.models import SocialPlatform
from apps.events.tests.helpers import make_event

from .helpers import (
    make_user, make_venue, make_venue_contact, make_venue_social_link,
)


# ---------------------------------------------------------------------------
# profile_events
# ---------------------------------------------------------------------------


class ProfileEventsViewTest(TestCase):
    def setUp(self):
        self.venue = make_venue(name="The Spot")

    def url(self, slug=None):
        return reverse("venues:profile_events",
                       kwargs={"slug": slug or self.venue.slug})

    def test_404_for_unpublished_venue(self):
        venue = make_venue(publish_status="draft")
        r = self.client.get(self.url(venue.slug))
        self.assertEqual(r.status_code, 404)

    def test_upcoming_events_default(self):
        upcoming = make_event(title="Future Show", venue=self.venue,
                              start_datetime=timezone.now() + timedelta(days=7))
        past = make_event(title="Past Show", venue=self.venue,
                          start_datetime=timezone.now() - timedelta(days=7))
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        events = list(r.context["events"])
        self.assertIn(upcoming, events)
        self.assertNotIn(past, events)
        self.assertEqual(r.context["show"], "upcoming")

    def test_past_events_when_show_past(self):
        upcoming = make_event(title="Future Show", venue=self.venue,
                              start_datetime=timezone.now() + timedelta(days=7))
        past = make_event(title="Past Show", venue=self.venue,
                          start_datetime=timezone.now() - timedelta(days=7))
        r = self.client.get(self.url(), {"show": "past"})
        events = list(r.context["events"])
        self.assertIn(past, events)
        self.assertNotIn(upcoming, events)


# ---------------------------------------------------------------------------
# submit_for_review
# ---------------------------------------------------------------------------


class SubmitForReviewViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.venue = make_venue(user=self.owner, publish_status="draft")

    def url(self):
        return reverse("venues:submit_for_review",
                       kwargs={"slug": self.venue.slug})

    def test_get_not_allowed(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 405)

    def test_non_owner_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 403)
        self.venue.refresh_from_db()
        self.assertEqual(self.venue.publish_status, "draft")

    @mock.patch("apps.venues.views.notify_admin_profile_submitted")
    def test_draft_transitions_to_pending_and_notifies_admin(self, mock_notify):
        self.client.force_login(self.owner)
        r = self.client.post(self.url())
        self.assertRedirects(r, reverse("venues:edit",
                                        kwargs={"slug": self.venue.slug}))
        self.venue.refresh_from_db()
        self.assertEqual(self.venue.publish_status, "pending")
        self.assertIsNotNone(self.venue.submitted_at)
        mock_notify.assert_called_once_with(self.venue)

    @mock.patch("apps.venues.views.notify_admin_profile_submitted")
    def test_already_published_no_state_change_no_notify(self, mock_notify):
        self.venue.publish_status = "published"
        self.venue.save()
        self.client.force_login(self.owner)
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 302)  # redirects to edit either way
        self.venue.refresh_from_db()
        self.assertEqual(self.venue.publish_status, "published")
        mock_notify.assert_not_called()

    @mock.patch("apps.venues.views.notify_admin_profile_submitted")
    def test_already_pending_no_state_change_no_notify(self, mock_notify):
        self.venue.publish_status = "pending"
        self.venue.save()
        self.client.force_login(self.owner)
        self.client.post(self.url())
        mock_notify.assert_not_called()


# ---------------------------------------------------------------------------
# Social link HTMX (list / add / edit / delete)
# ---------------------------------------------------------------------------


class SocialLinkViewsTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.stranger = make_user()
        self.venue = make_venue(user=self.owner)

    # ---- list ----

    def test_list_403_for_non_owner(self):
        self.client.force_login(self.stranger)
        r = self.client.get(reverse("venues:social_links",
                                    kwargs={"slug": self.venue.slug}))
        self.assertEqual(r.status_code, 403)

    def test_list_renders_for_owner(self):
        make_venue_social_link(self.venue)
        self.client.force_login(self.owner)
        r = self.client.get(reverse("venues:social_links",
                                    kwargs={"slug": self.venue.slug}))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "venues/_social_links.html")
        self.assertEqual(len(r.context["links"]), 1)

    # ---- add ----

    def test_add_get_renders_form(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("venues:add_social_link",
                                    kwargs={"slug": self.venue.slug}))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "venues/_social_link_form.html")

    def test_add_post_creates_link_and_returns_list(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("venues:add_social_link",
                                     kwargs={"slug": self.venue.slug}), {
            "platform": SocialPlatform.INSTAGRAM,
            "url": "https://instagram.com/thespot",
            "sort_order": 0,
        })
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "venues/_social_links.html")
        link = VenueSocialLink.objects.get(venue=self.venue)
        self.assertEqual(link.url, "https://instagram.com/thespot")

    def test_add_403_for_non_owner(self):
        self.client.force_login(self.stranger)
        r = self.client.post(reverse("venues:add_social_link",
                                     kwargs={"slug": self.venue.slug}), {
            "platform": SocialPlatform.INSTAGRAM,
            "url": "https://instagram.com/x",
            "sort_order": 0,
        })
        self.assertEqual(r.status_code, 403)

    def test_add_invalid_form_re_renders_form(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("venues:add_social_link",
                                     kwargs={"slug": self.venue.slug}), {})
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "venues/_social_link_form.html")
        self.assertFalse(VenueSocialLink.objects.exists())

    # ---- edit ----

    def test_edit_get_renders_form(self):
        link = make_venue_social_link(self.venue)
        self.client.force_login(self.owner)
        r = self.client.get(reverse("venues:edit_social_link",
                                    kwargs={"slug": self.venue.slug,
                                            "pk": link.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["link"], link)

    def test_edit_post_updates_link(self):
        link = make_venue_social_link(self.venue)
        self.client.force_login(self.owner)
        r = self.client.post(reverse("venues:edit_social_link",
                                     kwargs={"slug": self.venue.slug,
                                             "pk": link.pk}), {
            "platform": link.platform,
            "url": "https://updated.example.com",
            "sort_order": 5,
        })
        self.assertEqual(r.status_code, 200)
        link.refresh_from_db()
        self.assertEqual(link.url, "https://updated.example.com")
        self.assertEqual(link.sort_order, 5)

    def test_edit_link_from_other_venue_404s(self):
        """edit_social_link scopes the link to venue=<slug>, so editing
        a link from venue A via venue B's URL 404s."""
        other_venue = make_venue(user=self.owner, name="Second Venue")
        other_link = make_venue_social_link(other_venue)
        self.client.force_login(self.owner)
        r = self.client.get(reverse("venues:edit_social_link",
                                    kwargs={"slug": self.venue.slug,
                                            "pk": other_link.pk}))
        self.assertEqual(r.status_code, 404)

    def test_edit_403_for_non_owner(self):
        link = make_venue_social_link(self.venue)
        self.client.force_login(self.stranger)
        r = self.client.get(reverse("venues:edit_social_link",
                                    kwargs={"slug": self.venue.slug,
                                            "pk": link.pk}))
        self.assertEqual(r.status_code, 403)

    # ---- delete ----

    def test_delete_get_not_allowed(self):
        link = make_venue_social_link(self.venue)
        self.client.force_login(self.owner)
        r = self.client.get(reverse("venues:delete_social_link",
                                    kwargs={"slug": self.venue.slug,
                                            "pk": link.pk}))
        self.assertEqual(r.status_code, 405)

    def test_delete_removes_link(self):
        link = make_venue_social_link(self.venue)
        self.client.force_login(self.owner)
        r = self.client.post(reverse("venues:delete_social_link",
                                     kwargs={"slug": self.venue.slug,
                                             "pk": link.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(VenueSocialLink.objects.filter(pk=link.pk).exists())

    def test_delete_403_for_non_owner(self):
        link = make_venue_social_link(self.venue)
        self.client.force_login(self.stranger)
        r = self.client.post(reverse("venues:delete_social_link",
                                     kwargs={"slug": self.venue.slug,
                                             "pk": link.pk}))
        self.assertEqual(r.status_code, 403)


# ---------------------------------------------------------------------------
# Contact HTMX (list / add / edit / delete)
# ---------------------------------------------------------------------------


class ContactViewsTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.stranger = make_user()
        self.venue = make_venue(user=self.owner)

    def test_list_403_for_non_owner(self):
        self.client.force_login(self.stranger)
        r = self.client.get(reverse("venues:contacts",
                                    kwargs={"slug": self.venue.slug}))
        self.assertEqual(r.status_code, 403)

    def test_list_renders_for_owner(self):
        make_venue_contact(self.venue)
        self.client.force_login(self.owner)
        r = self.client.get(reverse("venues:contacts",
                                    kwargs={"slug": self.venue.slug}))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "venues/_contacts.html")
        self.assertEqual(len(r.context["contacts"]), 1)

    def test_add_get_renders_form(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse("venues:add_contact",
                                    kwargs={"slug": self.venue.slug}))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "venues/_contact_form.html")

    def test_add_post_creates_contact(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("venues:add_contact",
                                     kwargs={"slug": self.venue.slug}), {
            "contact_type": VenueContact.ContactType.BOOKING,
            "method": VenueContact.Method.EMAIL,
            "value": "book@thespot.example",
            "name": "Booking Manager",
            "is_public": "on",
            "sort_order": 0,
        })
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "venues/_contacts.html")
        contact = VenueContact.objects.get(venue=self.venue)
        self.assertEqual(contact.value, "book@thespot.example")

    def test_add_invalid_form_re_renders(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("venues:add_contact",
                                     kwargs={"slug": self.venue.slug}), {})
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "venues/_contact_form.html")
        self.assertFalse(VenueContact.objects.exists())

    def test_add_403_for_non_owner(self):
        self.client.force_login(self.stranger)
        r = self.client.post(reverse("venues:add_contact",
                                     kwargs={"slug": self.venue.slug}), {})
        self.assertEqual(r.status_code, 403)

    def test_edit_post_updates_contact(self):
        contact = make_venue_contact(self.venue)
        self.client.force_login(self.owner)
        r = self.client.post(reverse("venues:edit_contact",
                                     kwargs={"slug": self.venue.slug,
                                             "pk": contact.pk}), {
            "contact_type": VenueContact.ContactType.PRESS,
            "method": VenueContact.Method.EMAIL,
            "value": "press@thespot.example",
            "is_public": "on",
            "sort_order": 0,
        })
        self.assertEqual(r.status_code, 200)
        contact.refresh_from_db()
        self.assertEqual(contact.value, "press@thespot.example")
        self.assertEqual(contact.contact_type, VenueContact.ContactType.PRESS)

    def test_edit_contact_from_other_venue_404s(self):
        other_venue = make_venue(user=self.owner, name="Second Venue")
        other_contact = make_venue_contact(other_venue)
        self.client.force_login(self.owner)
        r = self.client.get(reverse("venues:edit_contact",
                                    kwargs={"slug": self.venue.slug,
                                            "pk": other_contact.pk}))
        self.assertEqual(r.status_code, 404)

    def test_edit_403_for_non_owner(self):
        contact = make_venue_contact(self.venue)
        self.client.force_login(self.stranger)
        r = self.client.get(reverse("venues:edit_contact",
                                    kwargs={"slug": self.venue.slug,
                                            "pk": contact.pk}))
        self.assertEqual(r.status_code, 403)

    def test_delete_get_not_allowed(self):
        contact = make_venue_contact(self.venue)
        self.client.force_login(self.owner)
        r = self.client.get(reverse("venues:delete_contact",
                                    kwargs={"slug": self.venue.slug,
                                            "pk": contact.pk}))
        self.assertEqual(r.status_code, 405)

    def test_delete_removes_contact(self):
        contact = make_venue_contact(self.venue)
        self.client.force_login(self.owner)
        r = self.client.post(reverse("venues:delete_contact",
                                     kwargs={"slug": self.venue.slug,
                                             "pk": contact.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(VenueContact.objects.filter(pk=contact.pk).exists())

    def test_delete_403_for_non_owner(self):
        contact = make_venue_contact(self.venue)
        self.client.force_login(self.stranger)
        r = self.client.post(reverse("venues:delete_contact",
                                     kwargs={"slug": self.venue.slug,
                                             "pk": contact.pk}))
        self.assertEqual(r.status_code, 403)
