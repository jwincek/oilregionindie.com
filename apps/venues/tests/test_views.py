"""
Tests for venues app views.

Covers: directory with filters, detail page, setup (multi-venue with Address),
edit with permission checking, and HTMX partial responses.
"""

from django.test import TestCase
from django.urls import reverse

from apps.venues.models import VenueProfile

from .helpers import make_amenity, make_user, make_venue


def venue_form_data(**overrides):
    """Return valid POST data for VenueProfileForm with new field names."""
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
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Directory view
# ---------------------------------------------------------------------------


class VenueDirectoryViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("venues:directory")

        cls.pa_system = make_amenity("PA System")
        cls.stage = make_amenity("Stage")
        cls.parking = make_amenity("Parking")

        # Availability types
        from apps.core.models import AvailabilityType, ProfileAvailability
        cls.avail_accepting = AvailabilityType.objects.create(
            name="Accepting Booking Requests", applies_to="venue", sort_order=1,
        )

        cls.bar = make_venue(
            name="Billy's Bar",
            venue_type=VenueProfile.VenueType.BAR,
            city="Oil City",
            state="PA",
        )
        cls.bar.amenities.add(cls.pa_system, cls.stage)
        ProfileAvailability.objects.create(
            venue=cls.bar, availability_type=cls.avail_accepting,
        )

        cls.gallery = make_venue(
            name="Graffiti Gallery",
            venue_type=VenueProfile.VenueType.GALLERY,
            city="Franklin",
            state="PA",
        )
        cls.gallery.amenities.add(cls.parking)

        cls.cafe = make_venue(
            name="Mosaic Cafe",
            venue_type=VenueProfile.VenueType.CAFE,
            city="Oil City",
            state="PA",
        )

        cls.unpublished = make_venue(
            name="Hidden Venue",
            publish_status="draft",
        )

    def test_directory_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "venues/directory.html")

    def test_excludes_unpublished(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "Hidden Venue")

    def test_shows_published_venues(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Billy")
        self.assertContains(response, "Graffiti Gallery")
        self.assertContains(response, "Mosaic Cafe")

    def test_filter_by_venue_type(self):
        response = self.client.get(self.url, {"type": "bar"})
        self.assertContains(response, "Billy")
        self.assertNotContains(response, "Graffiti Gallery")
        self.assertNotContains(response, "Mosaic Cafe")

    def test_filter_by_gallery_type(self):
        response = self.client.get(self.url, {"type": "gallery"})
        self.assertContains(response, "Graffiti Gallery")
        self.assertNotContains(response, "Billy")

    def test_filter_by_amenity(self):
        response = self.client.get(self.url, {"amenity": "pa-system"})
        self.assertContains(response, "Billy")
        self.assertNotContains(response, "Graffiti Gallery")
        self.assertNotContains(response, "Mosaic Cafe")

    def test_filter_by_location(self):
        response = self.client.get(self.url, {"location": "Franklin"})
        self.assertContains(response, "Graffiti Gallery")
        self.assertNotContains(response, "Billy")

    def test_search_by_name(self):
        response = self.client.get(self.url, {"q": "Mosaic"})
        self.assertContains(response, "Mosaic Cafe")
        self.assertNotContains(response, "Billy")
        self.assertNotContains(response, "Graffiti")

    def test_combined_filters(self):
        response = self.client.get(self.url, {"type": "bar", "location": "Oil City"})
        self.assertContains(response, "Billy")
        self.assertNotContains(response, "Mosaic Cafe")

    def test_filter_by_availability(self):
        response = self.client.get(self.url, {"availability": "accepting-booking-requests"})
        self.assertContains(response, "Billy")
        self.assertNotContains(response, "Graffiti Gallery")
        self.assertNotContains(response, "Mosaic Cafe")

    def test_empty_results(self):
        response = self.client.get(self.url, {"q": "zzzznonexistent"})
        self.assertContains(response, "No venues found")

    def test_htmx_returns_partial(self):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "venues/_venue_list.html")


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------


