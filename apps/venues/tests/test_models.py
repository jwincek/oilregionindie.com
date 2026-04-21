"""
Tests for venues app models.

Covers: Amenity, VenueProfile (slug, permissions, properties),
VenueContact (multiple contacts, booking_email fallback),
VenueArea (uniqueness), and VenueSocialLink.
"""

from django.db import IntegrityError
from django.test import TestCase

from apps.venues.models import Amenity, VenueArea, VenueContact, VenueProfile

from .helpers import (
    make_amenity,
    make_user,
    make_venue,
    make_venue_area,
    make_venue_contact,
    make_venue_social_link,
)


# ---------------------------------------------------------------------------
# Amenity
# ---------------------------------------------------------------------------


class AmenityModelTest(TestCase):
    def test_auto_slug(self):
        a = Amenity(name="PA System")
        a.save()
        self.assertEqual(a.slug, "pa-system")

    def test_preserves_explicit_slug(self):
        a = Amenity(name="PA System", slug="custom")
        a.save()
        self.assertEqual(a.slug, "custom")

    def test_str(self):
        a = make_amenity("Green Room")
        self.assertEqual(str(a), "Green Room")

    def test_unique_name(self):
        make_amenity("Stage")
        with self.assertRaises(IntegrityError):
            Amenity.objects.create(name="Stage")


# ---------------------------------------------------------------------------
# VenueProfile - auto slug
# ---------------------------------------------------------------------------


class VenueSlugTest(TestCase):
    def test_auto_generates_slug(self):
        venue = make_venue(name="Mid-Town Cafe")
        self.assertEqual(venue.slug, "mid-town-cafe")

    def test_slug_uniqueness(self):
        v1 = make_venue(name="Belize's")
        v2 = make_venue(name="Belize's")
        self.assertEqual(v1.slug, "belizes")
        self.assertEqual(v2.slug, "belizes-1")

    def test_third_duplicate_slug(self):
        make_venue(name="The Nickel")
        make_venue(name="The Nickel")
        v3 = make_venue(name="The Nickel")
        self.assertEqual(v3.slug, "the-nickel-2")

    def test_preserves_explicit_slug(self):
        venue = make_venue(name="Test", slug="my-slug")
        self.assertEqual(venue.slug, "my-slug")

    def test_slug_not_overwritten_on_save(self):
        venue = make_venue(name="Original")
        original_slug = venue.slug
        venue.name = "Renamed"
        venue.save()
        self.assertEqual(venue.slug, original_slug)


# ---------------------------------------------------------------------------
# VenueProfile - get_absolute_url
# ---------------------------------------------------------------------------


class VenueAbsoluteUrlTest(TestCase):
    def test_url_uses_slug(self):
        venue = make_venue(name="Petrol Alley")
        self.assertEqual(venue.get_absolute_url(), "/venues/petrol-alley/")


# ---------------------------------------------------------------------------
# VenueProfile - str
# ---------------------------------------------------------------------------


class VenueStrTest(TestCase):
    def test_str_is_name(self):
        venue = make_venue(name="McNerny's")
        self.assertEqual(str(venue), "McNerny's")


# ---------------------------------------------------------------------------
# VenueProfile - full_address
# ---------------------------------------------------------------------------


class FullAddressTest(TestCase):
    def test_full_address_with_all_parts(self):
        venue = make_venue(
            street="123 Seneca St",
            city="Oil City",
            state="PA",
            zip_code="16301",
        )
        self.assertEqual(venue.full_address, "123 Seneca St, Oil City, PA, 16301")

    def test_full_address_without_zip(self):
        venue = make_venue(
            street="456 Main St",
            city="Franklin",
            state="PA",
            zip_code="",
        )
        self.assertEqual(venue.full_address, "456 Main St, Franklin, PA")

    def test_full_address_without_street(self):
        venue = make_venue(
            street="",
            city="Titusville",
            state="PA",
            zip_code="16354",
        )
        self.assertEqual(venue.full_address, "Titusville, PA, 16354")

    def test_full_address_fallback_without_address_object(self):
        """If no Address FK, fall back to city/state."""
        user = make_user()
        venue = VenueProfile.objects.create(
            user=user, name="No Address Venue", city="Cranberry", state="PA",
            venue_type=VenueProfile.VenueType.BAR, publish_status="published",
        )
        self.assertEqual(venue.full_address, "Cranberry, PA")


# ---------------------------------------------------------------------------
# VenueProfile - amenity_list
# ---------------------------------------------------------------------------


