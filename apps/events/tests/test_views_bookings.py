"""
Tests for booking-related views in apps.events.views.

Covers: booking_inbox, booking_detail, booking_respond, booking_withdraw,
booking_create (both directions), create_from_booking, and booking_feedback.
The shared invariants exercised across these views are the booking's
can_be_viewed_by / can_be_responded_to_by gates and the
notify_booking_status_changed side effect on state transitions.
"""

import uuid
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.events.models import BookingRequest, Event, EventSlot

from .helpers import (
    make_booking_request,
    make_creator,
    make_event,
    make_user,
    make_venue,
)


# ---------------------------------------------------------------------------
# booking_inbox
# ---------------------------------------------------------------------------


class BookingInboxTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.venue = make_venue(user=self.venue_user)
        # An incoming pending request for the venue (creator initiated)
        self.received = make_booking_request(
            creator=self.creator, venue=self.venue,
            direction=BookingRequest.Direction.CREATOR_TO_VENUE,
        )

    def url(self):
        return reverse("events:booking_inbox")

    def test_login_required(self):
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 302)

    def test_user_with_no_profiles_sees_empty_inbox(self):
        """A signed-in user who has neither a creator nor a venue profile
        gets a clean empty inbox (rather than a crash)."""
        rando = make_user()
        self.client.force_login(rando)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["total_count"], 0)

    def test_venue_owner_sees_received_pending(self):
        self.client.force_login(self.venue_user)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertIn(self.received, r.context["received_pending"])
        self.assertEqual(r.context["sent_pending"], [])

    def test_creator_sees_their_request_in_sent_pending(self):
        """The same request, viewed from the creator side, lands in
        sent_pending — they initiated it, so they can't respond."""
        self.client.force_login(self.creator_user)
        r = self.client.get(self.url())
        self.assertIn(self.received, r.context["sent_pending"])
        self.assertEqual(r.context["received_pending"], [])

    def test_resolved_bucket_holds_non_pending(self):
        self.received.status = BookingRequest.Status.ACCEPTED
        self.received.save()
        self.client.force_login(self.venue_user)
        r = self.client.get(self.url())
        self.assertEqual(r.context["received_pending"], [])
        self.assertIn(self.received, r.context["resolved"])

    def test_search_filters_by_message_creator_or_venue(self):
        booking_special = make_booking_request(
            creator=self.creator, venue=self.venue,
            message="A very unique phrase nobody else will type",
        )
        self.client.force_login(self.venue_user)
        r = self.client.get(self.url(), {"q": "unique phrase"})
        bookings = (r.context["received_pending"] + r.context["sent_pending"]
                    + r.context["resolved"])
        self.assertIn(booking_special, bookings)
        self.assertNotIn(self.received, bookings)

    def test_status_filter_narrows_results(self):
        accepted = make_booking_request(
            creator=self.creator, venue=self.venue,
            status=BookingRequest.Status.ACCEPTED,
        )
        self.client.force_login(self.venue_user)
        r = self.client.get(self.url(), {"status": "accepted"})
        all_visible = (r.context["received_pending"] + r.context["sent_pending"]
                       + r.context["resolved"])
        self.assertIn(accepted, all_visible)
        self.assertNotIn(self.received, all_visible)


# ---------------------------------------------------------------------------
# booking_detail
# ---------------------------------------------------------------------------


class BookingDetailTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.venue = make_venue(user=self.venue_user)
        self.booking = make_booking_request(
            creator=self.creator, venue=self.venue,
            direction=BookingRequest.Direction.CREATOR_TO_VENUE,
        )

    def url(self, pk=None):
        return reverse("events:booking_detail",
                       kwargs={"pk": pk or self.booking.pk})

    def test_login_required(self):
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 302)

    def test_unrelated_user_gets_404(self):
        """can_be_viewed_by guards detail — strangers raise Http404
        (not 403, intentionally — don't reveal that a booking exists)."""
        self.client.force_login(make_user())
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 404)

    def test_venue_owner_can_respond_to_creator_initiated_request(self):
        """The receiving party sees can_respond=True and gets a form."""
        self.client.force_login(self.venue_user)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["can_respond"])
        self.assertIsNotNone(r.context["response_form"])

    def test_initiator_cannot_respond_to_their_own_request(self):
        self.client.force_login(self.creator_user)
        r = self.client.get(self.url())
        self.assertFalse(r.context["can_respond"])
        self.assertIsNone(r.context["response_form"])

    def test_feedback_form_only_after_acceptance(self):
        self.client.force_login(self.creator_user)
        r = self.client.get(self.url())
        self.assertFalse(r.context["can_leave_feedback"])
        self.assertIsNone(r.context["feedback_form"])
        self.booking.status = BookingRequest.Status.ACCEPTED
        self.booking.save()
        r = self.client.get(self.url())
        self.assertTrue(r.context["can_leave_feedback"])
        self.assertIsNotNone(r.context["feedback_form"])

    def test_existing_feedback_appears_in_context(self):
        from apps.events.models import BookingFeedback
        self.booking.status = BookingRequest.Status.ACCEPTED
        self.booking.save()
        mine = BookingFeedback.objects.create(
            booking=self.booking, author=self.creator_user,
            body="Was great", would_work_again=True,
        )
        theirs = BookingFeedback.objects.create(
            booking=self.booking, author=self.venue_user,
            body="Loved them", would_work_again=True,
        )
        self.client.force_login(self.creator_user)
        r = self.client.get(self.url())
        self.assertEqual(r.context["my_feedback"], mine)
        self.assertEqual(r.context["other_feedback"], theirs)
        # Already left feedback → no more feedback form.
        self.assertFalse(r.context["can_leave_feedback"])


# ---------------------------------------------------------------------------
# booking_respond
# ---------------------------------------------------------------------------


@mock.patch("apps.events.views.notify_booking_status_changed")
class BookingRespondTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.venue = make_venue(user=self.venue_user)
        self.booking = make_booking_request(
            creator=self.creator, venue=self.venue,
            direction=BookingRequest.Direction.CREATOR_TO_VENUE,
        )

    def url(self):
        return reverse("events:booking_respond", kwargs={"pk": self.booking.pk})

    def test_get_not_allowed(self, _mock_notify):
        self.client.force_login(self.venue_user)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 405)

    def test_initiator_cannot_accept_or_decline(self, _mock_notify):
        self.client.force_login(self.creator_user)
        r = self.client.post(self.url(), {"action": "accept"})
        self.assertEqual(r.status_code, 403)

    def test_accept_transitions_status_and_notifies(self, mock_notify):
        self.client.force_login(self.venue_user)
        r = self.client.post(self.url(), {
            "action": "accept",
            "response_message": "See you Friday",
        })
        self.assertRedirects(r, reverse(
            "events:booking_detail", kwargs={"pk": self.booking.pk}
        ))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.ACCEPTED)
        self.assertEqual(self.booking.response_message, "See you Friday")
        self.assertIsNotNone(self.booking.responded_at)
        mock_notify.assert_called_once_with(self.booking)

    def test_decline_transitions_status_and_notifies(self, mock_notify):
        self.client.force_login(self.venue_user)
        r = self.client.post(self.url(), {"action": "decline"})
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.DECLINED)
        mock_notify.assert_called_once_with(self.booking)

    def test_cannot_respond_to_non_pending_booking(self, mock_notify):
        self.booking.status = BookingRequest.Status.ACCEPTED
        self.booking.save()
        self.client.force_login(self.venue_user)
        r = self.client.post(self.url(), {"action": "accept"})
        self.assertEqual(r.status_code, 403)
        mock_notify.assert_not_called()


# ---------------------------------------------------------------------------
# booking_withdraw
# ---------------------------------------------------------------------------


class BookingWithdrawTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.venue = make_venue(user=self.venue_user)
        self.booking = make_booking_request(
            creator=self.creator, venue=self.venue,
            direction=BookingRequest.Direction.CREATOR_TO_VENUE,
        )

    def url(self):
        return reverse("events:booking_withdraw", kwargs={"pk": self.booking.pk})

    def test_only_initiator_can_withdraw(self):
        self.client.force_login(self.venue_user)  # receiver, not initiator
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 403)

    def test_initiator_withdraws_pending_request(self):
        self.client.force_login(self.creator_user)
        r = self.client.post(self.url())
        self.assertRedirects(r, reverse("events:booking_inbox"))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingRequest.Status.WITHDRAWN)

    def test_cannot_withdraw_non_pending_request(self):
        self.booking.status = BookingRequest.Status.ACCEPTED
        self.booking.save()
        self.client.force_login(self.creator_user)
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 403)


