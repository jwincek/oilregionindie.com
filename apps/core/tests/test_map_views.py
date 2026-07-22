"""
Tests for apps.core.map_views.map_view — the Leaflet/OpenStreetMap
page at /map/.

Branches exercised:
  - No markers anywhere → falls back to the Oil City default centerpoint.
  - Venues with lat/lng appear as venue markers.
  - Creators with lat/lng appear as creator markers.
  - Profiles WITHOUT lat/lng on their address are excluded (the
    address__latitude__isnull=False filter).
  - Centerpoint = average of all marker coordinates when any exist.
"""

import json
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Address
from apps.creators.tests.helpers import make_creator, make_user
from apps.events.models import Event
from apps.events.tests.helpers import make_event
from apps.venues.tests.helpers import make_address, make_venue


def _published_venue_with_coords(lat, lng, **kwargs):
    """Helper: a published venue whose address has real lat/lng."""
    address = make_address()
    address.latitude = Decimal(str(lat))
    address.longitude = Decimal(str(lng))
    address.save()
    venue = make_venue(address=address, **kwargs)
    return venue


def _published_creator_with_coords(lat, lng, **kwargs):
    """Helper: a published creator whose address has real lat/lng."""
    address = Address.objects.create(
        city="Oil City", state="PA",
        latitude=Decimal(str(lat)),
        longitude=Decimal(str(lng)),
    )
    return make_creator(user=make_user(), address=address, **kwargs)


