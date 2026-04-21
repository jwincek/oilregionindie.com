"""
Tests for events app models.

Covers: Event (slug, can_be_edited_by with all three permission paths,
ticket_price_display, organizer_display, lineup ordering),
EventSlot (multiple slots per creator, venue_area FK, str),
BookingRequest (bidirectional, permissions, recipient_email).
"""

from datetime import time

from django.test import TestCase

from apps.events.models import BookingRequest, Event, EventSlot

from .helpers import (
    make_booking_request,
    make_creator,
    make_event,
    make_event_slot,
    make_past_event,
    make_user,
    make_venue,
    make_venue_area,
    make_venue_contact,
)


# ---------------------------------------------------------------------------
# Event - auto slug
# ---------------------------------------------------------------------------


class EventSlugTest(TestCase):
    def test_auto_generates_slug(self):
        event = make_event(title="Oil Region Indie Fest 2026")
        self.assertEqual(event.slug, "oil-region-indie-fest-2026")

    def test_slug_uniqueness(self):
        e1 = make_event(title="Summer Show")
        e2 = make_event(title="Summer Show")
        self.assertEqual(e1.slug, "summer-show")
        self.assertEqual(e2.slug, "summer-show-1")

    def test_preserves_explicit_slug(self):
        event = make_event(title="Test", slug="custom-event-slug")
        self.assertEqual(event.slug, "custom-event-slug")

    def test_slug_not_overwritten_on_save(self):
        event = make_event(title="Original Title")
        original_slug = event.slug
        event.title = "New Title"
        event.save()
        self.assertEqual(event.slug, original_slug)


# ---------------------------------------------------------------------------
# Event - str / get_absolute_url
# ---------------------------------------------------------------------------


class EventBasicsTest(TestCase):
    def test_str(self):
        event = make_event(title="Petrol Alley Concert")
        self.assertEqual(str(event), "Petrol Alley Concert")

    def test_get_absolute_url(self):
        event = make_event(title="Test Show")
        self.assertEqual(event.get_absolute_url(), "/events/test-show/")


# ---------------------------------------------------------------------------
# Event - ticket_price_display
# ---------------------------------------------------------------------------


class TicketPriceDisplayTest(TestCase):
    def test_free_event(self):
        event = make_event(is_free=True)
        self.assertEqual(event.ticket_price_display, "Free")

    def test_priced_event(self):
        event = make_event(is_free=False, ticket_price_cents=1500)
        self.assertEqual(event.ticket_price_display, "$15.00")

    def test_priced_event_with_cents(self):
        event = make_event(is_free=False, ticket_price_cents=750)
        self.assertEqual(event.ticket_price_display, "$7.50")

    def test_tba_when_not_free_and_no_price(self):
        event = make_event(is_free=False, ticket_price_cents=None)
        self.assertEqual(event.ticket_price_display, "TBA")

    def test_free_overrides_price(self):
        """If is_free is True, price is ignored."""
        event = make_event(is_free=True, ticket_price_cents=2000)
        self.assertEqual(event.ticket_price_display, "Free")


# ---------------------------------------------------------------------------
# Event - organizer_display
# ---------------------------------------------------------------------------


class OrganizerDisplayTest(TestCase):
    def test_no_organizers(self):
        event = make_event()
        self.assertEqual(event.organizer_display, "")

    def test_creator_organizer(self):
        creator = make_creator(display_name="Jerome Wincek")
        event = make_event(organizing_creator=creator)
        self.assertEqual(event.organizer_display, "Jerome Wincek")

    def test_venue_organizer(self):
        venue = make_venue(name="Mid-Town Cafe")
        event = make_event(organizing_venue=venue)
        self.assertEqual(event.organizer_display, "Mid-Town Cafe")

    def test_both_organizers(self):
        creator = make_creator(display_name="The Old Hats")
        venue = make_venue(name="Belize's")
        event = make_event(organizing_creator=creator, organizing_venue=venue)
        self.assertEqual(event.organizer_display, "The Old Hats & Belize's")


# ---------------------------------------------------------------------------
# Event - can_be_edited_by (the most complex permission logic)
# ---------------------------------------------------------------------------


