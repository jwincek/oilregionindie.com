"""
Tests for apps.core.notifications — the three email-and-in-app
notification helpers that fan out from the views layer:

  notify_admin_profile_submitted   → admins, when a profile enters
                                     pending-review state.
  notify_profile_approved          → the profile owner, when an admin
                                     approves their profile.
  notify_booking_status_changed    → the other party of a booking
                                     request, on create / accept /
                                     decline (silent on withdrawn /
                                     expired).

We pin the email backend to the locmem backend so `mail.outbox`
collects messages without leaving files in /tmp/oilregion-emails/.
"""

from django.core import mail
from django.test import TestCase, override_settings

from apps.core.models import Notification
from apps.core.notifications import (
    notify_admin_profile_submitted,
    notify_booking_status_changed,
    notify_profile_approved,
)
from apps.creators.tests.helpers import make_creator, make_user
from apps.events.models import BookingRequest
from apps.events.tests.helpers import make_booking_request
from apps.venues.tests.helpers import make_venue


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotifyAdminProfileSubmittedTest(TestCase):
    def setUp(self):
        mail.outbox.clear()

    @override_settings(ADMINS=[("Admin One", "a@example.com"),
                               ("Admin Two", "b@example.com")])
    def test_creator_profile_emails_all_admins(self):
        c = make_creator(user=make_user(), display_name="Sender Creator",
                         publish_status="pending")
        notify_admin_profile_submitted(c)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("Creator", msg.subject)
        self.assertIn("Sender Creator", msg.subject)
        self.assertSetEqual(set(msg.to), {"a@example.com", "b@example.com"})
        # Message body contains the admin URL pointing at the right model.
        self.assertIn("/admin/creators/creatorprofile/", msg.body)

    @override_settings(ADMINS=[("Admin", "a@example.com")])
    def test_venue_profile_emails_admins_with_venue_subject(self):
        v = make_venue(user=make_user(), name="Sender Venue",
                       publish_status="pending")
        notify_admin_profile_submitted(v)
        msg = mail.outbox[0]
        self.assertIn("Venue", msg.subject)
        self.assertIn("Sender Venue", msg.subject)
        self.assertIn("/admin/venues/venueprofile/", msg.body)

    @override_settings(ADMINS=[],
                       DEFAULT_FROM_EMAIL="fallback@example.com")
    def test_falls_back_to_default_from_email_when_no_admins(self):
        c = make_creator(user=make_user())
        notify_admin_profile_submitted(c)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["fallback@example.com"])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotifyProfileApprovedTest(TestCase):
    def setUp(self):
        mail.outbox.clear()

    def test_creator_approval_creates_notification_and_emails_owner(self):
        owner = make_user()
        c = make_creator(user=owner, display_name="Approved Creator")
        notify_profile_approved(c)
        notif = Notification.objects.get(recipient=owner)
        self.assertEqual(
            notif.notification_type,
            Notification.NotificationType.PROFILE_APPROVED,
        )
        self.assertIn("Approved Creator", notif.message)
        self.assertEqual(notif.url, c.get_absolute_url())
        # And an email landed in the outbox addressed to the owner.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [owner.email])
        self.assertIn("approved", mail.outbox[0].body.lower())

    def test_venue_approval_uses_venue_url_and_name(self):
        owner = make_user()
        v = make_venue(user=owner, name="Approved Venue")
        notify_profile_approved(v)
        notif = Notification.objects.get(recipient=owner)
        self.assertIn("Approved Venue", notif.message)
        self.assertEqual(notif.url, v.get_absolute_url())
        self.assertIn("approved", mail.outbox[0].body.lower())


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotifyBookingStatusChangedTest(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.creator_user = make_user()
        self.venue_user = make_user()
        self.creator = make_creator(user=self.creator_user,
                                    display_name="Headliner")
        self.venue = make_venue(user=self.venue_user, name="Main Stage")

    # ----- pending: brand-new request fan-out -----

    def test_pending_creator_initiated_emails_venue_and_notifies_venue_user(self):
        booking = make_booking_request(
            creator=self.creator, venue=self.venue,
            direction=BookingRequest.Direction.CREATOR_TO_VENUE,
        )
        notify_booking_status_changed(booking)
        # Email lands on the venue's booking email (falls back to user.email).
        self.assertEqual(mail.outbox[0].to, [self.venue.booking_email])
        self.assertIn("Booking request from Headliner",
                      mail.outbox[0].subject)
        # In-app notification routed to the venue owner.
        notif = Notification.objects.get(recipient=self.venue_user)
        self.assertEqual(notif.notification_type,
                         Notification.NotificationType.BOOKING)
        self.assertEqual(notif.actor, booking.initiated_by)
        self.assertIn("Main Stage", notif.message)

    def test_pending_venue_initiated_emails_creator_and_notifies_creator_user(self):
        booking = make_booking_request(
            creator=self.creator, venue=self.venue,
            direction=BookingRequest.Direction.VENUE_TO_CREATOR,
        )
        notify_booking_status_changed(booking)
        self.assertEqual(mail.outbox[0].to,
                         [self.creator.booking_email or self.creator_user.email])
        self.assertIn("Booking invitation from Main Stage",
                      mail.outbox[0].subject)
        notif = Notification.objects.get(recipient=self.creator_user)
        self.assertEqual(notif.notification_type,
                         Notification.NotificationType.BOOKING)

    # ----- accepted / declined: response fan-out -----

    def test_accepted_creator_initiated_emails_creator_initiator(self):
        booking = make_booking_request(
            creator=self.creator, venue=self.venue,
            direction=BookingRequest.Direction.CREATOR_TO_VENUE,
            status=BookingRequest.Status.ACCEPTED,
            response_message="See you Friday",
        )
        notify_booking_status_changed(booking)
        # Email goes to the initiator (the creator user, who originated
        # the request).
        self.assertEqual(mail.outbox[0].to, [booking.initiated_by.email])
        self.assertIn("accepted", mail.outbox[0].subject)
        self.assertIn("See you Friday", mail.outbox[0].body)
        # Notification recipient is the initiator (no actor on responses).
        notif = Notification.objects.get(recipient=booking.initiated_by)
        self.assertIsNone(notif.actor)
        self.assertIn("accepted", notif.message)

    def test_declined_venue_initiated_emails_initiator(self):
        booking = make_booking_request(
            creator=self.creator, venue=self.venue,
            direction=BookingRequest.Direction.VENUE_TO_CREATOR,
            status=BookingRequest.Status.DECLINED,
        )
        notify_booking_status_changed(booking)
        self.assertEqual(mail.outbox[0].to, [booking.initiated_by.email])
        self.assertIn("declined", mail.outbox[0].subject)
        # No response_message → body shouldn't include the "Response:" header.
        self.assertNotIn("Response:", mail.outbox[0].body)
        notif = Notification.objects.get(recipient=booking.initiated_by)
        self.assertIn("declined", notif.message)

    # ----- terminal states: silent -----

    def test_withdrawn_status_is_silent(self):
        booking = make_booking_request(
            creator=self.creator, venue=self.venue,
            status=BookingRequest.Status.WITHDRAWN,
        )
        notify_booking_status_changed(booking)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_expired_status_is_silent(self):
        booking = make_booking_request(
            creator=self.creator, venue=self.venue,
            status=BookingRequest.Status.EXPIRED,
        )
        notify_booking_status_changed(booking)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Notification.objects.count(), 0)