class MapViewTest(TestCase):
    def url(self):
        return reverse("map")

    # ---- empty / default centerpoint ----

    def test_empty_state_uses_oil_city_default_center(self):
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["venue_count"], 0)
        self.assertEqual(r.context["creator_count"], 0)
        # Oil City coordinates as the fallback.
        self.assertAlmostEqual(r.context["center_lat"], 41.434, places=3)
        self.assertAlmostEqual(r.context["center_lng"], -79.7025, places=4)
        self.assertEqual(json.loads(r.context["markers_json"]), [])

    # ---- venues ----

    def test_published_venue_with_coords_appears_as_marker(self):
        _published_venue_with_coords(
            41.4, -79.7, name="Mapped Venue",
            venue_type="bar",
        )
        r = self.client.get(self.url())
        markers = json.loads(r.context["markers_json"])
        self.assertEqual(len(markers), 1)
        m = markers[0]
        self.assertEqual(m["name"], "Mapped Venue")
        self.assertEqual(m["type"], "venue")
        self.assertEqual(m["lat"], 41.4)
        self.assertEqual(m["lng"], -79.7)
        # venue_type is the display form, not the slug.
        self.assertEqual(m["venue_type"], "Bar")

    def test_unpublished_venue_excluded_even_with_coords(self):
        _published_venue_with_coords(
            41.4, -79.7, name="Draft Venue",
            publish_status="draft",
        )
        r = self.client.get(self.url())
        self.assertEqual(r.context["venue_count"], 0)

    def test_venue_without_coordinates_excluded(self):
        """A published venue whose address has no lat/lng doesn't appear
        in the markers list."""
        addr_no_coords = make_address()  # latitude/longitude default to None
        make_venue(address=addr_no_coords, name="Coords-less venue")
        r = self.client.get(self.url())
        self.assertEqual(r.context["venue_count"], 0)
        self.assertEqual(json.loads(r.context["markers_json"]), [])

    # ---- creators ----

    def test_published_creator_with_coords_appears_as_marker(self):
        _published_creator_with_coords(
            41.45, -79.71, display_name="Mapped Creator",
        )
        r = self.client.get(self.url())
        markers = json.loads(r.context["markers_json"])
        self.assertEqual(len(markers), 1)
        m = markers[0]
        self.assertEqual(m["name"], "Mapped Creator")
        self.assertEqual(m["type"], "creator")
        self.assertEqual(m["lat"], 41.45)
        self.assertEqual(m["lng"], -79.71)

    def test_unpublished_creator_excluded(self):
        _published_creator_with_coords(
            41.45, -79.71,
            display_name="Draft Creator",
            publish_status="draft",
        )
        r = self.client.get(self.url())
        self.assertEqual(r.context["creator_count"], 0)

    def test_creator_without_coordinates_excluded(self):
        """A published creator whose address has no lat/lng is excluded
        — the directory still shows them, but they don't pin on the map."""
        no_coord_addr = Address.objects.create(city="Oil City", state="PA")
        make_creator(user=make_user(), address=no_coord_addr,
                     display_name="Address but no coords")
        r = self.client.get(self.url())
        self.assertEqual(r.context["creator_count"], 0)

    # ---- centerpoint math ----

    def test_centerpoint_is_average_of_all_marker_coords(self):
        _published_venue_with_coords(40.0, -80.0)
        _published_creator_with_coords(42.0, -78.0)
        r = self.client.get(self.url())
        # Average of (40, -80) and (42, -78) is (41, -79).
        self.assertEqual(r.context["center_lat"], 41.0)
        self.assertEqual(r.context["center_lng"], -79.0)

    def test_mixed_venues_and_creators_appear_in_markers(self):
        _published_venue_with_coords(41.0, -79.0, name="V")
        _published_creator_with_coords(41.5, -79.5, display_name="C")
        r = self.client.get(self.url())
        self.assertEqual(r.context["venue_count"], 1)
        self.assertEqual(r.context["creator_count"], 1)
        markers = json.loads(r.context["markers_json"])
        types = {m["type"] for m in markers}
        self.assertEqual(types, {"venue", "creator"})

    # ---- marker clustering (dense downtowns like Seneca St would
    # otherwise overlap into indistinguishable pins once zoomed out) ----

    def test_page_includes_clustering_plugin(self):
        _published_venue_with_coords(41.0, -79.0, name="V")
        r = self.client.get(self.url())
        self.assertContains(r, "leaflet.markercluster")
        self.assertContains(r, "markerClusterGroup")

    def test_extra_js_block_is_not_nested_inside_content(self):
        """Regression test for a template bug: extra_js was nested inside
        content, so base.html's own separate extra_js block ALSO rendered
        it — the whole Leaflet + markercluster + init script executed
        twice per page load. The second L.map('map') call threw "Map
        container is already initialized" and broke cluster-click
        interactivity (spiderfying silently failed) even though the
        initial cluster bubble still rendered from the first, working
        execution. Assert the init script appears exactly once."""
        _published_venue_with_coords(41.0, -79.0, name="V")
        r = self.client.get(self.url())
        self.assertEqual(
            r.content.decode().count("var clusters = L.markerClusterGroup"), 1,
        )

    # ---- off-venue events (street fairs, house shows, pop-up crawls) ----

    def _freeform_event(self, lat, lng, **kwargs):
        addr = Address.objects.create(
            city="Oil City", state="PA",
            latitude=Decimal(str(lat)), longitude=Decimal(str(lng)),
        )
        return make_event(location_name=kwargs.pop("location_name", "Seneca Street"),
                          location_address=addr, **kwargs)

    def test_freeform_event_appears_as_event_marker(self):
        self._freeform_event(41.44, -79.71, title="Street Fair")
        r = self.client.get(self.url())
        markers = json.loads(r.context["markers_json"])
        self.assertEqual(len(markers), 1)
        m = markers[0]
        self.assertEqual(m["type"], "event")
        self.assertEqual(m["name"], "Street Fair")
        self.assertEqual(r.context["event_count"], 1)

    def test_venue_hosted_event_does_not_create_duplicate_event_marker(self):
        """Events at a listed venue enrich that venue's own popup instead
        of stacking a second pin exactly on top of it — but they still
        count as upcoming events in the header."""
        venue = _published_venue_with_coords(41.4, -79.7, name="Belize's")
        make_event(title="Friday Show", venue=venue)
        r = self.client.get(self.url())
        markers = json.loads(r.context["markers_json"])
        self.assertEqual(len(markers), 1)  # the venue only, no event pin
        self.assertEqual(markers[0]["type"], "venue")
        self.assertEqual(r.context["event_pin_count"], 0)  # no off-venue pin
        self.assertEqual(r.context["event_count"], 1)  # but the show is counted

    def test_freeform_event_without_address_excluded(self):
        make_event(title="No Address Fair", location_name="Somewhere")
        r = self.client.get(self.url())
        self.assertEqual(r.context["event_count"], 0)

    def test_freeform_event_beyond_window_excluded(self):
        addr = Address.objects.create(
            city="Oil City", state="PA", latitude=Decimal("41.44"), longitude=Decimal("-79.71"),
        )
        make_event(
            title="Far Future Fair", location_name="Seneca St", location_address=addr,
            start_datetime=timezone.now() + timedelta(days=45),
        )
        r = self.client.get(self.url())
        self.assertEqual(r.context["event_count"], 0)

    def test_past_freeform_event_excluded(self):
        addr = Address.objects.create(
            city="Oil City", state="PA", latitude=Decimal("41.44"), longitude=Decimal("-79.71"),
        )
        make_event(
            title="Already Happened", location_name="Seneca St", location_address=addr,
            start_datetime=timezone.now() - timedelta(days=1),
        )
        r = self.client.get(self.url())
        self.assertEqual(r.context["event_count"], 0)

    def test_unpublished_freeform_event_excluded(self):
        self._freeform_event(41.44, -79.71, title="Draft Fair", is_published=False)
        r = self.client.get(self.url())
        self.assertEqual(r.context["event_count"], 0)

    def test_cancelled_freeform_event_still_appears_with_status(self):
        self._freeform_event(41.44, -79.71, title="Rained Out Fair", status=Event.Status.CANCELLED)
        r = self.client.get(self.url())
        markers = json.loads(r.context["markers_json"])
        self.assertEqual(markers[0]["status"], "cancelled")

    # ---- venue popups gain an upcoming-shows list ----

    def test_venue_marker_includes_upcoming_events(self):
        venue = _published_venue_with_coords(41.4, -79.7, name="Belize's")
        make_event(title="Friday Show", venue=venue,
                  start_datetime=timezone.now() + timedelta(days=3))
        r = self.client.get(self.url())
        markers = json.loads(r.context["markers_json"])
        upcoming = markers[0]["upcoming_events"]
        self.assertEqual(len(upcoming), 1)
        self.assertEqual(upcoming[0]["title"], "Friday Show")
        self.assertIn("date", upcoming[0])

    def test_venue_marker_upcoming_events_capped_and_ordered(self):
        venue = _published_venue_with_coords(41.4, -79.7, name="Belize's")
        for i in range(7):
            make_event(title=f"Show {i}", venue=venue,
                      start_datetime=timezone.now() + timedelta(days=i + 1))
        r = self.client.get(self.url())
        markers = json.loads(r.context["markers_json"])
        upcoming = markers[0]["upcoming_events"]
        self.assertEqual(len(upcoming), 5)
        self.assertEqual(upcoming[0]["title"], "Show 0")  # soonest first

    def test_venue_marker_upcoming_events_excludes_past_and_unpublished(self):
        venue = _published_venue_with_coords(41.4, -79.7, name="Belize's")
        make_event(title="Old Show", venue=venue,
                  start_datetime=timezone.now() - timedelta(days=1))
        make_event(title="Draft Show", venue=venue, is_published=False,
                  start_datetime=timezone.now() + timedelta(days=2))
        r = self.client.get(self.url())
        markers = json.loads(r.context["markers_json"])
        self.assertEqual(markers[0]["upcoming_events"], [])

    def test_venue_with_no_upcoming_events_has_empty_list(self):
        _published_venue_with_coords(41.4, -79.7, name="Quiet Venue")
        r = self.client.get(self.url())
        markers = json.loads(r.context["markers_json"])
        self.assertEqual(markers[0]["upcoming_events"], [])

    # ---- popup HTML escaping (names/titles are user-controlled) ----

    def test_page_includes_html_escaping_helper(self):
        r = self.client.get(self.url())
        self.assertContains(r, "escapeHtml")

    # ---- conditional legend / count (empty types are hidden) ----

    def test_creator_count_and_legend_hidden_when_no_creators_mapped(self):
        _published_venue_with_coords(41.4, -79.7, name="V")
        r = self.client.get(self.url())
        self.assertEqual(r.context["creator_count"], 0)
        header = r.content.decode().split("</h1>")[1].split("</p>")[0]
        self.assertNotIn("creator", header)  # count segment omitted
        # Creator legend entry omitted too (the "Creator Directory" button
        # is elsewhere and unaffected).
        self.assertNotIn("shadow-sm\"></span> Creator", r.content.decode())

    def test_creator_count_and_legend_shown_when_a_creator_is_mapped(self):
        _published_venue_with_coords(41.4, -79.7, name="V")
        _published_creator_with_coords(41.45, -79.71, display_name="Mapped Creator")
        r = self.client.get(self.url())
        self.assertEqual(r.context["creator_count"], 1)
        header = r.content.decode().split("</h1>")[1].split("</p>")[0]
        self.assertIn("creator", header)

    def test_offvenue_event_legend_keys_off_pins_not_count(self):
        """A venue-hosted event makes event_count > 0 but adds no off-venue
        pin, so the "not at a listed venue" legend must stay hidden."""
        venue = _published_venue_with_coords(41.4, -79.7, name="Belize's")
        make_event(title="Friday Show", venue=venue)
        r = self.client.get(self.url())
        self.assertEqual(r.context["event_count"], 1)
        self.assertEqual(r.context["event_pin_count"], 0)
        self.assertNotContains(r, "not at a listed venue")
