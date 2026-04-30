from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.core.notifications import notify_booking_status_changed

from .forms import BookingRequestForm, BookingResponseForm, EventForm, EventSlotForm
from .models import BookingRequest, Event, EventSlot


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

    query = request.GET.get("q")
    if query:
        events = events.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )

    template = "events/_event_list.html" if request.htmx else "events/listing.html"

    return render(request, template, {
        "events": events,
        "event_types": Event.EventType.choices,
        "current_type": event_type,
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
    return render(request, "events/detail.html", {"event": event})


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
            # Auto-set organizing_creator if user has a creator profile
            if hasattr(request.user, "creator_profile"):
                event.organizing_creator = request.user.creator_profile
            event.save()
            form.save_m2m()
            return redirect("events:detail", slug=event.slug)
    else:
        form = EventForm()

    return render(request, "events/create.html", {"form": form})


@login_required
def edit(request, slug):
    """Edit an event (organizer or manager only)."""
    event = get_object_or_404(Event, slug=slug)
    if not event.can_be_edited_by(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
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

    if request.method == "POST":
        form = EventSlotForm(request.POST, instance=slot, event=event)
        if form.is_valid():
            form.save()
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

    # Split into actionable (pending, received) and other
    received_pending = [r for r in requests_list if r.status == "pending" and r.can_be_responded_to_by(request.user)]
    sent_pending = [r for r in requests_list if r.status == "pending" and not r.can_be_responded_to_by(request.user)]
    resolved = [r for r in requests_list if r.status != "pending"]

    return render(request, "events/booking_inbox.html", {
        "received_pending": received_pending,
        "sent_pending": sent_pending,
        "resolved": resolved,
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

    return render(request, "events/booking_detail.html", {
        "booking": booking,
        "can_respond": can_respond,
        "response_form": response_form,
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
        # Creator is requesting to play at a venue
        venue = get_object_or_404(VenueProfile, slug=profile_slug, publish_status="published")
        creator = getattr(request.user, "creator_profile", None)
        if not creator:
            messages.error(request, "You need a creator profile to send booking requests.")
            return redirect("creators:setup")
        target_name = venue.name
        booking_direction = BookingRequest.Direction.CREATOR_TO_VENUE
    elif direction == "to-creator":
        # Venue is inviting a creator
        creator = get_object_or_404(CreatorProfile, slug=profile_slug, publish_status="published")
        # Find which venue the user manages
        user_venues = list(request.user.venue_profiles.all()) + list(request.user.managed_venue_profiles.all())
        if not user_venues:
            messages.error(request, "You need a venue profile to send booking invitations.")
            return redirect("venues:setup")
        venue = user_venues[0]  # Default to first venue; could add selection if user has multiple
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
    })
