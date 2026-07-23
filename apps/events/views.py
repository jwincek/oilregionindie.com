from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.core.notifications import notify_booking_status_changed

from .forms import (
    BookingFeedbackForm, BookingRequestForm, BookingResponseForm,
    EndorsementForm, EventForm, EventSlotForm,
)
from .models import (
    BookingFeedback, BookingRequest, Endorsement, Event, EventRSVP, EventSlot,
)


@require_GET
def listing(request):
    """Upcoming events listing with filtering."""
    events = Event.objects.filter(
        is_published=True,
        start_datetime__gte=timezone.now(),
    ).select_related("venue").prefetch_related("creators")

    event_type = request.GET.get("type")
    if event_type:
        events = events.filter(event_type=event_type)

    location = request.GET.get("location")
    if location:
        events = events.filter(
            Q(venue__city__icontains=location) | Q(venue__state__icontains=location)
        )

    venue_slug = request.GET.get("venue")
    if venue_slug:
        events = events.filter(venue__slug=venue_slug)

    cost = request.GET.get("cost")
    if cost == "free":
        events = events.filter(is_free=True)
    elif cost == "paid":
        events = events.filter(is_free=False)

    query = request.GET.get("q")
    if query:
        from wagtail.search.backends import get_search_backend
        try:
            search_results = get_search_backend().search(query, events)
            if len(search_results) > 0:
                events = search_results
            else:
                events = events.filter(
                    Q(title__icontains=query) | Q(description__icontains=query)
                )
        except Exception:
            events = events.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            )

    from apps.venues.models import VenueProfile
    venues = VenueProfile.objects.filter(publish_status="published").order_by("name")

    template = "events/_event_list.html" if request.htmx else "events/listing.html"

    return render(request, template, {
        "events": events,
        "event_types": Event.EventType.choices,
        "venues": venues,
        "current_type": event_type,
        "current_location": location or "",
        "current_venue": venue_slug or "",
        "current_cost": cost or "",
        "query": query or "",
    })


@require_GET
def detail(request, slug):
    """Event detail page with lineup."""
    event = get_object_or_404(
        Event.objects.select_related(
            "venue", "created_by", "organizing_creator", "organizing_venue"
        ).prefetch_related(
            "slots__creator__disciplines"
        ),
        slug=slug,
        is_published=True,
    )
    return render(request, "events/detail.html", {
        "event": event,
        **_rsvp_context(event, request.user),
    })


def _rsvp_context(event, user):
    """Public RSVP counts for an event, plus the viewer's own RSVP status."""
    rsvps = list(event.rsvps.all())
    my_rsvp = None
    if user.is_authenticated:
        my_rsvp = next((r.status for r in rsvps if r.user_id == user.pk), None)
    return {
        "going_count": sum(1 for r in rsvps if r.status == EventRSVP.Status.GOING),
        "interested_count": sum(
            1 for r in rsvps if r.status == EventRSVP.Status.INTERESTED
        ),
        "my_rsvp": my_rsvp,
    }


@login_required
@require_POST
def rsvp(request, slug):
    """Toggle the current user's RSVP to an event. Clicking the status you
    already hold clears it; a different status switches to it."""
    event = get_object_or_404(Event, slug=slug, is_published=True)
    status = request.POST.get("status")
    if status not in (EventRSVP.Status.GOING, EventRSVP.Status.INTERESTED):
        raise Http404

    existing = EventRSVP.objects.filter(event=event, user=request.user).first()
    if existing and existing.status == status:
        existing.delete()
    else:
        EventRSVP.objects.update_or_create(
            event=event, user=request.user, defaults={"status": status}
        )

    if request.htmx:
        return render(
            request, "events/_rsvp_button.html",
            {"event": event, **_rsvp_context(event, request.user)},
        )
    return redirect(event.get_absolute_url())


