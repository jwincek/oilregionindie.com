"""
Tests for venues app forms.

Covers: VenueProfileForm validation, required fields, inline Address creation.
"""

from django.test import TestCase

from apps.core.models import Address
from apps.venues.forms import VenueProfileForm

from .helpers import make_amenity, make_user, make_venue


def form_data(**overrides):
    """Return valid form data dict."""
    data = {
        "name": "Test Venue",
        "venue_type": "bar",
        "street": "123 Seneca St",
        "address_city": "Oil City",
        "address_state": "PA",
        "zip_code": "16301",
        "capacity": "",
        "description": "",
        "website": "",
        "is_published": True,
    }
    data.update(overrides)
    return data


class VenueProfileFormTest(TestCase):
    def test_valid_minimal_data(self):
        form = VenueProfileForm(data=form_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_requires_name(self):
        form = VenueProfileForm(data=form_data(name=""))
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_requires_city(self):
        form = VenueProfileForm(data=form_data(address_city=""))
        self.assertFalse(form.is_valid())
        self.assertIn("address_city", form.errors)

    def test_requires_state(self):
        form = VenueProfileForm(data=form_data(address_state=""))
        self.assertFalse(form.is_valid())
        self.assertIn("address_state", form.errors)

    def test_requires_venue_type(self):
        form = VenueProfileForm(data=form_data(venue_type=""))
        self.assertFalse(form.is_valid())
        self.assertIn("venue_type", form.errors)

    def test_invalid_venue_type(self):
        form = VenueProfileForm(data=form_data(venue_type="spaceship"))
        self.assertFalse(form.is_valid())
        self.assertIn("venue_type", form.errors)

    def test_all_venue_types_accepted(self):
        for vtype in ["bar", "cafe", "gallery", "theater", "outdoor", "community_space", "other"]:
            form = VenueProfileForm(data=form_data(venue_type=vtype))
            self.assertTrue(form.is_valid(), f"Failed for venue_type={vtype}: {form.errors}")

    def test_street_optional(self):
        form = VenueProfileForm(data=form_data(street=""))
        self.assertTrue(form.is_valid(), form.errors)

    def test_zip_code_optional(self):
        form = VenueProfileForm(data=form_data(zip_code=""))
        self.assertTrue(form.is_valid(), form.errors)

    def test_capacity_optional(self):
        form = VenueProfileForm(data=form_data(capacity=""))
        self.assertTrue(form.is_valid(), form.errors)

    def test_capacity_accepts_number(self):
        form = VenueProfileForm(data=form_data(capacity="150"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_website_validates_url(self):
        form = VenueProfileForm(data=form_data(website="not-a-url"))
        self.assertFalse(form.is_valid())
        self.assertIn("website", form.errors)

    def test_website_accepts_valid_url(self):
        form = VenueProfileForm(data=form_data(website="https://example.com"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_amenities_optional(self):
        form = VenueProfileForm(data=form_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_amenities_selection(self):
        pa = make_amenity("PA System")
        stage = make_amenity("Stage")
        form = VenueProfileForm(data=form_data(amenities=[pa.pk, stage.pk]))
        self.assertTrue(form.is_valid(), form.errors)

    def test_save_creates_address(self):
        """Saving the form should create an Address object."""
        user = make_user()
        form = VenueProfileForm(data=form_data(
            street="100 Main St",
            address_city="Franklin",
            address_state="PA",
            zip_code="16323",
        ))
        self.assertTrue(form.is_valid(), form.errors)
        venue = form.save(commit=False)
        venue.user = user
        venue = form.save(commit=True)
        self.assertIsNotNone(venue.address)
        self.assertEqual(venue.address.street, "100 Main St")
        self.assertEqual(venue.address.city, "Franklin")
        self.assertEqual(venue.city, "Franklin")

    def test_save_updates_existing_address(self):
        """Editing should update the existing Address, not create a new one."""
        venue = make_venue(name="Existing Venue")
        original_address_pk = venue.address.pk
        form = VenueProfileForm(
            data=form_data(name="Existing Venue", street="999 New St", address_city="Titusville"),
            instance=venue,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        venue.refresh_from_db()
        self.assertEqual(venue.address.pk, original_address_pk)
        self.assertEqual(venue.address.street, "999 New St")

    def test_pre_populates_from_existing_address(self):
        """Form should pre-fill address fields from existing Address FK."""
        venue = make_venue(street="Original St", city="Oil City", state="PA")
        form = VenueProfileForm(instance=venue)
        self.assertEqual(form.fields["street"].initial, "Original St")
        self.assertEqual(form.fields["address_city"].initial, "Oil City")
        self.assertEqual(form.fields["address_state"].initial, "PA")
