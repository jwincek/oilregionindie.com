"""
Tests for events app forms.

Covers: EventForm validation, required fields, optional fields, venue/organizer selection.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.events.forms import EventForm

from .helpers import make_creator, make_venue


class EventFormTest(TestCase):
    def get_valid_data(self, **overrides):
        future = (timezone.now() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
        data = {
            "title": "Test Event",
            "event_type": "concert",
            "start_datetime": future,
            "description": "",
            "is_free": True,
            "ticket_price_cents": "",
            "ticket_url": "",
            "is_virtual": False,
            "stream_url": "",
            "is_published": True,
        }
        data.update(overrides)
        return data

    def test_valid_minimal_data(self):
        form = EventForm(data=self.get_valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_requires_title(self):
        form = EventForm(data=self.get_valid_data(title=""))
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)

    def test_requires_start_datetime(self):
        form = EventForm(data=self.get_valid_data(start_datetime=""))
        self.assertFalse(form.is_valid())
        self.assertIn("start_datetime", form.errors)

    def test_requires_event_type(self):
        form = EventForm(data=self.get_valid_data(event_type=""))
        self.assertFalse(form.is_valid())
        self.assertIn("event_type", form.errors)

    def test_invalid_event_type(self):
        form = EventForm(data=self.get_valid_data(event_type="rave"))
        self.assertFalse(form.is_valid())
        self.assertIn("event_type", form.errors)

    def test_all_event_types_accepted(self):
        for etype in ["concert", "art_show", "market", "festival", "open_mic", "workshop", "other"]:
            form = EventForm(data=self.get_valid_data(event_type=etype))
            self.assertTrue(form.is_valid(), f"Failed for event_type={etype}: {form.errors}")

    def test_venue_optional(self):
        form = EventForm(data=self.get_valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_venue_selection(self):
        venue = make_venue(name="Test Venue")
        form = EventForm(data=self.get_valid_data(venue=venue.pk))
        self.assertTrue(form.is_valid(), form.errors)

    def test_organizing_creator_optional(self):
        form = EventForm(data=self.get_valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_organizing_creator_selection(self):
        creator = make_creator(display_name="Organizer")
        form = EventForm(data=self.get_valid_data(organizing_creator=creator.pk))
        self.assertTrue(form.is_valid(), form.errors)

    def test_organizing_venue_optional(self):
        form = EventForm(data=self.get_valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_organizing_venue_selection(self):
        venue = make_venue(name="Organizing Venue")
        form = EventForm(data=self.get_valid_data(organizing_venue=venue.pk))
        self.assertTrue(form.is_valid(), form.errors)

    def test_end_datetime_optional(self):
        form = EventForm(data=self.get_valid_data(end_datetime=""))
        self.assertTrue(form.is_valid(), form.errors)

    def test_ticket_url_validates(self):
        form = EventForm(data=self.get_valid_data(ticket_url="not-a-url"))
        self.assertFalse(form.is_valid())
        self.assertIn("ticket_url", form.errors)

    def test_stream_url_validates(self):
        form = EventForm(data=self.get_valid_data(stream_url="not-a-url"))
        self.assertFalse(form.is_valid())
        self.assertIn("stream_url", form.errors)

    def test_virtual_event(self):
        form = EventForm(data=self.get_valid_data(
            is_virtual=True,
            stream_url="https://twitch.tv/example",
        ))
        self.assertTrue(form.is_valid(), form.errors)