class EventCanBeEditedByTest(TestCase):
    def test_created_by_user_can_edit(self):
        user = make_user()
        event = make_event(created_by=user)
        self.assertTrue(event.can_be_edited_by(user))

    def test_stranger_cannot_edit(self):
        creator_user = make_user()
        stranger = make_user()
        event = make_event(created_by=creator_user)
        self.assertFalse(event.can_be_edited_by(stranger))

    def test_organizing_creator_owner_can_edit(self):
        """The user who owns the organizing creator profile can edit."""
        creator_user = make_user()
        creator = make_creator(user=creator_user, display_name="Organizer")
        other_user = make_user()
        event = make_event(created_by=other_user, organizing_creator=creator)
        self.assertTrue(event.can_be_edited_by(creator_user))

    def test_organizing_creator_manager_can_edit(self):
        """A manager of the organizing creator profile can edit."""
        owner = make_user()
        manager = make_user()
        creator = make_creator(user=owner, display_name="Band")
        creator.managers.add(manager)
        other_user = make_user()
        event = make_event(created_by=other_user, organizing_creator=creator)
        self.assertTrue(event.can_be_edited_by(manager))

    def test_organizing_venue_owner_can_edit(self):
        """The user who owns the organizing venue can edit."""
        venue_user = make_user()
        venue = make_venue(user=venue_user, name="Host Venue")
        other_user = make_user()
        event = make_event(created_by=other_user, organizing_venue=venue)
        self.assertTrue(event.can_be_edited_by(venue_user))

    def test_organizing_venue_manager_can_edit(self):
        """A manager of the organizing venue can edit."""
        owner = make_user()
        manager = make_user()
        venue = make_venue(user=owner, name="Managed Venue")
        venue.managers.add(manager)
        other_user = make_user()
        event = make_event(created_by=other_user, organizing_venue=venue)
        self.assertTrue(event.can_be_edited_by(manager))

    def test_host_venue_owner_cannot_edit_without_organizing_role(self):
        """Owning the host venue doesn't grant edit access unless it's the organizer."""
        venue_user = make_user()
        venue = make_venue(user=venue_user, name="Host Only")
        other_user = make_user()
        event = make_event(
            created_by=other_user,
            venue=venue,  # host venue, not organizing venue
            organizing_venue=None,
        )
        self.assertFalse(event.can_be_edited_by(venue_user))

    def test_unrelated_creator_cannot_edit(self):
        """A creator on the lineup but not the organizer cannot edit."""
        organizer_user = make_user()
        performer_user = make_user()
        performer = make_creator(user=performer_user, display_name="Performer")
        event = make_event(created_by=organizer_user)
        make_event_slot(event, performer)
        self.assertFalse(event.can_be_edited_by(performer_user))

    def test_all_three_paths_combined(self):
        """An event with all three organizer types set — each can edit."""
        user_a = make_user()
        user_b = make_user()
        user_c = make_user()
        stranger = make_user()
        creator = make_creator(user=user_b, display_name="Co-organizer")
        venue = make_venue(user=user_c, name="Co-host")
        event = make_event(
            created_by=user_a,
            organizing_creator=creator,
            organizing_venue=venue,
        )
        self.assertTrue(event.can_be_edited_by(user_a))
        self.assertTrue(event.can_be_edited_by(user_b))
        self.assertTrue(event.can_be_edited_by(user_c))
        self.assertFalse(event.can_be_edited_by(stranger))


# ---------------------------------------------------------------------------
# EventSlot
# ---------------------------------------------------------------------------


