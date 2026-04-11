from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from apps.core.models import AvailabilityType

from .forms import VenueProfileForm
from .models import VenueProfile


@require_GET
def directory(request):
    """Browsable venue directory."""
    venues = VenueProfile.objects.filter(is_published=True).prefetch_related(
        "amenities", "availabilities__availability_type"
    )

    venue_type = request.GET.get("type")
    if venue_type:
        venues = venues.filter(venue_type=venue_type)

    amenity = request.GET.get("amenity")
    if amenity:
        venues = venues.filter(amenities__slug=amenity)

    availability_slug = request.GET.get("availability")
    if availability_slug:
        venues = venues.filter(
            availabilities__availability_type__slug=availability_slug,
            availabilities__is_active=True,
        )

    location = request.GET.get("location")
    if location:
        venues = venues.filter(
            Q(city__icontains=location) | Q(state__icontains=location)
        )

    query = request.GET.get("q")
    if query:
        venues = venues.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

    venues = venues.distinct()
    availability_types = AvailabilityType.for_venues()

    template = "venues/_venue_list.html" if request.htmx else "venues/directory.html"

    return render(request, template, {
        "venues": venues,
        "venue_types": VenueProfile.VenueType.choices,
        "availability_types": availability_types,
        "current_type": venue_type,
        "current_availability": availability_slug,
        "query": query or "",
    })


@require_GET
def detail(request, slug):
    """Individual venue profile page."""
    venue = get_object_or_404(
        VenueProfile.objects.prefetch_related("events", "amenities", "social_links"),
        slug=slug,
        is_published=True,
    )
    return render(request, "venues/detail.html", {"venue": venue})


@login_required
def setup(request):
    """Create a new venue profile. A user can create multiple venues."""
    if request.method == "POST":
        form = VenueProfileForm(request.POST, request.FILES)
        if form.is_valid():
            venue = form.save(commit=False)
            venue.user = request.user
            venue.save()
            form.save_m2m()
            return redirect("venues:detail", slug=venue.slug)
    else:
        form = VenueProfileForm()

    return render(request, "venues/setup.html", {"form": form})


@login_required
def edit(request, slug):
    """Edit a venue profile (owner or manager only)."""
    venue = get_object_or_404(VenueProfile, slug=slug)

    if not venue.can_be_edited_by(request.user):
        return HttpResponseForbidden()

    if request.method == "POST":
        form = VenueProfileForm(request.POST, request.FILES, instance=venue)
        if form.is_valid():
            form.save()
            return redirect("venues:detail", slug=venue.slug)
    else:
        form = VenueProfileForm(instance=venue)

    return render(request, "venues/edit.html", {"form": form, "venue": venue})
