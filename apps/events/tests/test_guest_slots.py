"""
Guest performers in event lineups (issue #18).

A slot names exactly one performer: a registered creator or a freeform
guest (touring acts and one-offs without hub profiles). Guests render
by name with no profile link.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.events.forms import EventSlotForm
from apps.events.models import EventSlot

from .helpers import make_creator, make_event, make_user


class EventSlotGuestFormTest(TestCase):
    def _form(self, data):
        return EventSlotForm(data={"status": EventSlot.Status.CONFIRMED, "sort_order": 0, **data})

    def test_guest_only_is_valid(self):
        form = self._form({"guest_name": "The Wild Turnpikes"})
        self.assertTrue(form.is_valid(), form.errors)

    def test_creator_and_guest_together_invalid(self):
        creator = make_creator(user=make_user())
        form = self._form({"creator": str(creator.pk), "guest_name": "Somebody Else"})
        self.assertFalse(form.is_valid())
        self.assertIn("not both", str(form.errors))

    def test_neither_is_invalid(self):
        form = self._form({})
        self.assertFalse(form.is_valid())


class GuestSlotViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.event = make_event(created_by=self.owner)

    def test_post_guest_creates_slot_without_creator(self):
        self.client.force_login(self.owner)
        r = self.client.post(
            reverse("events:add_slot", kwargs={"slug": self.event.slug}),
            {"guest_name": "Touring Headliner", "status": EventSlot.Status.CONFIRMED, "sort_order": 0},
        )
        self.assertEqual(r.status_code, 200)
        slot = EventSlot.objects.get(event=self.event)
        self.assertIsNone(slot.creator)
        self.assertEqual(slot.guest_name, "Touring Headliner")
        self.assertEqual(slot.performer_name, "Touring Headliner")

    def test_event_detail_renders_guest_without_profile_link(self):
        EventSlot.objects.create(
            event=self.event, guest_name="Touring Headliner",
            status=EventSlot.Status.CONFIRMED,
        )
        r = self.client.get(self.event.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Touring Headliner")
        self.assertContains(r, "Guest performer")


class GuestSlotModelTest(TestCase):
    def test_constraint_rejects_both_and_neither(self):
        event = make_event()
        creator = make_creator(user=make_user())
        both = EventSlot(event=event, creator=creator, guest_name="X")
        with self.assertRaises(ValidationError):
            both.full_clean()
        neither = EventSlot(event=event)
        with self.assertRaises(ValidationError):
            neither.full_clean()
