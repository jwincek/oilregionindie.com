"""
Tests for the lineup-management and calendar surfaces in
apps.events.views — the HTMX endpoints under /events/<slug>/lineup/
and the monthly calendar at /events/calendar/.
"""

import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event, EventSlot

from .helpers import (
    make_creator, make_event, make_event_slot, make_user, make_venue,
)


# ---------------------------------------------------------------------------
# Calendar view
# ---------------------------------------------------------------------------


class CalendarViewTest(TestCase):
    url = reverse("events:calendar")

    def test_calendar_renders_current_month_by_default(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        today = timezone.now().date()
        self.assertEqual(r.context["year"], today.year)
        self.assertEqual(r.context["month"], today.month)

    def test_calendar_renders_specified_year_and_month(self):
        r = self.client.get(self.url, {"year": 2026, "month": 7})
        self.assertEqual(r.context["year"], 2026)
        self.assertEqual(r.context["month"], 7)
        self.assertEqual(r.context["month_name"], "July")

    def test_invalid_year_or_month_clamps_to_today(self):
        """Garbage strings → current month (no 500)."""
        today = timezone.now().date()
        r = self.client.get(self.url, {"year": "garbage", "month": "nope"})
        self.assertEqual(r.context["year"], today.year)
        self.assertEqual(r.context["month"], today.month)

    def test_out_of_range_year_clamps_to_current_year(self):
        today = timezone.now().date()
        # 1990 is below the floor (2020) — should clamp.
        r = self.client.get(self.url, {"year": "1990", "month": "3"})
        self.assertEqual(r.context["year"], today.year)
        # Year 2099 is above ceiling — also clamps.
        r = self.client.get(self.url, {"year": "2099", "month": "3"})
        self.assertEqual(r.context["year"], today.year)

    def test_month_clamped_to_1_through_12(self):
        r = self.client.get(self.url, {"year": "2026", "month": "0"})
        self.assertEqual(r.context["month"], 1)
        r = self.client.get(self.url, {"year": "2026", "month": "15"})
        self.assertEqual(r.context["month"], 12)

    def test_events_in_month_appear_in_grid(self):
        """An event scheduled within the requested month shows up in the
        day-of-month grid."""
        target = datetime(2026, 6, 15, 19, 0, tzinfo=dt_timezone.utc)
        make_event(title="Mid-June Show", start_datetime=target)
        r = self.client.get(self.url, {"year": 2026, "month": 6})
        self.assertEqual(r.context["total_events"], 1)
        # Find the cell for day 15 and confirm the event is in it.
        all_cells = [cell for week in r.context["calendar_weeks"] for cell in week]
        june_15 = next((c for c in all_cells if c["day"] == 15), None)
        self.assertIsNotNone(june_15)
        self.assertEqual(len(june_15["events"]), 1)

    def test_january_prev_navigation_rolls_year_back(self):
        r = self.client.get(self.url, {"year": 2026, "month": 1})
        self.assertEqual(r.context["prev_year"], 2025)
        self.assertEqual(r.context["prev_month"], 12)
        self.assertEqual(r.context["next_year"], 2026)
        self.assertEqual(r.context["next_month"], 2)

    def test_december_next_navigation_rolls_year_forward(self):
        r = self.client.get(self.url, {"year": 2026, "month": 12})
        self.assertEqual(r.context["prev_year"], 2026)
        self.assertEqual(r.context["prev_month"], 11)
        self.assertEqual(r.context["next_year"], 2027)
        self.assertEqual(r.context["next_month"], 1)

    def test_is_today_flag_only_on_actual_today(self):
        today = timezone.now().date()
        r = self.client.get(self.url, {"year": today.year, "month": today.month})
        all_cells = [cell for week in r.context["calendar_weeks"] for cell in week]
        # Exactly one cell flagged as today.
        flagged = [c for c in all_cells if c["is_today"]]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["day"], today.day)

    def test_unpublished_events_excluded(self):
        target = datetime(2026, 6, 10, 19, 0, tzinfo=dt_timezone.utc)
        make_event(title="Public", start_datetime=target, is_published=True)
        make_event(title="Draft", start_datetime=target, is_published=False)
        r = self.client.get(self.url, {"year": 2026, "month": 6})
        self.assertEqual(r.context["total_events"], 1)


# ---------------------------------------------------------------------------
# Lineup HTMX endpoints
# ---------------------------------------------------------------------------


class LineupViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.stranger = make_user()
        self.event = make_event(created_by=self.owner)
        self.creator = make_creator(user=make_user(), display_name="Headliner")

    def test_lineup_requires_login(self):
        r = self.client.get(reverse("events:lineup", kwargs={"slug": self.event.slug}))
        self.assertEqual(r.status_code, 302)

    def test_lineup_403_for_non_organizer(self):
        self.client.force_login(self.stranger)
        r = self.client.get(reverse("events:lineup", kwargs={"slug": self.event.slug}))
        self.assertEqual(r.status_code, 403)

    def test_lineup_partial_returns_slot_list_to_organizer(self):
        make_event_slot(self.event, self.creator)
        self.client.force_login(self.owner)
        r = self.client.get(reverse("events:lineup", kwargs={"slug": self.event.slug}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["slots"]), 1)
        self.assertTemplateUsed(r, "events/_lineup.html")


class AddSlotViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.event = make_event(created_by=self.owner)
        self.creator = make_creator(user=make_user(), display_name="Slot Candidate")

    def url(self):
        return reverse("events:add_slot", kwargs={"slug": self.event.slug})

    def test_get_renders_slot_form(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "events/_slot_form.html")

    def test_get_403_for_non_organizer(self):
        self.client.force_login(make_user())
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 403)

    def test_post_creates_slot_and_returns_lineup_partial(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url(), {
            "creator": str(self.creator.pk),
            "status": EventSlot.Status.CONFIRMED,
            "sort_order": 0,
        })
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "events/_lineup.html")
        slot = EventSlot.objects.get(event=self.event)
        self.assertEqual(slot.creator, self.creator)

    def test_post_invalid_form_re_renders_slot_form(self):
        """Posting an empty body to an HTMX form should re-render with
        errors rather than 500."""
        self.client.force_login(self.owner)
        r = self.client.post(self.url(), {})
        self.assertEqual(r.status_code, 200)
        # form is rendered, no slot was created
        self.assertFalse(EventSlot.objects.filter(event=self.event).exists())


class EditSlotViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.event = make_event(created_by=self.owner)
        self.creator = make_creator(user=make_user(), display_name="Headliner")
        self.other_creator = make_creator(user=make_user(), display_name="Replacement")
        self.slot = make_event_slot(self.event, self.creator)

    def url(self):
        return reverse("events:edit_slot",
                       kwargs={"slug": self.event.slug, "pk": self.slot.pk})

    def test_get_renders_edit_form(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["slot"], self.slot)

    def test_post_updates_slot(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url(), {
            "creator": str(self.other_creator.pk),
            "status": EventSlot.Status.CONFIRMED,
            "sort_order": 5,
        })
        self.assertEqual(r.status_code, 200)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.creator, self.other_creator)
        self.assertEqual(self.slot.sort_order, 5)

    def test_403_for_non_organizer(self):
        self.client.force_login(make_user())
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 403)

    def test_404_for_slot_belonging_to_a_different_event(self):
        """The view scopes the slot to event=<slug>, so you can't edit a
        slot from event A via event B's URL."""
        other_event = make_event(created_by=self.owner, title="Other")
        other_slot = make_event_slot(other_event, self.creator)
        self.client.force_login(self.owner)
        r = self.client.get(
            reverse("events:edit_slot",
                    kwargs={"slug": self.event.slug, "pk": other_slot.pk}),
        )
        self.assertEqual(r.status_code, 404)

    def test_post_invalid_re_renders_form(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url(), {
            "creator": "",  # required
            "status": EventSlot.Status.CONFIRMED,
            "sort_order": 0,
        })
        self.assertEqual(r.status_code, 200)


class DeleteSlotViewTest(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.event = make_event(created_by=self.owner)
        self.creator = make_creator(user=make_user())
        self.slot = make_event_slot(self.event, self.creator)

    def url(self):
        return reverse("events:delete_slot",
                       kwargs={"slug": self.event.slug, "pk": self.slot.pk})

    def test_get_not_allowed(self):
        """delete_slot is @require_POST."""
        self.client.force_login(self.owner)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 405)

    def test_organizer_deletes_slot(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertFalse(EventSlot.objects.filter(pk=self.slot.pk).exists())
        # Returns the refreshed lineup partial.
        self.assertTemplateUsed(r, "events/_lineup.html")

    def test_non_organizer_gets_403(self):
        self.client.force_login(make_user())
        r = self.client.post(self.url())
        self.assertEqual(r.status_code, 403)
        self.assertTrue(EventSlot.objects.filter(pk=self.slot.pk).exists())
