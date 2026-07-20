"""
Event relocation (issue #44): moving an event snapshots the old place,
badges the listing, and notifies followers — the rain-out that moves
instead of cancelling. Plus lineup-change notifications: the affected
creator hears about being added, removed, or cancelled on a public bill.
"""
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Notification
from apps.events.models import Event, EventSlot

from .helpers import make_creator, make_event, make_user
from .test_locations_status import form_data


def _event_notes(user):
    return Notification.objects.filter(
        recipient=user, notification_type=Notification.NotificationType.EVENT,
    )


class RelocationTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.organizer = make_creator(user=make_user())
        self.event = make_event(
            created_by=self.owner,
            organizing_creator=self.organizer,
            location_name="Justus Park",
        )
        self.fan = make_user()
        self.fan.profile.followed_creators.add(self.organizer)
        self.url = reverse("events:edit", kwargs={"slug": self.event.slug})
        self.client.force_login(self.owner)

    def test_location_change_snapshots_badges_and_notifies_once(self):
        r = self.client.post(self.url, form_data(
            title=self.event.title, location_name="The Rathskeller",
        ))
        self.assertEqual(r.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.previous_location, "Justus Park")

        notes = _event_notes(self.fan)
        self.assertEqual(notes.count(), 1)
        self.assertIn("moved to The Rathskeller", notes.first().message)
        self.assertIn("was Justus Park", notes.first().message)

        detail = self.client.get(self.event.get_absolute_url())
        self.assertContains(detail, "New location")
        self.assertContains(detail, "Moved from Justus Park")

    def test_unchanged_location_does_not_notify(self):
        self.client.post(self.url, form_data(
            title="Renamed But Not Moved", location_name="Justus Park",
        ))
        self.event.refresh_from_db()
        self.assertEqual(self.event.previous_location, "")
        self.assertEqual(_event_notes(self.fan).count(), 0)

    def test_setting_location_from_blank_is_not_a_move(self):
        event = make_event(created_by=self.owner, organizing_creator=self.organizer)
        url = reverse("events:edit", kwargs={"slug": event.slug})
        self.client.post(url, form_data(
            title=event.title, location_name="First Announced Spot",
        ))
        event.refresh_from_db()
        self.assertEqual(event.previous_location, "")
        self.assertEqual(_event_notes(self.fan).count(), 0)


class LineupNotificationTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.event = make_event(created_by=self.owner)
        self.performer = make_creator(user=make_user(), display_name="Notified Act")
        self.client.force_login(self.owner)

    def _add_url(self):
        return reverse("events:add_slot", kwargs={"slug": self.event.slug})

    def _add_slot(self, **extra):
        return self.client.post(self._add_url(), {
            "creator": str(self.performer.pk),
            "status": EventSlot.Status.CONFIRMED,
            "sort_order": 0,
            **extra,
        })

    def test_added_to_lineup_notifies_performer(self):
        self._add_slot()
        notes = _event_notes(self.performer.user)
        self.assertEqual(notes.count(), 1)
        self.assertIn("added to the lineup", notes.first().message)

    def test_removed_from_lineup_notifies_performer(self):
        self._add_slot()
        slot = EventSlot.objects.get(event=self.event)
        self.client.post(reverse("events:delete_slot", kwargs={
            "slug": self.event.slug, "pk": slot.pk,
        }))
        messages = [n.message for n in _event_notes(self.performer.user)]
        self.assertTrue(any("removed from the lineup" in m for m in messages))

    def test_slot_cancellation_notifies_performer_once(self):
        self._add_slot()
        slot = EventSlot.objects.get(event=self.event)
        edit_url = reverse("events:edit_slot", kwargs={
            "slug": self.event.slug, "pk": slot.pk,
        })
        data = {"creator": str(self.performer.pk),
                "status": EventSlot.Status.CANCELLED, "sort_order": 0}
        self.client.post(edit_url, data)
        self.client.post(edit_url, data)  # same status again — no re-notify
        messages = [n.message for n in _event_notes(self.performer.user)]
        self.assertEqual(sum("was cancelled" in m for m in messages), 1)

    def test_guest_slot_notifies_no_one(self):
        self.client.post(self._add_url(), {
            "guest_name": "Touring Headliner",
            "status": EventSlot.Status.CONFIRMED, "sort_order": 0,
        })
        self.assertEqual(Notification.objects.count(), 0)

    def test_self_add_is_not_notified(self):
        own_profile = make_creator(user=self.owner, display_name="Owner Act")
        self.client.post(self._add_url(), {
            "creator": str(own_profile.pk),
            "status": EventSlot.Status.CONFIRMED, "sort_order": 0,
        })
        self.assertEqual(_event_notes(self.owner).count(), 0)
