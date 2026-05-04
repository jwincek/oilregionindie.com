from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.core.models import AvailabilityType
from apps.core.notifications import notify_admin_profile_submitted

from .forms import VenueContactForm, VenueProfileForm, VenueSocialLinkForm
from .models import VenueContact, VenueProfile, VenueSocialLink


@require_GET
def directory(request):
    """Browsable venue directory."""
    venues = VenueProfile.objects.filter(publish_status="published").prefetch_related(
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
        venues = venues.distinct()
        from wagtail.search.backends import get_search_backend
        try:
            search_results = get_search_backend().search(query, venues)
            if len(search_results) > 0:
                venues = search_results
            else:
                venues = venues.filter(
                    Q(name__icontains=query) | Q(description__icontains=query)
                )
        except Exception:
            venues = venues.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            )
    else:
        venues = venues.distinct()
    availability_types = AvailabilityType.for_venues()

    from apps.venues.models import Amenity
    amenities = Amenity.objects.all()

    current_amenity_label = ""
    if amenity:
        a = Amenity.objects.filter(slug=amenity).first()
        if a:
            current_amenity_label = a.name

    template = "venues/_venue_list.html" if request.htmx else "venues/directory.html"

    return render(request, template, {
        "venues": venues,
        "venue_types": VenueProfile.VenueType.choices,
        "availability_types": availability_types,
        "amenities": amenities,
        "current_type": venue_type,
        "current_amenity": amenity,
        "current_amenity_label": current_amenity_label,
        "current_availability": availability_slug,
        "current_location": location or "",
        "query": query or "",
    })


@require_GET
def detail(request, slug):
    """Individual venue profile page. Owners can preview unpublished profiles."""
    venue = get_object_or_404(
        VenueProfile.objects.prefetch_related("events", "amenities", "social_links"),
        slug=slug,
    )

    # Only published profiles are visible to the public
    if not venue.is_published and not venue.can_be_edited_by(request.user):
        from django.http import Http404
        raise Http404

    is_following = (
        request.user.is_authenticated
        and hasattr(request.user, "profile")
        and request.user.profile.followed_venues.filter(pk=venue.pk).exists()
    )

    from apps.events.models import Event
    upcoming_events = Event.objects.filter(
        is_published=True,
        start_datetime__gte=timezone.now(),
        venue=venue,
    ).select_related("venue").prefetch_related(
        "slots__creator"
    ).order_by("start_datetime")[:10]

    is_accepting_bookings = venue.availabilities.filter(
        availability_type__slug="accepting-booking-requests",
        is_active=True,
    ).exists()

    return render(request, "venues/detail.html", {
        "venue": venue,
        "is_preview": not venue.is_published,
        "is_following": is_following,
        "upcoming_events": upcoming_events,
        "is_accepting_bookings": is_accepting_bookings,
    })


@require_GET
def profile_events(request, slug):
    """HTMX partial — upcoming or past events for a venue profile."""
    from apps.events.models import Event

    venue = get_object_or_404(VenueProfile, slug=slug, publish_status="published")
    show = request.GET.get("show", "upcoming")

    if show == "past":
        events = Event.objects.filter(
            is_published=True,
            start_datetime__lt=timezone.now(),
            venue=venue,
        ).select_related("venue").prefetch_related(
            "slots__creator"
        ).order_by("-start_datetime")[:10]
    else:
        events = Event.objects.filter(
            is_published=True,
            start_datetime__gte=timezone.now(),
            venue=venue,
        ).select_related("venue").prefetch_related(
            "slots__creator"
        ).order_by("start_datetime")[:10]

    return render(request, "venues/_profile_events.html", {
        "events": events,
        "venue": venue,
        "show": show,
    })


@login_required
@require_POST
def submit_for_review(request, slug):
    """Submit venue profile for admin review."""
    venue = get_object_or_404(VenueProfile, slug=slug)

    if not venue.can_be_edited_by(request.user):
        return HttpResponseForbidden()

    if venue.publish_status == "published":
        messages.info(request, "This venue is already published.")
    elif venue.publish_status == "pending":
        messages.info(request, "This venue is already pending review.")
    else:
        venue.publish_status = "pending"
        venue.submitted_at = timezone.now()
        venue.save(update_fields=["publish_status", "submitted_at", "updated_at"])
        notify_admin_profile_submitted(venue)
        messages.success(request, "Your venue has been submitted for review.")

    return redirect("venues:edit", slug=venue.slug)


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