@require_GET
def calendar_view(request):
    """Monthly calendar view of events."""
    import calendar
    from datetime import date

    # Get year/month from query params, default to current
    today = timezone.now().date()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    # Clamp to reasonable range
    if year < 2020 or year > 2030:
        year = today.year
    month = max(1, min(12, month))

    # Get events for this month
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1)
    else:
        last_day = date(year, month + 1, 1)

    events = Event.objects.filter(
        is_published=True,
        start_datetime__date__gte=first_day,
        start_datetime__date__lt=last_day,
    ).select_related("venue").order_by("start_datetime")

    # Group events by day
    events_by_day = {}
    for event in events:
        day = event.start_datetime.day
        events_by_day.setdefault(day, []).append(event)

    # Build calendar grid
    cal = calendar.Calendar(firstweekday=6)  # Sunday first
    weeks = cal.monthdayscalendar(year, month)

    calendar_weeks = []
    for week in weeks:
        week_data = []
        for day in week:
            if day == 0:
                week_data.append({"day": 0, "events": [], "is_today": False})
            else:
                week_data.append({
                    "day": day,
                    "events": events_by_day.get(day, []),
                    "is_today": (day == today.day and month == today.month and year == today.year),
                })
        calendar_weeks.append(week_data)

    # Previous/next month navigation
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    month_name = calendar.month_name[month]

    return render(request, "events/calendar.html", {
        "calendar_weeks": calendar_weeks,
        "month_name": month_name,
        "year": year,
        "month": month,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "today": today,
        "total_events": events.count(),
    })


@require_GET
def past(request):
    """Archive of past events."""
    events = Event.objects.filter(
        is_published=True,
        start_datetime__lt=timezone.now(),
    ).select_related("venue").order_by("-start_datetime")

    return render(request, "events/past.html", {"events": events})


@login_required
def create(request):
    """Create a new event."""
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            if hasattr(request.user, "creator_profile"):
                event.organizing_creator = request.user.creator_profile
            # Auto-set organizing_venue if event has a venue the user manages
            if event.venue and event.venue.can_be_edited_by(request.user):
                event.organizing_venue = event.venue
            event.save()
            form.save_m2m()
            return redirect("events:detail", slug=event.slug)
    else:
        # Smart defaults
        initial = {}
        user_venues = list(request.user.venue_profiles.all())
        if user_venues:
            initial["venue"] = user_venues[0]
        form = EventForm(initial=initial)

    return render(request, "events/create.html", {"form": form})