class EventSlotTest(TestCase):
    def test_str_without_description(self):
        creator = make_creator(display_name="Alice")
        event = make_event(title="Friday Show")
        slot = make_event_slot(event, creator)
        self.assertEqual(str(slot), "Alice at Friday Show")

    def test_str_with_description(self):
        creator = make_creator(display_name="Alice")
        event = make_event(title="Friday Show")
        slot = make_event_slot(event, creator, set_description="Acoustic Set")
        self.assertEqual(str(slot), "Alice at Friday Show — Acoustic Set")

    def test_multiple_slots_per_creator(self):
        """A creator can have multiple slots at the same event."""
        creator = make_creator(display_name="Multi-set Artist")
        event = make_event(title="All Day Fest")
        slot_1 = make_event_slot(
            event, creator,
            start_time=time(14, 0),
            set_description="Acoustic Set",
            sort_order=1,
        )
        slot_2 = make_event_slot(
            event, creator,
            start_time=time(21, 0),
            set_description="Electric Set",
            sort_order=5,
        )
        self.assertEqual(event.slots.filter(creator=creator).count(), 2)

    def test_slot_with_venue_area(self):
        venue = make_venue(name="Multi-Stage Venue")
        area = make_venue_area(venue, name="Main Stage")
        creator = make_creator(display_name="Headliner")
        event = make_event(title="Big Show", venue=venue)
        slot = make_event_slot(event, creator, venue_area=area)
        self.assertEqual(slot.venue_area.name, "Main Stage")

    def test_slot_without_venue_area(self):
        creator = make_creator(display_name="Solo Artist")
        event = make_event(title="Simple Show")
        slot = make_event_slot(event, creator)
        self.assertIsNone(slot.venue_area)

    def test_default_status_is_pending(self):
        creator = make_creator()
        event = make_event()
        slot = EventSlot.objects.create(event=event, creator=creator)
        self.assertEqual(slot.status, EventSlot.Status.PENDING)

    def test_lineup_ordering(self):
        """Lineup should be ordered by sort_order then start_time."""
        creator_a = make_creator(display_name="Opener")
        creator_b = make_creator(display_name="Headliner")
        creator_c = make_creator(display_name="Middle Act")
        event = make_event(title="Ordered Show")
        make_event_slot(event, creator_b, sort_order=3, start_time=time(21, 0))
        make_event_slot(event, creator_a, sort_order=1, start_time=time(18, 0))
        make_event_slot(event, creator_c, sort_order=2, start_time=time(19, 30))
        lineup = list(event.lineup)
        self.assertEqual(lineup[0].creator.display_name, "Opener")
        self.assertEqual(lineup[1].creator.display_name, "Middle Act")
        self.assertEqual(lineup[2].creator.display_name, "Headliner")

    def test_cascade_delete_with_event(self):
        creator = make_creator()
        event = make_event()
        make_event_slot(event, creator)
        event_pk = event.pk
        event.delete()
        self.assertEqual(EventSlot.objects.filter(event_id=event_pk).count(), 0)


# ---------------------------------------------------------------------------
# BookingRequest
# ---------------------------------------------------------------------------


class BookingRequestBasicsTest(TestCase):
    def test_str_creator_to_venue(self):
        creator = make_creator(display_name="Alice")
        venue = make_venue(name="Belize's")
        req = make_booking_request(creator, venue)
        self.assertEqual(str(req), "Alice → Belize's (Pending)")

    def test_str_venue_to_creator(self):
        creator = make_creator(display_name="Alice")
        venue = make_venue(name="Belize's")
        req = make_booking_request(
            creator, venue,
            direction=BookingRequest.Direction.VENUE_TO_CREATOR,
        )
        self.assertEqual(str(req), "Alice ← Belize's (Pending)")

    def test_is_creator_initiated(self):
        creator = make_creator()
        venue = make_venue()
        req = make_booking_request(creator, venue)
        self.assertTrue(req.is_creator_initiated)
        self.assertFalse(req.is_venue_initiated)

    def test_is_venue_initiated(self):
        creator = make_creator()
        venue = make_venue()
        req = make_booking_request(
            creator, venue,
            direction=BookingRequest.Direction.VENUE_TO_CREATOR,
        )
        self.assertTrue(req.is_venue_initiated)
        self.assertFalse(req.is_creator_initiated)

    def test_default_status_is_pending(self):
        creator = make_creator()
        venue = make_venue()
        req = make_booking_request(creator, venue)
        self.assertEqual(req.status, BookingRequest.Status.PENDING)


