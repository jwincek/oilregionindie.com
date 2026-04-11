from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .forms import EventForm
from .models import Event


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
