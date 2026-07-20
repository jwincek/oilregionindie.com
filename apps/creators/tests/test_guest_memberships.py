"""
Guest members in bands/collectives (issue #16).

A membership row names exactly one person: a registered creator or a
freeform guest (the drummer who'll never sign up). Guests render by
name with no profile link; guest_email lets the row be claimed later.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.creators.forms import CreatorMembershipForm
from apps.creators.models import CreatorMembership, CreatorProfile

from .helpers import make_creator, make_user


def make_band(**kwargs):
    return make_creator(
        user=make_user(),
        profile_type=CreatorProfile.ProfileType.COLLECTIVE,
        **kwargs,
    )


class GuestMembershipFormTest(TestCase):
    def test_guest_only_is_valid(self):
        form = CreatorMembershipForm(data={
            "guest_name": "Sal the Drummer", "role": "Drums",
            "is_active": True, "sort_order": 0,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_member_and_guest_together_invalid(self):
        member = make_creator(user=make_user())
        form = CreatorMembershipForm(data={
            "member": str(member.pk), "guest_name": "Someone",
            "is_active": True, "sort_order": 0,
        })
        self.assertFalse(form.is_valid())

    def test_neither_is_invalid(self):
        form = CreatorMembershipForm(data={"is_active": True, "sort_order": 0})
        self.assertFalse(form.is_valid())


class GuestMembershipModelTest(TestCase):
    def test_member_name_prefers_profile_then_guest(self):
        band = make_band()
        m = CreatorMembership.objects.create(
            group=band, guest_name="Sal the Drummer",
            guest_email="sal@example.com", role="Drums",
        )
        self.assertEqual(m.member_name, "Sal the Drummer")
        self.assertIn("Sal the Drummer", str(m))

    def test_constraint_rejects_both_and_neither(self):
        band = make_band()
        member = make_creator(user=make_user())
        both = CreatorMembership(group=band, member=member, guest_name="X")
        with self.assertRaises(ValidationError):
            both.full_clean()
        neither = CreatorMembership(group=band)
        with self.assertRaises(ValidationError):
            neither.full_clean()


class GuestMembershipRenderTest(TestCase):
    def test_band_detail_lists_guest_member_by_name(self):
        band = make_band(display_name="The Test Collective")
        CreatorMembership.objects.create(
            group=band, guest_name="Sal the Drummer", role="Drums",
        )
        r = self.client.get(band.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Sal the Drummer")
        self.assertContains(r, "Drums")