class BookingRequestRecipientEmailTest(TestCase):
    def test_creator_initiated_sends_to_venue_booking_email(self):
        from apps.venues.models import VenueContact
        creator = make_creator()
        venue = make_venue()
        make_venue_contact(
            venue,
            contact_type=VenueContact.ContactType.BOOKING,
            method=VenueContact.Method.EMAIL,
            value="booking@billys.com",
        )
        req = make_booking_request(creator, venue)
        self.assertEqual(req.recipient_email, "booking@billys.com")

    def test_creator_initiated_falls_back_to_owner_email(self):
        creator = make_creator()
        venue_user = make_user()
        venue = make_venue(user=venue_user)
        req = make_booking_request(creator, venue)
        self.assertEqual(req.recipient_email, venue_user.email)

    def test_venue_initiated_sends_to_creator_email(self):
        creator_user = make_user()
        creator = make_creator(user=creator_user)
        venue = make_venue()
        req = make_booking_request(
            creator, venue,
            direction=BookingRequest.Direction.VENUE_TO_CREATOR,
        )
        self.assertEqual(req.recipient_email, creator_user.email)


class BookingRequestPermissionsTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user, display_name="Performer")
        self.venue = make_venue(user=self.venue_user, name="The Venue")

    def test_initiator_can_view(self):
        req = make_booking_request(self.creator, self.venue)
        self.assertTrue(req.can_be_viewed_by(self.creator_user))

    def test_receiver_can_view(self):
        req = make_booking_request(self.creator, self.venue)
        self.assertTrue(req.can_be_viewed_by(self.venue_user))

    def test_stranger_cannot_view(self):
        stranger = make_user()
        req = make_booking_request(self.creator, self.venue)
        self.assertFalse(req.can_be_viewed_by(stranger))

    def test_creator_manager_can_view(self):
        manager = make_user()
        self.creator.managers.add(manager)
        req = make_booking_request(self.creator, self.venue)
        self.assertTrue(req.can_be_viewed_by(manager))

    def test_venue_manager_can_view(self):
        manager = make_user()
        self.venue.managers.add(manager)
        req = make_booking_request(self.creator, self.venue)
        self.assertTrue(req.can_be_viewed_by(manager))

    # --- can_be_responded_to_by ---

    def test_venue_can_respond_to_creator_request(self):
        req = make_booking_request(self.creator, self.venue)
        self.assertTrue(req.can_be_responded_to_by(self.venue_user))

    def test_creator_cannot_respond_to_own_request(self):
        req = make_booking_request(self.creator, self.venue)
        self.assertFalse(req.can_be_responded_to_by(self.creator_user))

    def test_creator_can_respond_to_venue_request(self):
        req = make_booking_request(
            self.creator, self.venue,
            direction=BookingRequest.Direction.VENUE_TO_CREATOR,
        )
        self.assertTrue(req.can_be_responded_to_by(self.creator_user))

    def test_venue_cannot_respond_to_own_request(self):
        req = make_booking_request(
            self.creator, self.venue,
            direction=BookingRequest.Direction.VENUE_TO_CREATOR,
        )
        self.assertFalse(req.can_be_responded_to_by(self.venue_user))

    def test_stranger_cannot_respond(self):
        stranger = make_user()
        req = make_booking_request(self.creator, self.venue)
        self.assertFalse(req.can_be_responded_to_by(stranger))

    def test_venue_manager_can_respond_to_creator_request(self):
        manager = make_user()
        self.venue.managers.add(manager)
        req = make_booking_request(self.creator, self.venue)
        self.assertTrue(req.can_be_responded_to_by(manager))

    def test_creator_manager_can_respond_to_venue_request(self):
        manager = make_user()
        self.creator.managers.add(manager)
        req = make_booking_request(
            self.creator, self.venue,
            direction=BookingRequest.Direction.VENUE_TO_CREATOR,
        )
        self.assertTrue(req.can_be_responded_to_by(manager))


class BookingRequestResultingEventTest(TestCase):
    def test_link_to_resulting_event(self):
        creator = make_creator()
        venue = make_venue()
        req = make_booking_request(creator, venue)
        event = make_event(title="Booked Show", venue=venue)
        req.resulting_event = event
        req.status = BookingRequest.Status.ACCEPTED
        req.save()
        req.refresh_from_db()
        self.assertEqual(req.resulting_event, event)
        self.assertEqual(req.status, BookingRequest.Status.ACCEPTED)

    def test_resulting_event_nullable(self):
        creator = make_creator()
        venue = make_venue()
        req = make_booking_request(creator, venue)
        self.assertIsNone(req.resulting_event)