class AmenityListTest(TestCase):
    def test_amenity_list(self):
        venue = make_venue()
        a1 = make_amenity("PA System")
        a2 = make_amenity("Stage")
        venue.amenities.add(a1, a2)
        # Ordering is alphabetical by name
        self.assertEqual(venue.amenity_list, "PA System, Stage")

    def test_empty_amenity_list(self):
        venue = make_venue()
        self.assertEqual(venue.amenity_list, "")


# ---------------------------------------------------------------------------
# VenueProfile - can_be_edited_by
# ---------------------------------------------------------------------------


class VenueCanBeEditedByTest(TestCase):
    def test_owner_can_edit(self):
        user = make_user()
        venue = make_venue(user=user)
        self.assertTrue(venue.can_be_edited_by(user))

    def test_manager_can_edit(self):
        owner = make_user()
        manager = make_user()
        venue = make_venue(user=owner)
        venue.managers.add(manager)
        self.assertTrue(venue.can_be_edited_by(manager))

    def test_stranger_cannot_edit(self):
        owner = make_user()
        stranger = make_user()
        venue = make_venue(user=owner)
        self.assertFalse(venue.can_be_edited_by(stranger))

    def test_manager_of_different_venue_cannot_edit(self):
        owner_a = make_user()
        owner_b = make_user()
        manager = make_user()
        venue_a = make_venue(user=owner_a, name="Venue A")
        venue_b = make_venue(user=owner_b, name="Venue B")
        venue_a.managers.add(manager)
        self.assertTrue(venue_a.can_be_edited_by(manager))
        self.assertFalse(venue_b.can_be_edited_by(manager))


# ---------------------------------------------------------------------------
# VenueProfile - multiple venues per user
# ---------------------------------------------------------------------------


class MultipleVenuesPerUserTest(TestCase):
    def test_user_can_own_multiple_venues(self):
        user = make_user()
        v1 = make_venue(user=user, name="Venue One")
        v2 = make_venue(user=user, name="Venue Two")
        venues = VenueProfile.objects.filter(user=user)
        self.assertEqual(venues.count(), 2)

    def test_each_venue_has_own_slug(self):
        user = make_user()
        v1 = make_venue(user=user, name="Shared Name")
        v2 = make_venue(user=user, name="Shared Name")
        self.assertNotEqual(v1.slug, v2.slug)


# ---------------------------------------------------------------------------
# VenueSocialLink
# ---------------------------------------------------------------------------


class VenueSocialLinkTest(TestCase):
    def test_str(self):
        venue = make_venue(name="The Shamrock")
        link = make_venue_social_link(venue)
        self.assertIn("Facebook", str(link))
        self.assertIn("The Shamrock", str(link))


# ---------------------------------------------------------------------------
# VenueArea
# ---------------------------------------------------------------------------


class VenueAreaTest(TestCase):
    def test_create_area(self):
        venue = make_venue(name="The National Transit Building")
        area = make_venue_area(venue, name="Main Stage", capacity=200)
        self.assertEqual(str(area), "Main Stage (The National Transit Building)")

    def test_unique_name_per_venue(self):
        venue = make_venue()
        make_venue_area(venue, name="Main Stage")
        with self.assertRaises(IntegrityError):
            VenueArea.objects.create(venue=venue, name="Main Stage")

    def test_same_name_different_venues(self):
        """Two venues can both have a 'Main Stage'."""
        v1 = make_venue(name="Venue One")
        v2 = make_venue(name="Venue Two")
        a1 = make_venue_area(v1, name="Main Stage")
        a2 = make_venue_area(v2, name="Main Stage")
        self.assertNotEqual(a1.pk, a2.pk)

    def test_areas_ordered_by_sort_order(self):
        venue = make_venue()
        a2 = make_venue_area(venue, name="Patio", sort_order=2)
        a1 = make_venue_area(venue, name="Main Stage", sort_order=1)
        a3 = make_venue_area(venue, name="Gallery", sort_order=3)
        areas = list(venue.areas.all())
        self.assertEqual(areas[0].name, "Main Stage")
        self.assertEqual(areas[1].name, "Patio")
        self.assertEqual(areas[2].name, "Gallery")

    def test_cascade_delete_with_venue(self):
        venue = make_venue()
        make_venue_area(venue, name="Stage")
        venue_pk = venue.pk
        venue.delete()
        self.assertEqual(VenueArea.objects.filter(venue_id=venue_pk).count(), 0)


# ---------------------------------------------------------------------------
# VenueContact
# ---------------------------------------------------------------------------


