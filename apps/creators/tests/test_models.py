"""
Tests for creators app models.

Covers: auto-slug generation, sync_disciplines_from_skills, can_be_edited_by,
can_accept_payments, is_group, skills_by_discipline, memberships, and
string representations.
"""

from django.db import IntegrityError
from django.test import TestCase

from apps.creators.models import (
    CreatorMembership,
    CreatorProfile,
    Discipline,
    Genre,
    MediaItem,
    Skill,
)

from .helpers import (
    make_band,
    make_collective,
    make_creator,
    make_discipline,
    make_genre,
    make_media_item,
    make_membership,
    make_skill,
    make_social_link,
    make_user,
)


# ---------------------------------------------------------------------------
# Discipline / Genre / Skill basics
# ---------------------------------------------------------------------------


class DisciplineModelTest(TestCase):
    def test_auto_slug(self):
        d = Discipline(name="Visual Artist")
        d.save()
        self.assertEqual(d.slug, "visual-artist")

    def test_preserves_explicit_slug(self):
        d = Discipline(name="Visual Artist", slug="custom-slug")
        d.save()
        self.assertEqual(d.slug, "custom-slug")

    def test_str(self):
        d = make_discipline("Jeweler")
        self.assertEqual(str(d), "Jeweler")


class GenreModelTest(TestCase):
    def test_auto_slug(self):
        g = Genre(name="Indie Rock")
        g.save()
        self.assertEqual(g.slug, "indie-rock")

    def test_str(self):
        g = make_genre("Blues")
        self.assertEqual(str(g), "Blues")


class SkillModelTest(TestCase):
    def test_auto_slug(self):
        d = make_discipline("Musician")
        s = Skill(name="Electric Guitar", discipline=d)
        s.save()
        self.assertEqual(s.slug, "electric-guitar")

    def test_str_includes_discipline(self):
        d = make_discipline("Jeweler")
        s = make_skill("Silversmithing", discipline=d)
        self.assertEqual(str(s), "Silversmithing (Jeweler)")

    def test_unique_constraint_per_discipline(self):
        d = make_discipline("Musician")
        make_skill("Guitar", discipline=d)
        with self.assertRaises(IntegrityError):
            Skill.objects.create(name="Guitar", discipline=d)

    def test_same_name_different_disciplines(self):
        """'Screen Printing' can exist under both Visual Artist and Printmaker."""
        d1 = make_discipline("Visual Artist")
        d2 = make_discipline("Printmaker")
        s1 = make_skill("Screen Printing", discipline=d1)
        s2 = make_skill("Screen Printing", discipline=d2)
        self.assertNotEqual(s1.pk, s2.pk)


# ---------------------------------------------------------------------------
# CreatorProfile - auto slug
# ---------------------------------------------------------------------------


class CreatorSlugTest(TestCase):
    def test_auto_generates_slug(self):
        creator = make_creator(display_name="Jerome Wincek")
        self.assertEqual(creator.slug, "jerome-wincek")

    def test_slug_uniqueness(self):
        """Second creator with same name gets a numbered slug."""
        c1 = make_creator(display_name="Seth Brewster")
        c2 = make_creator(display_name="Seth Brewster")
        self.assertEqual(c1.slug, "seth-brewster")
        self.assertEqual(c2.slug, "seth-brewster-1")

    def test_third_duplicate_slug(self):
        make_creator(display_name="Lauren Joyce")
        make_creator(display_name="Lauren Joyce")
        c3 = make_creator(display_name="Lauren Joyce")
        self.assertEqual(c3.slug, "lauren-joyce-2")

    def test_preserves_explicit_slug(self):
        creator = make_creator(display_name="Test", slug="custom-slug")
        self.assertEqual(creator.slug, "custom-slug")

    def test_slug_not_overwritten_on_save(self):
        creator = make_creator(display_name="Original Name")
        original_slug = creator.slug
        creator.display_name = "New Name"
        creator.save()
        self.assertEqual(creator.slug, original_slug)


# ---------------------------------------------------------------------------
# CreatorProfile - get_absolute_url
# ---------------------------------------------------------------------------


class CreatorAbsoluteUrlTest(TestCase):
    def test_url_uses_slug(self):
        creator = make_creator(display_name="Test Artist")
        self.assertEqual(creator.get_absolute_url(), "/creators/test-artist/")


# ---------------------------------------------------------------------------
# CreatorProfile - profile types and is_group
# ---------------------------------------------------------------------------


class ProfileTypeTest(TestCase):
    def test_individual_is_not_group(self):
        creator = make_creator()
        self.assertFalse(creator.is_group)

    def test_band_is_group(self):
        band = make_band()
        self.assertTrue(band.is_group)

    def test_collective_is_group(self):
        collective = make_collective()
        self.assertTrue(collective.is_group)

    def test_default_profile_type_is_individual(self):
        creator = make_creator()
        self.assertEqual(creator.profile_type, CreatorProfile.ProfileType.INDIVIDUAL)