# ---------------------------------------------------------------------------
# Social links (HTMX-powered add/edit/delete)
# ---------------------------------------------------------------------------


def _get_editable_venue(request, slug):
    """Get a venue the current user can edit, or 403."""
    venue = get_object_or_404(VenueProfile, slug=slug)
    if not venue.can_be_edited_by(request.user):
        return None, HttpResponseForbidden()
    return venue, None


@login_required
def social_links(request, slug):
    """List social links for a venue (HTMX partial)."""
    venue, err = _get_editable_venue(request, slug)
    if err:
        return err
    return render(request, "venues/_social_links.html", {
        "venue": venue,
        "links": venue.social_links.all(),
    })


@login_required
def add_social_link(request, slug):
    """Add a social link to a venue via HTMX."""
    venue, err = _get_editable_venue(request, slug)
    if err:
        return err

    if request.method == "POST":
        form = VenueSocialLinkForm(request.POST)
        if form.is_valid():
            link = form.save(commit=False)
            link.venue = venue
            link.save()
            return render(request, "venues/_social_links.html", {
                "venue": venue,
                "links": venue.social_links.all(),
            })
    else:
        form = VenueSocialLinkForm()

    return render(request, "venues/_social_link_form.html", {
        "form": form,
        "venue": venue,
    })


@login_required
def edit_social_link(request, slug, pk):
    """Edit a venue social link via HTMX."""
    venue, err = _get_editable_venue(request, slug)
    if err:
        return err
    link = get_object_or_404(VenueSocialLink, pk=pk, venue=venue)

    if request.method == "POST":
        form = VenueSocialLinkForm(request.POST, instance=link)
        if form.is_valid():
            form.save()
            return render(request, "venues/_social_links.html", {
                "venue": venue,
                "links": venue.social_links.all(),
            })
    else:
        form = VenueSocialLinkForm(instance=link)

    return render(request, "venues/_social_link_form.html", {
        "form": form,
        "venue": venue,
        "link": link,
    })


@login_required
@require_POST
def delete_social_link(request, slug, pk):
    """Delete a venue social link via HTMX."""
    venue, err = _get_editable_venue(request, slug)
    if err:
        return err
    link = get_object_or_404(VenueSocialLink, pk=pk, venue=venue)
    link.delete()
    return render(request, "venues/_social_links.html", {
        "venue": venue,
        "links": venue.social_links.all(),
    })


# ---------------------------------------------------------------------------
# Contacts (HTMX-powered add/edit/delete)
# ---------------------------------------------------------------------------


def _contact_context(venue):
    return {"venue": venue, "contacts": venue.contacts.all()}


@login_required
def contacts(request, slug):
    """List contacts for a venue (HTMX partial)."""
    venue, err = _get_editable_venue(request, slug)
    if err:
        return err
    return render(request, "venues/_contacts.html", _contact_context(venue))


@login_required
def add_contact(request, slug):
    """Add a contact to a venue via HTMX."""
    venue, err = _get_editable_venue(request, slug)
    if err:
        return err

    if request.method == "POST":
        form = VenueContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.venue = venue
            contact.save()
            return render(request, "venues/_contacts.html", _contact_context(venue))
    else:
        form = VenueContactForm()

    return render(request, "venues/_contact_form.html", {"form": form, "venue": venue})


@login_required
def edit_contact(request, slug, pk):
    """Edit a venue contact via HTMX."""
    venue, err = _get_editable_venue(request, slug)
    if err:
        return err
    contact = get_object_or_404(VenueContact, pk=pk, venue=venue)

    if request.method == "POST":
        form = VenueContactForm(request.POST, instance=contact)
        if form.is_valid():
            form.save()
            return render(request, "venues/_contacts.html", _contact_context(venue))
    else:
        form = VenueContactForm(instance=contact)

    return render(request, "venues/_contact_form.html", {"form": form, "venue": venue, "contact": contact})


@login_required
@require_POST
def delete_contact(request, slug, pk):
    """Delete a venue contact via HTMX."""
    venue, err = _get_editable_venue(request, slug)
    if err:
        return err
    contact = get_object_or_404(VenueContact, pk=pk, venue=venue)
    contact.delete()
    return render(request, "venues/_contacts.html", _contact_context(venue))
