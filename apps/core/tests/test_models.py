"""
Tests for core app models and signals.

Covers: Address properties, UserProfile auto-creation, display_name fallback.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Address, UserProfile

User = get_user_model()


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------


class AddressModelTest(TestCase):
    def test_short_display(self):
        addr = Address.objects.create(city="Oil City", state="PA")
        self.assertEqual(addr.short_display, "Oil City, PA")

    def test_short_display_city_only(self):
        addr = Address.objects.create(city="Franklin", state="")
        self.assertEqual(addr.short_display, "Franklin")

    def test_full_display(self):
        addr = Address.objects.create(
            street="123 Seneca St", city="Oil City", state="PA", zip_code="16301"
        )
        self.assertEqual(addr.full_display, "123 Seneca St, Oil City, PA, 16301")

    def test_full_display_without_street(self):
        addr = Address.objects.create(city="Titusville", state="PA", zip_code="16354")
        self.assertEqual(addr.full_display, "Titusville, PA, 16354")

    def test_full_display_with_street_2(self):
        addr = Address.objects.create(
            street="100 Main St", street_2="Suite 3", city="Franklin", state="PA"
        )
        self.assertEqual(addr.full_display, "100 Main St, Suite 3, Franklin, PA")

    def test_str_uses_short_display(self):
        addr = Address.objects.create(city="Oil City", state="PA")
        self.assertEqual(str(addr), "Oil City, PA")

    def test_has_coordinates_true(self):
        addr = Address.objects.create(
            city="Oil City", state="PA",
            latitude=41.4340, longitude=-79.7026,
        )
        self.assertTrue(addr.has_coordinates)

    def test_has_coordinates_false(self):
        addr = Address.objects.create(city="Oil City", state="PA")
        self.assertFalse(addr.has_coordinates)

    def test_has_coordinates_partial(self):
        addr = Address.objects.create(city="Oil City", state="PA", latitude=41.4340)
        self.assertFalse(addr.has_coordinates)

    def test_default_country(self):
        addr = Address.objects.create(city="Oil City", state="PA")
        self.assertEqual(addr.country, "US")


# ---------------------------------------------------------------------------
# UserProfile auto-creation signal
# ---------------------------------------------------------------------------


class UserProfileSignalTest(TestCase):
    def test_profile_auto_created_on_user_creation(self):
        user = User.objects.create_user(
            username="signaltest", email="signal@example.com", password="test123"
        )
        self.assertTrue(hasattr(user, "profile"))
        self.assertIsInstance(user.profile, UserProfile)

    def test_profile_not_duplicated_on_user_save(self):
        user = User.objects.create_user(
            username="savetest", email="save@example.com", password="test123"
        )
        user.first_name = "Updated"
        user.save()
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)


# ---------------------------------------------------------------------------
# UserProfile
# ---------------------------------------------------------------------------


class UserProfileModelTest(TestCase):
    def test_display_name_when_set(self):
        user = User.objects.create_user(
            username="named", email="named@example.com", password="test123"
        )
        user.profile.display_name = "Jerome"
        user.profile.save()
        self.assertEqual(user.profile.get_display_name(), "Jerome")
        self.assertEqual(str(user.profile), "Jerome")

    def test_display_name_falls_back_to_email_prefix(self):
        user = User.objects.create_user(
            username="fallback", email="jerome.wincek@example.com", password="test123"
        )
        self.assertEqual(user.profile.get_display_name(), "jerome.wincek")

    def test_display_name_falls_back_to_user_pk(self):
        user = User.objects.create_user(
            username="noemail", email="", password="test123"
        )
        self.assertIn("User", user.profile.get_display_name())

    def test_defaults(self):
        user = User.objects.create_user(
            username="defaults", email="defaults@example.com", password="test123"
        )
        profile = user.profile
        self.assertEqual(profile.display_name, "")
        self.assertEqual(profile.bio, "")
        self.assertEqual(profile.location, "")
        self.assertTrue(profile.email_digest)
        self.assertIsNone(profile.address)
        self.assertEqual(profile.followed_creators.count(), 0)
        self.assertEqual(profile.followed_venues.count(), 0)

    def test_follow_creators(self):
        from apps.creators.tests.helpers import make_creator
        user = User.objects.create_user(
            username="fan", email="fan@example.com", password="test123"
        )
        creator = make_creator(display_name="Followed Artist")
        user.profile.followed_creators.add(creator)
        self.assertEqual(user.profile.followed_creators.count(), 1)
        self.assertIn(user.profile, creator.followers.all())

    def test_follow_venues(self):
        from apps.venues.tests.helpers import make_venue
        user = User.objects.create_user(
            username="venufan", email="venufan@example.com", password="test123"
        )
        venue = make_venue(name="Followed Venue")
        user.profile.followed_venues.add(venue)
        self.assertEqual(user.profile.followed_venues.count(), 1)
        self.assertIn(user.profile, venue.followers.all())


# ---------------------------------------------------------------------------
# AvailabilityType
# ---------------------------------------------------------------------------


class AvailabilityTypeTest(TestCase):
    def test_auto_slug(self):
        from apps.core.models import AvailabilityType
        at = AvailabilityType(name="Available for Booking", applies_to="creator")
        at.save()
        self.assertEqual(at.slug, "available-for-booking")

    def test_preserves_explicit_slug(self):
        from apps.core.models import AvailabilityType
        at = AvailabilityType(name="Test", slug="custom", applies_to="creator")
        at.save()
        self.assertEqual(at.slug, "custom")

    def test_str(self):
        from apps.core.models import AvailabilityType
        at = AvailabilityType.objects.create(name="Open to Collaboration", applies_to="creator")
        self.assertEqual(str(at), "Open to Collaboration")

    def test_for_creators(self):
        from apps.core.models import AvailabilityType
        AvailabilityType.objects.create(name="Creator Only", applies_to="creator")
        AvailabilityType.objects.create(name="Venue Only", applies_to="venue")
        AvailabilityType.objects.create(name="Both Type", applies_to="both")
        creator_types = AvailabilityType.for_creators()
        names = set(creator_types.values_list("name", flat=True))
        self.assertIn("Creator Only", names)
        self.assertIn("Both Type", names)
        self.assertNotIn("Venue Only", names)

    def test_for_venues(self):
        from apps.core.models import AvailabilityType
        AvailabilityType.objects.create(name="Creator Only V", applies_to="creator")
        AvailabilityType.objects.create(name="Venue Only V", applies_to="venue")
        AvailabilityType.objects.create(name="Both Type V", applies_to="both")
        venue_types = AvailabilityType.for_venues()
        names = set(venue_types.values_list("name", flat=True))
        self.assertIn("Venue Only V", names)
        self.assertIn("Both Type V", names)
        self.assertNotIn("Creator Only V", names)


# ---------------------------------------------------------------------------
# ProfileAvailability
# ---------------------------------------------------------------------------


class ProfileAvailabilityTest(TestCase):
    def setUp(self):
        from apps.core.models import AvailabilityType
        self.avail_booking = AvailabilityType.objects.create(
            name="Available for Booking", applies_to="creator", sort_order=1,
        )
        self.avail_commissions = AvailabilityType.objects.create(
            name="Accepting Commissions", applies_to="creator", sort_order=2,
        )

    def test_create_for_creator(self):
        from apps.core.models import ProfileAvailability
        from apps.creators.tests.helpers import make_creator
        creator = make_creator(display_name="Avail Test")
        pa = ProfileAvailability.objects.create(
            creator=creator, availability_type=self.avail_booking,
            note="Weekends only",
        )
        self.assertIn("Available for Booking", str(pa))
        self.assertIn("Active", str(pa))
        self.assertEqual(pa.profile, creator)

    def test_create_for_venue(self):
        from apps.core.models import AvailabilityType, ProfileAvailability
        from apps.venues.tests.helpers import make_venue
        avail_venue = AvailabilityType.objects.create(
            name="Accepting Requests", applies_to="venue",
        )
        venue = make_venue(name="Avail Venue")
        pa = ProfileAvailability.objects.create(
            venue=venue, availability_type=avail_venue,
        )
        self.assertEqual(pa.profile, venue)

    def test_paused_availability(self):
        from apps.core.models import ProfileAvailability
        from apps.creators.tests.helpers import make_creator
        creator = make_creator(display_name="Pause Test")
        pa = ProfileAvailability.objects.create(
            creator=creator, availability_type=self.avail_booking,
            is_active=False,
        )
        self.assertIn("Paused", str(pa))

    def test_active_availabilities_property(self):
        from apps.core.models import ProfileAvailability
        from apps.creators.tests.helpers import make_creator
        creator = make_creator(display_name="Active Test")
        ProfileAvailability.objects.create(
            creator=creator, availability_type=self.avail_booking, is_active=True,
        )
        ProfileAvailability.objects.create(
            creator=creator, availability_type=self.avail_commissions, is_active=False,
        )
        active = list(creator.active_availabilities)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].availability_type.name, "Available for Booking")

    def test_is_available_for_booking(self):
        from apps.core.models import ProfileAvailability
        from apps.creators.tests.helpers import make_creator
        creator = make_creator(display_name="Booking Check")
        self.assertFalse(creator.is_available_for_booking)
        ProfileAvailability.objects.create(
            creator=creator, availability_type=self.avail_booking, is_active=True,
        )
        self.assertTrue(creator.is_available_for_booking)

    def test_unique_constraint_per_creator(self):
        from django.db import IntegrityError
        from apps.core.models import ProfileAvailability
        from apps.creators.tests.helpers import make_creator
        creator = make_creator(display_name="Unique Test")
        ProfileAvailability.objects.create(
            creator=creator, availability_type=self.avail_booking,
        )
        with self.assertRaises(IntegrityError):
            ProfileAvailability.objects.create(
                creator=creator, availability_type=self.avail_booking,
            )