@login_required
def edit(request, slug):
    """Edit an event (organizer or manager only)."""
    event = get_object_or_404(Event, slug=slug)
    if not event.can_be_edited_by(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    old_status = event.status
    old_location = event.location_display
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            # Tell followers of the organizing profiles when a show they
            # might attend gets cancelled or postponed (issue #20).
            if event.status != old_status and event.status in (
                Event.Status.CANCELLED, Event.Status.POSTPONED,
            ):
                from apps.core.notifications import notify_event_status_changed
                notify_event_status_changed(event)
            # ... or moves somewhere else (issue #44). Snapshot where it
            # was so the listing can say "moved from X".
            new_location = event.location_display
            if old_location and new_location and new_location != old_location:
                event.previous_location = old_location
                event.save(update_fields=["previous_location"])
                from apps.core.notifications import notify_event_relocated
                notify_event_relocated(event, old_location)
            return redirect("events:detail", slug=event.slug)
    else:
        form = EventForm(instance=event)

    return render(request, "events/edit.html", {"form": form, "event": event})


# ---------------------------------------------------------------------------
# Lineup management (HTMX-powered)
# ---------------------------------------------------------------------------


def _get_editable_event(request, slug):
    """Get an event the current user can edit, or 403."""
    event = get_object_or_404(Event, slug=slug)
    if not event.can_be_edited_by(request.user):
        return None, HttpResponseForbidden()
    return event, None


def _lineup_context(event):
    return {
        "event": event,
        "slots": event.lineup,
    }


@login_required
def lineup(request, slug):
    """List lineup slots for an event (HTMX partial)."""
    event, err = _get_editable_event(request, slug)
    if err:
        return err
    return render(request, "events/_lineup.html", _lineup_context(event))


@login_required
def add_slot(request, slug):
    """Add a slot to an event's lineup via HTMX."""
    event, err = _get_editable_event(request, slug)
    if err:
        return err

    if request.method == "POST":
        form = EventSlotForm(request.POST, event=event)
        if form.is_valid():
            slot = form.save(commit=False)
            slot.event = event
            slot.save()
            from apps.core.notifications import notify_lineup_change
            notify_lineup_change(slot, "added", actor=request.user)
            return render(request, "events/_lineup.html", _lineup_context(event))
    else:
        # Default sort_order to next in sequence
        next_order = (event.slots.count()) * 1
        form = EventSlotForm(event=event, initial={"sort_order": next_order})

    return render(request, "events/_slot_form.html", {
        "form": form,
        "event": event,
    })


@login_required
def edit_slot(request, slug, pk):
    """Edit a lineup slot via HTMX."""
    event, err = _get_editable_event(request, slug)
    if err:
        return err
    slot = get_object_or_404(EventSlot, pk=pk, event=event)
    old_slot_status = slot.status

    if request.method == "POST":
        form = EventSlotForm(request.POST, instance=slot, event=event)
        if form.is_valid():
            form.save()
            if (
                slot.status == EventSlot.Status.CANCELLED
                and old_slot_status != EventSlot.Status.CANCELLED
            ):
                from apps.core.notifications import notify_lineup_change
                notify_lineup_change(slot, "cancelled", actor=request.user)
            return render(request, "events/_lineup.html", _lineup_context(event))
    else:
        form = EventSlotForm(instance=slot, event=event)

    return render(request, "events/_slot_form.html", {
        "form": form,
        "event": event,
        "slot": slot,
    })


@login_required
@require_POST
def delete_slot(request, slug, pk):
    """Remove a slot from an event's lineup via HTMX."""
    event, err = _get_editable_event(request, slug)
    if err:
        return err
    slot = get_object_or_404(EventSlot, pk=pk, event=event)
    from apps.core.notifications import notify_lineup_change
    notify_lineup_change(slot, "removed", actor=request.user)
    slot.delete()
    return render(request, "events/_lineup.html", _lineup_context(event))


# ---------------------------------------------------------------------------
# Booking requests
# ---------------------------------------------------------------------------


def _get_user_profiles(user):
    """Return the user's creator profile and venue profiles (if any)."""
    creator = getattr(user, "creator_profile", None)
    venues = list(user.venue_profiles.all()) if hasattr(user, "venue_profiles") else []
    # Include venues where user is a manager
    managed_venues = list(user.managed_venue_profiles.all()) if hasattr(user, "managed_venue_profiles") else []
    all_venues = list({v.pk: v for v in venues + managed_venues}.values())
    return creator, all_venues


@login_required
def booking_inbox(request):
    """Show all booking requests for the current user's profiles."""
    creator, venues = _get_user_profiles(request.user)

    # Build query for all requests involving the user's profiles
    filters = Q()
    if creator:
        filters |= Q(creator=creator)
    for venue in venues:
        filters |= Q(venue=venue)

    if not filters:
        requests_list = BookingRequest.objects.none()
    else:
        requests_list = BookingRequest.objects.filter(filters).select_related(
            "creator", "venue", "initiated_by"
        ).distinct()

    # Apply search filter
    query = request.GET.get("q", "").strip()
    if query:
        requests_list = requests_list.filter(
            Q(creator__display_name__icontains=query) |
            Q(venue__name__icontains=query) |
            Q(message__icontains=query)
        )

    # Apply status filter
    status_filter = request.GET.get("status", "")
    if status_filter:
        requests_list = requests_list.filter(status=status_filter)

    # Split into actionable (pending, received) and other
    received_pending = [r for r in requests_list if r.status == "pending" and r.can_be_responded_to_by(request.user)]
    sent_pending = [r for r in requests_list if r.status == "pending" and not r.can_be_responded_to_by(request.user)]
    resolved = [r for r in requests_list if r.status != "pending"]

    return render(request, "events/booking_inbox.html", {
        "received_pending": received_pending,
        "sent_pending": sent_pending,
        "resolved": resolved,
        "query": query,
        "status_filter": status_filter,
        "total_count": len(received_pending) + len(sent_pending) + len(resolved),
    })


@login_required
def booking_detail(request, pk):
    """View a booking request and optionally respond."""
    booking = get_object_or_404(
        BookingRequest.objects.select_related("creator", "venue", "initiated_by"),
        pk=pk,
    )

    if not booking.can_be_viewed_by(request.user):
        raise Http404

    can_respond = booking.status == "pending" and booking.can_be_responded_to_by(request.user)
    response_form = BookingResponseForm() if can_respond else None

    # Feedback: only for accepted bookings, check if user already left feedback
    my_feedback = booking.feedback.filter(author=request.user).first()
    other_feedback = booking.feedback.exclude(author=request.user).first()
    can_leave_feedback = (
        booking.status == "accepted"
        and booking.can_be_viewed_by(request.user)
        and not my_feedback
    )
    feedback_form = BookingFeedbackForm() if can_leave_feedback else None

    return render(request, "events/booking_detail.html", {
        "booking": booking,
        "can_respond": can_respond,
        "response_form": response_form,
        "my_feedback": my_feedback,
        "other_feedback": other_feedback,
        "can_leave_feedback": can_leave_feedback,
        "feedback_form": feedback_form,
    })


@login_required
@require_POST
def booking_respond(request, pk):
    """Accept or decline a booking request."""
    booking = get_object_or_404(BookingRequest, pk=pk)

    if booking.status != "pending" or not booking.can_be_responded_to_by(request.user):
        return HttpResponseForbidden()

    form = BookingResponseForm(request.POST)
    if form.is_valid():
        action = form.cleaned_data["action"]
        booking.response_message = form.cleaned_data.get("response_message", "")
        booking.responded_at = timezone.now()

        if action == "accept":
            booking.status = BookingRequest.Status.ACCEPTED
            messages.success(request, "Booking request accepted.")
        else:
            booking.status = BookingRequest.Status.DECLINED
            messages.info(request, "Booking request declined.")

        booking.save(update_fields=["status", "response_message", "responded_at", "updated_at"])
        notify_booking_status_changed(booking)

    return redirect("events:booking_detail", pk=booking.pk)


@login_required
@require_POST
def booking_withdraw(request, pk):
    """Withdraw a pending booking request (initiator only)."""
    booking = get_object_or_404(BookingRequest, pk=pk)

    if booking.status != "pending" or booking.initiated_by != request.user:
        return HttpResponseForbidden()

    booking.status = BookingRequest.Status.WITHDRAWN
    booking.save(update_fields=["status", "updated_at"])
    messages.info(request, "Booking request withdrawn.")

    return redirect("events:booking_inbox")


@login_required
def booking_create(request, direction, profile_slug):
    """
    Create a booking request.
    direction: 'to-venue' (creator initiates) or 'to-creator' (venue initiates)
    profile_slug: the target profile's slug
    """
    from apps.creators.models import CreatorProfile
    from apps.venues.models import VenueProfile

    if direction == "to-venue":
        # Creator is requesting to book at a venue
        # user__isnull=False: unclaimed (admin-seeded) listings have no one
        # behind them to answer, and the notification path needs a recipient
        venue = get_object_or_404(
            VenueProfile, slug=profile_slug, publish_status="published",
            user__isnull=False,
        )
        creator = getattr(request.user, "creator_profile", None)
        if not creator:
            messages.error(request, "You need a creator profile to send booking requests.")
            return redirect("creators:setup")
        target_name = venue.name
        booking_direction = BookingRequest.Direction.CREATOR_TO_VENUE
    elif direction == "to-creator":
        # Venue is inviting a creator
        creator = get_object_or_404(
            CreatorProfile, slug=profile_slug, publish_status="published",
            user__isnull=False,
        )
        # Find which venues the user manages
        user_venues = list({v.pk: v for v in (
            list(request.user.venue_profiles.all()) +
            list(request.user.managed_venue_profiles.all())
        )}.values())
        if not user_venues:
            messages.error(request, "You need a venue profile to send booking invitations.")
            return redirect("venues:setup")
        # If user selected a venue via GET param, use that
        venue_slug = request.GET.get("from_venue") or request.POST.get("from_venue")
        if venue_slug:
            venue = next((v for v in user_venues if v.slug == venue_slug), user_venues[0])
        else:
            venue = user_venues[0]
        target_name = creator.display_name
        booking_direction = BookingRequest.Direction.VENUE_TO_CREATOR
    else:
        raise Http404

    if request.method == "POST":
        form = BookingRequestForm(request.POST)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.creator = creator
            booking.venue = venue
            booking.initiated_by = request.user
            booking.direction = booking_direction
            booking.save()
            notify_booking_status_changed(booking)
            messages.success(request, f"Booking request sent to {target_name}.")
            return redirect("events:booking_inbox")
    else:
        form = BookingRequestForm()

    return render(request, "events/booking_create.html", {
        "form": form,
        "direction": direction,
        "target_name": target_name,
        "creator": creator,
        "venue": venue,
        "user_venues": user_venues if direction == "to-creator" else [],
    })


# ---------------------------------------------------------------------------
# Create event from accepted booking
# ---------------------------------------------------------------------------


@login_required
def create_from_booking(request, pk):
    """Pre-fill an event form from an accepted booking request."""
    booking = get_object_or_404(BookingRequest, pk=pk, status="accepted")

    if not booking.can_be_viewed_by(request.user):
        return HttpResponseForbidden()

    if booking.resulting_event:
        messages.info(request, "An event has already been created from this booking.")
        return redirect("events:booking_detail", pk=booking.pk)

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            if hasattr(request.user, "creator_profile"):
                event.organizing_creator = request.user.creator_profile
            event.save()
            form.save_m2m()

            # Create a slot for the creator
            EventSlot.objects.create(
                event=event,
                creator=booking.creator,
                status=EventSlot.Status.CONFIRMED,
            )

            # Link the booking to the event
            booking.resulting_event = event
            booking.save(update_fields=["resulting_event", "updated_at"])

            messages.success(request, f'Event "{event.title}" created from booking.')
            return redirect("events:detail", slug=event.slug)
    else:
        # Pre-fill the form from booking details
        form = EventForm(initial={
            "event_type": booking.event_type,
            "venue": booking.venue,
            "organizing_venue": booking.venue,
            "organizing_creator": booking.creator if booking.is_venue_initiated else None,
            "is_published": False,
        })

    return render(request, "events/create.html", {
        "form": form,
        "booking": booking,
    })


# ---------------------------------------------------------------------------
# Booking feedback (private)
# ---------------------------------------------------------------------------


@login_required
@require_POST
def booking_feedback(request, pk):
    """Leave private feedback on an accepted booking."""
    booking = get_object_or_404(BookingRequest, pk=pk, status="accepted")

    if not booking.can_be_viewed_by(request.user):
        return HttpResponseForbidden()

    # Check user hasn't already left feedback
    if booking.feedback.filter(author=request.user).exists():
        messages.info(request, "You've already left feedback for this booking.")
        return redirect("events:booking_detail", pk=booking.pk)

    form = BookingFeedbackForm(request.POST)
    if form.is_valid():
        fb = form.save(commit=False)
        fb.booking = booking
        fb.author = request.user
        fb.save()
        messages.success(request, "Feedback saved. Only the other party can see it.")

    return redirect("events:booking_detail", pk=booking.pk)


# ---------------------------------------------------------------------------
# Endorsements (public)
# ---------------------------------------------------------------------------


@login_required
def endorse(request, creator_slug, venue_slug):
    """Create an endorsement between a creator and venue."""
    from apps.creators.models import CreatorProfile
    from apps.venues.models import VenueProfile

    creator = get_object_or_404(CreatorProfile, slug=creator_slug, publish_status="published")
    venue = get_object_or_404(VenueProfile, slug=venue_slug, publish_status="published")

    # User must be the creator or the venue owner/manager
    is_creator_side = creator.can_be_edited_by(request.user)
    is_venue_side = venue.can_be_edited_by(request.user)
    if not is_creator_side and not is_venue_side:
        return HttpResponseForbidden()

    # Check for existing endorsement from this user
    if Endorsement.objects.filter(creator=creator, venue=venue, author=request.user).exists():
        messages.info(request, "You've already endorsed this relationship.")
        return redirect(creator.get_absolute_url() if is_venue_side else venue.get_absolute_url())

    if request.method == "POST":
        form = EndorsementForm(request.POST)
        if form.is_valid():
            endorsement = form.save(commit=False)
            endorsement.creator = creator
            endorsement.venue = venue
            endorsement.author = request.user
            endorsement.save()

            # Notify the other party
            from apps.core.models import Notification
            if is_creator_side:
                Notification.objects.create(
                    recipient=venue.user,
                    actor=request.user,
                    notification_type=Notification.NotificationType.FOLLOW,
                    message=f"{creator.display_name} endorsed {venue.name}",
                    url=f"/venues/{venue.slug}/",
                )
            else:
                Notification.objects.create(
                    recipient=creator.user,
                    actor=request.user,
                    notification_type=Notification.NotificationType.FOLLOW,
                    message=f"{venue.name} endorsed {creator.display_name}",
                    url=creator.get_absolute_url(),
                )

            messages.success(request, "Endorsement published.")
            return redirect(creator.get_absolute_url() if is_venue_side else venue.get_absolute_url())
    else:
        form = EndorsementForm()

    return render(request, "events/endorse.html", {
        "form": form,
        "creator": creator,
        "venue": venue,
        "is_creator_side": is_creator_side,
    })


@login_required
@require_POST
def edit_endorsement(request, pk):
    """Edit an endorsement (author only)."""
    endorsement = get_object_or_404(Endorsement, pk=pk, author=request.user)

    if request.method == "POST":
        form = EndorsementForm(request.POST, instance=endorsement)
        if form.is_valid():
            form.save()
            messages.success(request, "Endorsement updated.")
            return redirect(endorsement.creator.get_absolute_url())
    else:
        form = EndorsementForm(instance=endorsement)

    return render(request, "events/endorse.html", {
        "form": form,
        "creator": endorsement.creator,
        "venue": endorsement.venue,
        "is_creator_side": endorsement.is_from_creator,
        "editing": True,
    })


@login_required
@require_POST
def delete_endorsement(request, pk):
    """Delete an endorsement (author only)."""
    endorsement = get_object_or_404(Endorsement, pk=pk, author=request.user)
    creator_url = endorsement.creator.get_absolute_url()
    endorsement.delete()
    messages.info(request, "Endorsement removed.")
    return redirect(creator_url)


@require_GET
def series_detail(request, slug):
    """A festival / pop-up crawl page: all published events in a series."""
    from .models import EventSeries

    series = get_object_or_404(EventSeries, slug=slug)
    series_events = series.events.filter(is_published=True).select_related("venue")
    return render(request, "events/series_detail.html", {
        "series": series,
        "events": series_events,
    })