class VenueContactTest(TestCase):
    def test_str(self):
        venue = make_venue(name="Belize's")
        contact = make_venue_contact(venue, name="Joe")
        self.assertIn("Booking", str(contact))
        self.assertIn("Email", str(contact))
        self.assertIn("Joe", str(contact))

    def test_str_without_name(self):
        venue = make_venue()
        contact = make_venue_contact(venue)
        self.assertIn("Booking", str(contact))
        self.assertNotIn("()", str(contact))

    def test_multiple_contacts_per_venue(self):
        venue = make_venue()
        make_venue_contact(venue, contact_type=VenueContact.ContactType.BOOKING,
                           method=VenueContact.Method.EMAIL, value="book@example.com")
        make_venue_contact(venue, contact_type=VenueContact.ContactType.BOOKING,
                           method=VenueContact.Method.PHONE, value="814-555-0100")
        make_venue_contact(venue, contact_type=VenueContact.ContactType.GENERAL,
                           method=VenueContact.Method.EMAIL, value="info@example.com")
        self.assertEqual(venue.contacts.count(), 3)

    def test_multiple_methods_for_same_type(self):
        """A venue can have both email AND phone for booking."""
        venue = make_venue()
        email = make_venue_contact(venue, contact_type=VenueContact.ContactType.BOOKING,
                                   method=VenueContact.Method.EMAIL, value="book@example.com")
        phone = make_venue_contact(venue, contact_type=VenueContact.ContactType.BOOKING,
                                   method=VenueContact.Method.PHONE, value="814-555-0100")
        booking_contacts = venue.contacts.filter(contact_type=VenueContact.ContactType.BOOKING)
        self.assertEqual(booking_contacts.count(), 2)

    def test_public_contacts_filter(self):
        venue = make_venue()
        make_venue_contact(venue, is_public=True, value="public@example.com")
        make_venue_contact(venue, is_public=False, value="private@example.com")
        public = list(venue.public_contacts)
        self.assertEqual(len(public), 1)
        self.assertEqual(public[0].value, "public@example.com")

    def test_display_value_email(self):
        venue = make_venue()
        contact = make_venue_contact(venue, method=VenueContact.Method.EMAIL, value="test@example.com")
        self.assertEqual(contact.display_value, "test@example.com")

    def test_display_value_form(self):
        venue = make_venue()
        contact = make_venue_contact(venue, method=VenueContact.Method.FORM, value="https://example.com/contact")
        self.assertEqual(contact.display_value, "Contact Form")

    def test_cascade_delete_with_venue(self):
        venue = make_venue()
        make_venue_contact(venue)
        venue_pk = venue.pk
        venue.delete()
        self.assertEqual(VenueContact.objects.filter(venue_id=venue_pk).count(), 0)


# ---------------------------------------------------------------------------
# VenueProfile - booking_email property
# ---------------------------------------------------------------------------


class BookingEmailTest(TestCase):
    def test_returns_booking_contact_email(self):
        user = make_user()
        venue = make_venue(user=user)
        make_venue_contact(venue, contact_type=VenueContact.ContactType.BOOKING,
                           method=VenueContact.Method.EMAIL, value="booking@venue.com")
        self.assertEqual(venue.booking_email, "booking@venue.com")

    def test_falls_back_to_owner_email(self):
        user = make_user()
        venue = make_venue(user=user)
        # No contacts at all
        self.assertEqual(venue.booking_email, user.email)

    def test_ignores_non_email_booking_contacts(self):
        user = make_user()
        venue = make_venue(user=user)
        make_venue_contact(venue, contact_type=VenueContact.ContactType.BOOKING,
                           method=VenueContact.Method.PHONE, value="814-555-0100")
        # Phone booking contact exists but should not be returned as email
        self.assertEqual(venue.booking_email, user.email)

    def test_ignores_private_booking_contacts(self):
        user = make_user()
        venue = make_venue(user=user)
        make_venue_contact(venue, contact_type=VenueContact.ContactType.BOOKING,
                           method=VenueContact.Method.EMAIL, value="private@venue.com",
                           is_public=False)
        self.assertEqual(venue.booking_email, user.email)

    def test_ignores_non_booking_email_contacts(self):
        user = make_user()
        venue = make_venue(user=user)
        make_venue_contact(venue, contact_type=VenueContact.ContactType.GENERAL,
                           method=VenueContact.Method.EMAIL, value="info@venue.com")
        self.assertEqual(venue.booking_email, user.email)