class VenueDetailViewTest(TestCase):
    def test_published_venue_loads(self):
        venue = make_venue(name="Double Play")
        response = self.client.get(
            reverse("venues:detail", kwargs={"slug": venue.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Double Play")

    def test_unpublished_venue_returns_404(self):
        venue = make_venue(name="Hidden", publish_status="draft")
        response = self.client.get(
            reverse("venues:detail", kwargs={"slug": venue.slug})
        )
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_slug_returns_404(self):
        response = self.client.get(
            reverse("venues:detail", kwargs={"slug": "no-such-venue"})
        )
        self.assertEqual(response.status_code, 404)

    def test_detail_shows_amenities(self):
        venue = make_venue(name="Equipped Venue")
        pa = make_amenity("PA System")
        venue.amenities.add(pa)
        response = self.client.get(
            reverse("venues:detail", kwargs={"slug": venue.slug})
        )
        self.assertContains(response, "PA System")

    def test_detail_shows_venue_type(self):
        venue = make_venue(name="Art Space", venue_type="gallery")
        response = self.client.get(
            reverse("venues:detail", kwargs={"slug": venue.slug})
        )
        self.assertContains(response, "Gallery")

    def test_detail_shows_address(self):
        venue = make_venue(
            name="Located Venue",
            street="789 Center St",
            city="Titusville",
            state="PA",
        )
        response = self.client.get(
            reverse("venues:detail", kwargs={"slug": venue.slug})
        )
        self.assertContains(response, "789 Center St")
        self.assertContains(response, "Titusville")


# ---------------------------------------------------------------------------
# Setup view (requires login, allows multiple venues)
# ---------------------------------------------------------------------------


class VenueSetupViewTest(TestCase):
    def setUp(self):
        self.url = reverse("venues:setup")
        self.user = make_user()

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_loads_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "venues/setup.html")

    def test_creates_venue_on_post(self):
        self.client.force_login(self.user)
        self.client.post(self.url, venue_form_data(name="New Venue"))
        self.assertTrue(VenueProfile.objects.filter(user=self.user, name="New Venue").exists())
        venue = VenueProfile.objects.get(user=self.user, name="New Venue")
        self.assertEqual(venue.slug, "new-venue")

    def test_creates_address_on_post(self):
        """Form should create an Address object linked to the venue."""
        self.client.force_login(self.user)
        self.client.post(self.url, venue_form_data(
            name="Addressed Venue",
            street="100 Main St",
            address_city="Oil City",
            address_state="PA",
            zip_code="16301",
        ))
        venue = VenueProfile.objects.get(name="Addressed Venue")
        self.assertIsNotNone(venue.address)
        self.assertEqual(venue.address.street, "100 Main St")
        self.assertEqual(venue.address.city, "Oil City")

    def test_syncs_legacy_city_state(self):
        """Form should sync city/state onto the venue for query filtering."""
        self.client.force_login(self.user)
        self.client.post(self.url, venue_form_data(
            name="Synced Venue",
            address_city="Franklin",
            address_state="PA",
        ))
        venue = VenueProfile.objects.get(name="Synced Venue")
        self.assertEqual(venue.city, "Franklin")
        self.assertEqual(venue.state, "PA")

    def test_can_create_multiple_venues(self):
        self.client.force_login(self.user)
        for name in ["Venue One", "Venue Two", "Venue Three"]:
            self.client.post(self.url, venue_form_data(name=name))
        self.assertEqual(VenueProfile.objects.filter(user=self.user).count(), 3)

    def test_setup_with_amenities(self):
        pa = make_amenity("PA System")
        stage = make_amenity("Stage")
        self.client.force_login(self.user)
        self.client.post(self.url, venue_form_data(
            name="Equipped Venue",
            amenities=[pa.pk, stage.pk],
        ))
        venue = VenueProfile.objects.get(name="Equipped Venue")
        self.assertEqual(venue.amenities.count(), 2)


# ---------------------------------------------------------------------------
# Edit view (requires login, requires permission)
# ---------------------------------------------------------------------------


class VenueEditViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.venue = make_venue(user=self.owner, name="Editable Venue")
        self.url = reverse("venues:edit", kwargs={"slug": self.venue.slug})

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_loads_for_owner(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "venues/edit.html")

    def test_loads_for_manager(self):
        manager = make_user()
        self.venue.managers.add(manager)
        self.client.force_login(manager)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_forbidden_for_stranger(self):
        stranger = make_user()
        self.client.force_login(stranger)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_updates_venue_on_post(self):
        self.client.force_login(self.owner)
        self.client.post(self.url, venue_form_data(
            name="Renamed Venue",
            venue_type="gallery",
            address_city="Franklin",
            address_state="PA",
        ))
        self.venue.refresh_from_db()
        self.assertEqual(self.venue.name, "Renamed Venue")
        self.assertEqual(self.venue.city, "Franklin")
        self.assertEqual(self.venue.venue_type, "gallery")

    def test_updates_address_on_post(self):
        """Editing should update the existing Address, not create a new one."""
        self.client.force_login(self.owner)
        original_address_pk = self.venue.address.pk
        self.client.post(self.url, venue_form_data(
            name="Editable Venue",
            street="999 New St",
            address_city="Titusville",
            address_state="PA",
        ))
        self.venue.refresh_from_db()
        self.assertEqual(self.venue.address.pk, original_address_pk)
        self.assertEqual(self.venue.address.street, "999 New St")
        self.assertEqual(self.venue.address.city, "Titusville")

    def test_manager_can_update(self):
        manager = make_user()
        self.venue.managers.add(manager)
        self.client.force_login(manager)
        self.client.post(self.url, venue_form_data(name="Manager Updated"))
        self.venue.refresh_from_db()
        self.assertEqual(self.venue.name, "Manager Updated")

    def test_stranger_cannot_update(self):
        stranger = make_user()
        self.client.force_login(stranger)
        response = self.client.post(self.url, venue_form_data(name="Hacked Name"))
        self.assertEqual(response.status_code, 403)
        self.venue.refresh_from_db()
        self.assertNotEqual(self.venue.name, "Hacked Name")
