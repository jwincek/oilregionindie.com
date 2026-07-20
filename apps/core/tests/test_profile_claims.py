"""
Unclaimed (admin-seeded) profiles and the Phase A claim flow (issue #19).

Unclaimed profiles let the directory be complete before its subjects
register: admins seed them (user=None), visitors see a claim banner,
claim requests email the admins, and ownership is assigned in the
Django admin after human verification.
"""
from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Notification
from apps.core.notifications import notify_profile_approved
from apps.creators.admin import CreatorProfileAdmin
from apps.creators.models import CreatorMembership, CreatorProfile
from apps.creators.tests.helpers import make_creator, make_user
from apps.venues.tests.helpers import make_venue


def make_unclaimed_creator(display_name="Seeded Songwriter", **kwargs):
    return CreatorProfile.objects.create(
        user=None,
        display_name=display_name,
        publish_status=kwargs.pop("publish_status", "published"),
        profile_type=kwargs.pop("profile_type", CreatorProfile.ProfileType.INDIVIDUAL),
        **kwargs,
    )


def make_unclaimed_venue():
    venue = make_venue(user=make_user())
    venue.user = None
    venue.save(update_fields=["user"])
    return venue


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ClaimBannerTest(TestCase):
    def test_unclaimed_creator_shows_banner_and_no_booking_cta(self):
        creator = make_unclaimed_creator()
        r = self.client.get(creator.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Is this you?")
        self.assertContains(r, "Sign in to claim it")
        self.assertNotContains(r, "Invite to Book")

    def test_claimed_creator_shows_no_banner(self):
        creator = make_creator(user=make_user())
        r = self.client.get(creator.get_absolute_url())
        self.assertNotContains(r, "Is this you?")

    def test_unclaimed_venue_shows_banner(self):
        venue = make_unclaimed_venue()
        r = self.client.get(venue.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Is this you?")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ADMINS=[("Admin", "admin@example.com")],
)
class ClaimRequestViewTest(TestCase):
    def test_claim_post_emails_admins_and_redirects(self):
        creator = make_unclaimed_creator(claim_contact_email="mgr@example.com")
        claimant = make_user()
        self.client.force_login(claimant)
        url = reverse("request_claim", kwargs={"profile_type": "creator", "slug": creator.slug})
        r = self.client.post(url, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "verify and connect")
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn(claimant.email, body)
        self.assertIn(creator.display_name, body)
        self.assertIn("mgr@example.com", body)

    def test_claimed_profile_cannot_be_claimed_again(self):
        creator = make_creator(user=make_user())
        self.client.force_login(make_user())
        url = reverse("request_claim", kwargs={"profile_type": "creator", "slug": creator.slug})
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_claim_requires_login(self):
        creator = make_unclaimed_creator()
        url = reverse("request_claim", kwargs={"profile_type": "creator", "slug": creator.slug})
        self.assertEqual(self.client.post(url).status_code, 302)  # to login


class UnclaimedBookingGuardTest(TestCase):
    """Direct-URL booking attempts against unclaimed profiles must 404 —
    the CTA is hidden, but the URL is guessable, and the notification
    path downstream requires a recipient."""

    def test_booking_create_404s_for_unclaimed_creator(self):
        creator = make_unclaimed_creator()
        self.client.force_login(make_user())
        url = reverse("events:booking_create", kwargs={
            "direction": "to-creator", "profile_slug": creator.slug,
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_booking_create_404s_for_unclaimed_venue(self):
        venue = make_unclaimed_venue()
        user = make_user()
        make_creator(user=user)
        self.client.force_login(user)
        url = reverse("events:booking_create", kwargs={
            "direction": "to-venue", "profile_slug": venue.slug,
        })
        self.assertEqual(self.client.get(url).status_code, 404)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class UnclaimedNotificationSafetyTest(TestCase):
    def test_approving_unclaimed_profile_notifies_no_one_and_survives(self):
        creator = make_unclaimed_creator(publish_status="pending")
        notify_profile_approved(creator)  # must not raise
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)


class AdoptGuestMembershipsActionTest(TestCase):
    def setUp(self):
        self.admin = CreatorProfileAdmin(CreatorProfile, AdminSite())
        self.admin.message_user = mock.Mock()

    def test_adopts_matching_guest_rows_and_skips_duplicates(self):
        owner = make_user()
        profile = make_creator(user=owner, display_name="Sal Real")
        band_a = make_creator(user=make_user(), display_name="Band A",
                              profile_type=CreatorProfile.ProfileType.BAND)
        band_b = make_creator(user=make_user(), display_name="Band B",
                              profile_type=CreatorProfile.ProfileType.BAND)
        matching = CreatorMembership.objects.create(
            group=band_a, guest_name="Sal", guest_email=owner.email.upper(),
        )
        CreatorMembership.objects.create(group=band_b, member=profile)
        duplicate_guest = CreatorMembership.objects.create(
            group=band_b, guest_name="Sal again", guest_email=owner.email,
        )

        self.admin.adopt_guest_memberships(
            mock.Mock(), CreatorProfile.objects.filter(pk=profile.pk)
        )

        matching.refresh_from_db()
        self.assertEqual(matching.member, profile)
        self.assertEqual(matching.guest_name, "")
        duplicate_guest.refresh_from_db()
        self.assertIsNone(duplicate_guest.member)  # skipped — real row exists
