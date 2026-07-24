"""
Per-event .ics calendar export (issue #22).
"""
from django.test import TestCase
from django.urls import reverse

from apps.events.models import Event
from apps.events.tests.helpers import make_event


class ICSModelTest(TestCase):
    def test_to_ics_has_core_vevent_fields(self):
        event = make_event(title="Friday Show")
        ics = event.to_ics("https://example.test")
        for token in ("BEGIN:VCALENDAR", "BEGIN:VEVENT", "SUMMARY:Friday Show",
                      "DTSTART:", "DTEND:", "UID:", "END:VCALENDAR"):
            self.assertIn(token, ics)
        self.assertIn("URL:https://example.test/events/friday-show/", ics)
        self.assertTrue(ics.endswith("\r\n"))  # CRLF line endings

    def test_special_characters_are_escaped(self):
        event = make_event(title="Rock, Sweat; Beer")
        ics = event.to_ics()
        self.assertIn("SUMMARY:Rock\\, Sweat\\; Beer", ics)

    def test_cancelled_event_marked(self):
        event = make_event(status=Event.Status.CANCELLED)
        self.assertIn("STATUS:CANCELLED", event.to_ics())


class ICSViewTest(TestCase):
    def test_download_headers_and_body(self):
        event = make_event(title="Downloadable")
        r = self.client.get(reverse("events:ics", kwargs={"slug": event.slug}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn(f'filename="{event.slug}.ics"', r["Content-Disposition"])
        self.assertIn(b"BEGIN:VCALENDAR", r.content)

    def test_detail_page_links_to_ics(self):
        event = make_event()
        r = self.client.get(event.get_absolute_url())
        self.assertContains(r, reverse("events:ics", kwargs={"slug": event.slug}))