# ---------------------------------------------------------------------------
# CreatorProfile - sync_disciplines_from_skills
# ---------------------------------------------------------------------------


class SyncDisciplinesFromSkillsTest(TestCase):
    def setUp(self):
        self.musician = make_discipline("Musician")
        self.jeweler = make_discipline("Jeweler")
        self.guitar = make_skill("Guitar", discipline=self.musician)
        self.bass = make_skill("Bass", discipline=self.musician)
        self.silversmithing = make_skill("Silversmithing", discipline=self.jeweler)

    def test_adds_discipline_from_single_skill(self):
        creator = make_creator()
        creator.skills.add(self.guitar)
        creator.sync_disciplines_from_skills()
        self.assertIn(self.musician, creator.disciplines.all())

    def test_adds_multiple_disciplines_from_cross_discipline_skills(self):
        """A guitar-playing silversmith gets both Musician and Jeweler."""
        creator = make_creator()
        creator.skills.add(self.guitar, self.silversmithing)
        creator.sync_disciplines_from_skills()
        disciplines = set(creator.disciplines.all())
        self.assertEqual(disciplines, {self.musician, self.jeweler})

    def test_preserves_manually_added_disciplines(self):
        """Manual disciplines are not removed when syncing from skills."""
        photographer = make_discipline("Photographer")
        creator = make_creator()
        creator.disciplines.add(photographer)
        creator.skills.add(self.guitar)
        creator.sync_disciplines_from_skills()
        disciplines = set(creator.disciplines.all())
        self.assertIn(photographer, disciplines)
        self.assertIn(self.musician, disciplines)

    def test_no_duplicates_with_multiple_skills_in_same_discipline(self):
        """Adding Guitar and Bass should only add Musician once."""
        creator = make_creator()
        creator.skills.add(self.guitar, self.bass)
        creator.sync_disciplines_from_skills()
        musician_count = creator.disciplines.filter(name="Musician").count()
        self.assertEqual(musician_count, 1)

    def test_no_error_with_no_skills(self):
        creator = make_creator()
        creator.sync_disciplines_from_skills()  # should not raise
        self.assertEqual(creator.disciplines.count(), 0)


# ---------------------------------------------------------------------------
# CreatorProfile - skills_by_discipline
# ---------------------------------------------------------------------------


class SkillsByDisciplineTest(TestCase):
    def test_groups_skills_correctly(self):
        musician = make_discipline("Musician")
        jeweler = make_discipline("Jeweler")
        guitar = make_skill("Guitar", discipline=musician)
        vocals = make_skill("Vocals", discipline=musician)
        silver = make_skill("Silversmithing", discipline=jeweler)

        creator = make_creator()
        creator.skills.add(guitar, vocals, silver)

        grouped = creator.skills_by_discipline
        self.assertIn("Musician", grouped)
        self.assertIn("Jeweler", grouped)
        self.assertEqual(set(grouped["Musician"]), {"Guitar", "Vocals"})
        self.assertEqual(grouped["Jeweler"], ["Silversmithing"])

    def test_empty_when_no_skills(self):
        creator = make_creator()
        self.assertEqual(creator.skills_by_discipline, {})


# ---------------------------------------------------------------------------
# CreatorProfile - can_be_edited_by
# ---------------------------------------------------------------------------


class CanBeEditedByTest(TestCase):
    def test_owner_can_edit(self):
        user = make_user()
        creator = make_creator(user=user)
        self.assertTrue(creator.can_be_edited_by(user))

    def test_manager_can_edit(self):
        owner = make_user()
        manager = make_user()
        creator = make_creator(user=owner)
        creator.managers.add(manager)
        self.assertTrue(creator.can_be_edited_by(manager))

    def test_random_user_cannot_edit(self):
        owner = make_user()
        stranger = make_user()
        creator = make_creator(user=owner)
        self.assertFalse(creator.can_be_edited_by(stranger))

    def test_manager_of_different_profile_cannot_edit(self):
        owner_a = make_user()
        owner_b = make_user()
        manager = make_user()
        profile_a = make_creator(user=owner_a, display_name="Profile A")
        profile_b = make_creator(user=owner_b, display_name="Profile B")
        profile_a.managers.add(manager)
        self.assertTrue(profile_a.can_be_edited_by(manager))
        self.assertFalse(profile_b.can_be_edited_by(manager))


# ---------------------------------------------------------------------------
# CreatorProfile - can_accept_payments
# ---------------------------------------------------------------------------