# ---------------------------------------------------------------------------
# booking_create
# ---------------------------------------------------------------------------


@mock.patch("apps.events.views.notify_booking_status_changed")
class BookingCreateTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.venue = make_venue(user=self.venue_user)

    def test_unknown_direction_404s(self, _mock_notify):
        self.client.force_login(self.creator_user)
        r = self.client.get(reverse(
            "events:booking_create",
            kwargs={"direction": "sideways", "profile_slug": self.venue.slug},
        ))
        self.assertEqual(r.status_code, 404)

    def test_to_venue_without_creator_profile_redirects_to_setup(self, _m):
        rando = make_user()
        self.client.force_login(rando)
        r = self.client.get(reverse(
            "events:booking_create",
            kwargs={"direction": "to-venue", "profile_slug": self.venue.slug},
        ))
        self.assertRedirects(r, reverse("creators:setup"),
                             fetch_redirect_response=False)

    def test_to_venue_get_renders_form(self, _m):
        self.client.force_login(self.creator_user)
        r = self.client.get(reverse(
            "events:booking_create",
            kwargs={"direction": "to-venue", "profile_slug": self.venue.slug},
        ))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["target_name"], self.venue.name)

    def test_to_venue_post_creates_booking_with_correct_direction(self, mock_notify):
        self.client.force_login(self.creator_user)
        r = self.client.post(reverse(
            "events:booking_create",
            kwargs={"direction": "to-venue", "profile_slug": self.venue.slug},
        ), {
            "event_type": Event.EventType.CONCERT,
            "preferred_dates": "Any Friday in August",
            "message": "We'd love to play your venue.",
        })
        booking = BookingRequest.objects.get(creator=self.creator, venue=self.venue)
        self.assertEqual(booking.direction,
                         BookingRequest.Direction.CREATOR_TO_VENUE)
        self.assertEqual(booking.initiated_by, self.creator_user)
        self.assertRedirects(r, reverse("events:booking_inbox"))
        mock_notify.assert_called_once_with(booking)

    def test_to_creator_without_venue_profile_redirects_to_setup(self, _m):
        rando = make_user()
        self.client.force_login(rando)
        r = self.client.get(reverse(
            "events:booking_create",
            kwargs={"direction": "to-creator",
                    "profile_slug": self.creator.slug},
        ))
        self.assertRedirects(r, reverse("venues:setup"),
                             fetch_redirect_response=False)

    def test_to_creator_get_renders_form_with_user_venues(self, _m):
        self.client.force_login(self.venue_user)
        r = self.client.get(reverse(
            "events:booking_create",
            kwargs={"direction": "to-creator",
                    "profile_slug": self.creator.slug},
        ))
        self.assertEqual(r.status_code, 200)
        self.assertIn(self.venue, r.context["user_venues"])

    def test_to_creator_from_venue_query_picks_specific_venue(self, _m):
        """The optional ?from_venue=<slug> selects a specific venue when
        the user manages multiple."""
        second_venue = make_venue(user=self.venue_user, name="Second Stage")
        self.client.force_login(self.venue_user)
        r = self.client.get(reverse(
            "events:booking_create",
            kwargs={"direction": "to-creator",
                    "profile_slug": self.creator.slug},
        ), {"from_venue": second_venue.slug})
        self.assertEqual(r.context["venue"], second_venue)

    def test_to_creator_post_creates_booking(self, mock_notify):
        self.client.force_login(self.venue_user)
        self.client.post(reverse(
            "events:booking_create",
            kwargs={"direction": "to-creator",
                    "profile_slug": self.creator.slug},
        ), {
            "event_type": Event.EventType.CONCERT,
            "preferred_dates": "Sept 15",
            "message": "We'd love to host you.",
        })
        booking = BookingRequest.objects.get(creator=self.creator, venue=self.venue)
        self.assertEqual(booking.direction,
                         BookingRequest.Direction.VENUE_TO_CREATOR)
        self.assertEqual(booking.initiated_by, self.venue_user)
        mock_notify.assert_called_once_with(booking)


# ---------------------------------------------------------------------------
# create_from_booking
# ---------------------------------------------------------------------------


class CreateFromBookingTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.venue = make_venue(user=self.venue_user)
        self.booking = make_booking_request(
            creator=self.creator, venue=self.venue,
            status=BookingRequest.Status.ACCEPTED,
        )

    def url(self):
        return reverse("events:create_from_booking",
                       kwargs={"pk": self.booking.pk})

    def test_only_accepted_bookings_load(self):
        """The view's get_object_or_404 filters status='accepted'."""
        self.booking.status = BookingRequest.Status.PENDING
        self.booking.save()
        self.client.force_login(self.venue_user)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 404)

    def test_stranger_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 403)

    def test_booking_with_existing_event_redirects(self):
        existing = make_event(created_by=self.creator_user, title="Already linked")
        self.booking.resulting_event = existing
        self.booking.save()
        self.client.force_login(self.creator_user)
        r = self.client.get(self.url())
        self.assertRedirects(r, reverse("events:booking_detail",
                                        kwargs={"pk": self.booking.pk}))

    def test_get_renders_form_with_prefilled_event_type(self):
        self.client.force_login(self.creator_user)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        # The form is pre-populated from booking details.
        self.assertEqual(r.context["form"].initial["event_type"],
                         self.booking.event_type)
        self.assertEqual(r.context["form"].initial["venue"], self.venue)

    def test_post_creates_event_and_links_back_to_booking(self):
        from datetime import timedelta
        from django.utils import timezone
        self.client.force_login(self.creator_user)
        start = (timezone.now() + timedelta(days=14)).strftime("%Y-%m-%dT%H:%M")
        r = self.client.post(self.url(), {
            "title": "Booked Concert",
            "event_type": Event.EventType.CONCERT,
            "venue": str(self.venue.pk),
            "description": "From booking",
            "start_datetime": start,
            "is_free": "on",
            "is_published": "on",
        })
        event = Event.objects.get(title="Booked Concert")
        self.assertRedirects(r, reverse("events:detail",
                                        kwargs={"slug": event.slug}))
        # Booking now linked to the event.
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.resulting_event, event)
        # A slot for the creator was auto-created.
        slot = EventSlot.objects.get(event=event)
        self.assertEqual(slot.creator, self.creator)
        self.assertEqual(slot.status, EventSlot.Status.CONFIRMED)


# ---------------------------------------------------------------------------
# booking_feedback
# ---------------------------------------------------------------------------


class BookingFeedbackTest(TestCase):
    def setUp(self):
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user)
        self.venue = make_venue(user=self.venue_user)
        self.booking = make_booking_request(
            creator=self.creator, venue=self.venue,
            status=BookingRequest.Status.ACCEPTED,
        )

    def url(self):
        return reverse("events:booking_feedback",
                       kwargs={"pk": self.booking.pk})

    def test_only_accepted_bookings(self):
        self.booking.status = BookingRequest.Status.PENDING
        self.booking.save()
        self.client.force_login(self.creator_user)
        r = self.client.post(self.url(), {
            "body": "x", "would_work_again": True,
        })
        self.assertEqual(r.status_code, 404)

    def test_stranger_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.post(self.url(), {
            "body": "x", "would_work_again": True,
        })
        self.assertEqual(r.status_code, 403)

    def test_creates_feedback(self):
        from apps.events.models import BookingFeedback
        self.client.force_login(self.creator_user)
        r = self.client.post(self.url(), {
            "body": "Great fit, well-run venue.",
            "would_work_again": True,
        })
        self.assertRedirects(r, reverse("events:booking_detail",
                                        kwargs={"pk": self.booking.pk}))
        fb = BookingFeedback.objects.get(booking=self.booking)
        self.assertEqual(fb.author, self.creator_user)

    def test_duplicate_feedback_silently_redirects(self):
        from apps.events.models import BookingFeedback
        BookingFeedback.objects.create(
            booking=self.booking, author=self.creator_user,
            body="Original", would_work_again=True,
        )
        self.client.force_login(self.creator_user)
        r = self.client.post(self.url(), {
            "body": "Second try", "would_work_again": False,
        })
        # Only the original feedback row exists; the view redirects with
        # an info message rather than creating a duplicate.
        self.assertEqual(BookingFeedback.objects.filter(
            booking=self.booking, author=self.creator_user,
        ).count(), 1)
        self.assertRedirects(r, reverse("events:booking_detail",
                                        kwargs={"pk": self.booking.pk}))