class CanAcceptPaymentsTest(TestCase):
    def test_false_by_default(self):
        creator = make_creator()
        self.assertFalse(creator.can_accept_payments)

    def test_false_with_only_account_id(self):
        creator = make_creator(stripe_account_id="acct_123")
        self.assertFalse(creator.can_accept_payments)

    def test_false_with_only_onboarded(self):
        creator = make_creator(stripe_onboarded=True)
        self.assertFalse(creator.can_accept_payments)

    def test_true_when_both_set(self):
        creator = make_creator(stripe_account_id="acct_123", stripe_onboarded=True)
        self.assertTrue(creator.can_accept_payments)


# ---------------------------------------------------------------------------
# CreatorProfile - discipline_list / skill_list
# ---------------------------------------------------------------------------


class DisplayListTest(TestCase):
    def test_discipline_list(self):
        creator = make_creator()
        d1 = make_discipline("Musician")
        d2 = make_discipline("Jeweler")
        creator.disciplines.add(d1, d2)
        # ordering is alphabetical
        self.assertEqual(creator.discipline_list, "Jeweler, Musician")

    def test_skill_list(self):
        d = make_discipline("Musician")
        s1 = make_skill("Bass", discipline=d)
        s2 = make_skill("Guitar", discipline=d)
        creator = make_creator()
        creator.skills.add(s1, s2)
        self.assertIn("Bass", creator.skill_list)
        self.assertIn("Guitar", creator.skill_list)

    def test_empty_lists(self):
        creator = make_creator()
        self.assertEqual(creator.discipline_list, "")
        self.assertEqual(creator.skill_list, "")


# ---------------------------------------------------------------------------
# CreatorProfile - str
# ---------------------------------------------------------------------------


class CreatorStrTest(TestCase):
    def test_str_is_display_name(self):
        creator = make_creator(display_name="Floodplains")
        self.assertEqual(str(creator), "Floodplains")


# ---------------------------------------------------------------------------
# CreatorMembership
# ---------------------------------------------------------------------------


class MembershipTest(TestCase):
    def setUp(self):
        self.band = make_band(display_name="The Old Hats")
        self.member_a = make_creator(display_name="Alice")
        self.member_b = make_creator(display_name="Bob")

    def test_create_membership(self):
        m = make_membership(self.band, self.member_a, role="Guitar")
        self.assertEqual(str(m), "Alice in The Old Hats (Guitar)")

    def test_str_without_role(self):
        m = make_membership(self.band, self.member_a)
        self.assertEqual(str(m), "Alice in The Old Hats")

    def test_active_members(self):
        make_membership(self.band, self.member_a, role="Guitar", is_active=True)
        make_membership(self.band, self.member_b, role="Bass", is_active=False)
        active = list(self.band.active_members)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].member, self.member_a)

    def test_active_memberships(self):
        band2 = make_band(display_name="Side Project")
        make_membership(self.band, self.member_a, is_active=True)
        make_membership(band2, self.member_a, is_active=True)
        memberships = list(self.member_a.active_memberships)
        self.assertEqual(len(memberships), 2)

    def test_unique_constraint(self):
        make_membership(self.band, self.member_a)
        with self.assertRaises(IntegrityError):
            make_membership(self.band, self.member_a)

    def test_inactive_memberships_excluded(self):
        make_membership(self.band, self.member_a, is_active=False)
        self.assertEqual(list(self.member_a.active_memberships), [])


# ---------------------------------------------------------------------------
# CreatorSocialLink
# ---------------------------------------------------------------------------


class SocialLinkTest(TestCase):
    def test_str(self):
        creator = make_creator(display_name="Test Artist")
        link = make_social_link(creator)
        self.assertIn("Bandcamp", str(link))
        self.assertIn("Test Artist", str(link))


# ---------------------------------------------------------------------------
# MediaItem
# ---------------------------------------------------------------------------


class MediaItemTest(TestCase):
    def test_str(self):
        creator = make_creator()
        item = make_media_item(creator, title="Reckoning", media_type=MediaItem.MediaType.AUDIO)
        self.assertEqual(str(item), "Reckoning (Audio)")

    def test_featured_media_filter(self):
        creator = make_creator()
        make_media_item(creator, title="Track 1", is_featured=True)
        make_media_item(creator, title="Track 2", is_featured=False)
        make_media_item(creator, title="Track 3", is_featured=True)
        featured = list(creator.featured_media)
        self.assertEqual(len(featured), 2)

    def test_ordering_by_sort_order(self):
        creator = make_creator()
        m2 = make_media_item(creator, title="Second", sort_order=2)
        m1 = make_media_item(creator, title="First", sort_order=1)
        items = list(creator.media_items.all())
        self.assertEqual(items[0].title, "First")
        self.assertEqual(items[1].title, "Second")
