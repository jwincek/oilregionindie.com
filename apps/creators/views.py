from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.core.models import AvailabilityType
from apps.core.notifications import notify_admin_profile_submitted

from .forms import CreatorProfileForm, CreatorSocialLinkForm, MediaItemForm
from .models import CreatorProfile, CreatorSocialLink, Discipline, Genre, MediaItem, Skill


@require_GET
def directory(request):
    """Browsable creator directory with filtering."""
    creators = CreatorProfile.objects.filter(publish_status="published").prefetch_related(
        "disciplines", "genres", "skills", "availabilities__availability_type"
    )

    # Filter by profile type (individual, band, collective)
    profile_type = request.GET.get("profile_type")
    if profile_type:
        creators = creators.filter(profile_type=profile_type)

    # Filter by discipline
    discipline_slug = request.GET.get("discipline")
    if discipline_slug:
        creators = creators.filter(disciplines__slug=discipline_slug)

    # Filter by skill
    skill_slug = request.GET.get("skill")
    if skill_slug:
        creators = creators.filter(skills__slug=skill_slug)

    # Filter by genre
    genre_slug = request.GET.get("genre")
    if genre_slug:
        creators = creators.filter(genres__slug=genre_slug)

    # Filter by availability
    availability_slug = request.GET.get("availability")
    if availability_slug:
        creators = creators.filter(
            availabilities__availability_type__slug=availability_slug,
            availabilities__is_active=True,
        )

    # Filter by location
    location = request.GET.get("location")
    if location:
        creators = creators.filter(
            Q(location__icontains=location) | Q(home_region__icontains=location)
        )

    # Search — Wagtail full-text search with ORM fallback
    query = request.GET.get("q")
    if query:
        creators = creators.distinct()
        from wagtail.search.backends import get_search_backend
        try:
            search_results = get_search_backend().search(query, creators)
            if len(search_results) > 0:
                creators = search_results
            else:
                creators = creators.filter(
                    Q(display_name__icontains=query) | Q(bio__icontains=query)
                    | Q(location__icontains=query) | Q(home_region__icontains=query)
                )
        except Exception:
            creators = creators.filter(
                Q(display_name__icontains=query) | Q(bio__icontains=query)
                | Q(location__icontains=query) | Q(home_region__icontains=query)
            )
    else:
        creators = creators.distinct()
    disciplines = Discipline.objects.prefetch_related("skills").all()
    from apps.creators.models import Genre
    genres = Genre.objects.all()
    availability_types = AvailabilityType.for_creators()

    # Build skills list — if a discipline is selected, show only its skills
    if discipline_slug:
        available_skills = Skill.objects.filter(discipline__slug=discipline_slug)
    else:
        available_skills = Skill.objects.select_related("discipline").all()

    # Resolve labels for searchable selects
    current_skill_label = ""
    if skill_slug:
        s = Skill.objects.filter(slug=skill_slug).select_related("discipline").first()
        if s:
            current_skill_label = f"{s.name} ({s.discipline.name})" if not discipline_slug else s.name

    current_genre_label = ""
    if genre_slug:
        g = Genre.objects.filter(slug=genre_slug).first()
        if g:
            current_genre_label = g.name

    template = "creators/_creator_list.html" if request.htmx else "creators/directory.html"

    return render(request, template, {
        "creators": creators,
        "disciplines": disciplines,
        "available_skills": available_skills,
        "genres": genres,
        "availability_types": availability_types,
        "profile_types": CreatorProfile.ProfileType.choices,
        "current_profile_type": profile_type,
        "current_discipline": discipline_slug,
        "current_skill": skill_slug,
        "current_skill_label": current_skill_label,
        "current_genre": genre_slug,
        "current_genre_label": current_genre_label,
        "current_availability": availability_slug,
        "current_location": location or "",
        "query": query or "",
    })


@require_GET
def detail(request, slug):
    """Individual creator profile page. Owners can preview unpublished profiles."""
    creator = get_object_or_404(
        CreatorProfile.objects.prefetch_related(
            "disciplines", "genres", "skills__discipline",
            "media_items", "products",
            "members__member__disciplines",
            "memberships__group",
        ),
        slug=slug,
    )

    # Only published profiles are visible to the public
    if not creator.is_published and not creator.can_be_edited_by(request.user):
        from django.http import Http404
        raise Http404

    is_following = (
        request.user.is_authenticated
        and hasattr(request.user, "profile")
        and request.user.profile.followed_creators.filter(pk=creator.pk).exists()
    )

    from apps.events.models import Event
    upcoming_events = Event.objects.filter(
        is_published=True,
        start_datetime__gte=timezone.now(),
        creators=creator,
    ).select_related("venue").order_by("start_datetime")[:5]

    is_accepting_bookings = creator.availabilities.filter(
        availability_type__slug="available-for-booking",
        is_active=True,
    ).exists()

    # Similar creators — share disciplines or skills
    similar_creators = CreatorProfile.objects.filter(
        publish_status="published",
    ).filter(
        Q(disciplines__in=creator.disciplines.all()) |
        Q(skills__in=creator.skills.all())
    ).exclude(pk=creator.pk).distinct()[:4]

    return render(request, "creators/detail.html", {
        "creator": creator,
        "is_preview": not creator.is_published,
        "is_following": is_following,
        "upcoming_events": upcoming_events,
        "is_accepting_bookings": is_accepting_bookings,
        "similar_creators": similar_creators,
    })


@require_GET
def profile_events(request, slug):
    """HTMX partial — upcoming or past events for a creator profile."""
    from apps.events.models import Event

    creator = get_object_or_404(CreatorProfile, slug=slug, publish_status="published")
    show = request.GET.get("show", "upcoming")

    if show == "past":
        events = Event.objects.filter(
            is_published=True,
            start_datetime__lt=timezone.now(),
            creators=creator,
        ).select_related("venue").order_by("-start_datetime")[:10]
    else:
        events = Event.objects.filter(
            is_published=True,
            start_datetime__gte=timezone.now(),
            creators=creator,
        ).select_related("venue").order_by("start_datetime")[:5]

    return render(request, "creators/_profile_events.html", {
        "events": events,
        "creator": creator,
        "show": show,
    })


@login_required
def setup(request):
    """Initial profile setup after registration."""
    if hasattr(request.user, "creator_profile"):
        return redirect("creators:edit")

    if request.method == "POST":
        form = CreatorProfileForm(request.POST, request.FILES)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            form.save_m2m()
            # Sync disciplines from selected skills
            profile.sync_disciplines_from_skills()
            return redirect("creators:detail", slug=profile.slug)
    else:
        form = CreatorProfileForm()

    import json
    from django.utils.safestring import mark_safe

    skill_options = json.dumps([
        {"value": str(s.pk), "label": f"{s.name} ({s.discipline.name})"}
        for s in Skill.objects.select_related("discipline").order_by("discipline__name", "name")
    ])
    genre_options = json.dumps([
        {"value": str(g.pk), "label": g.name}
        for g in Genre.objects.order_by("name")
    ])

    return render(request, "creators/setup.html", {
        "form": form,
        "skill_options_json": mark_safe(skill_options.replace('"', "'")),
        "genre_options_json": mark_safe(genre_options.replace('"', "'")),
    })


@login_required
def edit(request):
    """Edit existing creator profile."""
    profile = get_object_or_404(CreatorProfile, user=request.user)

    if request.method == "POST":
        form = CreatorProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("creators:detail", slug=profile.slug)
    else:
        form = CreatorProfileForm(instance=profile)

    import json as _json
    from django.utils.safestring import mark_safe as _mark_safe

    skill_options = _json.dumps([
        {"value": str(s.pk), "label": f"{s.name} ({s.discipline.name})"}
        for s in Skill.objects.select_related("discipline").order_by("discipline__name", "name")
    ])
    genre_options = _json.dumps([
        {"value": str(g.pk), "label": g.name}
        for g in Genre.objects.order_by("name")
    ])
    selected_skills = _json.dumps([str(pk) for pk in profile.skills.values_list("pk", flat=True)])
    selected_genres = _json.dumps([str(pk) for pk in profile.genres.values_list("pk", flat=True)])

    return render(request, "creators/edit.html", {
        "form": form,
        "profile": profile,
        "skill_options_json": _mark_safe(skill_options.replace('"', "'")),
        "genre_options_json": _mark_safe(genre_options.replace('"', "'")),
        "selected_skills_json": _mark_safe(selected_skills.replace('"', "'")),
        "selected_genres_json": _mark_safe(selected_genres.replace('"', "'")),
    })


@login_required
@require_POST
def submit_for_review(request):
    """Submit creator profile for admin review."""
    profile = get_object_or_404(CreatorProfile, user=request.user)

    if profile.publish_status == "published":
        messages.info(request, "Your profile is already published.")
    elif profile.publish_status == "pending":
        messages.info(request, "Your profile is already pending review.")
    else:
        profile.publish_status = "pending"
        profile.submitted_at = timezone.now()
        profile.save(update_fields=["publish_status", "submitted_at", "updated_at"])
        notify_admin_profile_submitted(profile)
        messages.success(request, "Your profile has been submitted for review.")

    return redirect("creators:edit")


@login_required
def media_items(request):
    """List media items for the current user's profile (HTMX partial)."""
    profile = get_object_or_404(CreatorProfile, user=request.user)
    return render(request, "creators/_media_items.html", {
        "profile": profile,
        "items": profile.media_items.all(),
    })


@login_required
def add_media(request):
    """Add a media item to the creator's profile."""
    profile = get_object_or_404(CreatorProfile, user=request.user)

    if request.method == "POST":
        form = MediaItemForm(request.POST, request.FILES)
        if form.is_valid():
            media = form.save(commit=False)
            media.creator = profile
            media.save()
            if request.htmx:
                return render(request, "creators/_media_items.html", {
                    "profile": profile,
                    "items": profile.media_items.all(),
                })
            return redirect("creators:edit")
    else:
        form = MediaItemForm()

    if request.htmx:
        return render(request, "creators/_media_form.html", {"form": form})
    return render(request, "creators/add_media.html", {"form": form})


@login_required
def edit_media(request, pk):
    """Edit a media item via HTMX."""
    profile = get_object_or_404(CreatorProfile, user=request.user)
    item = get_object_or_404(MediaItem, pk=pk, creator=profile)

    if request.method == "POST":
        form = MediaItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            return render(request, "creators/_media_items.html", {
                "profile": profile,
                "items": profile.media_items.all(),
            })
    else:
        form = MediaItemForm(instance=item)

    return render(request, "creators/_media_form.html", {
        "form": form,
        "item": item,
    })


@login_required
@require_POST
def delete_media(request, pk):
    """Delete a media item via HTMX."""
    profile = get_object_or_404(CreatorProfile, user=request.user)
    item = get_object_or_404(MediaItem, pk=pk, creator=profile)
    item.delete()
    return render(request, "creators/_media_items.html", {
        "profile": profile,
        "items": profile.media_items.all(),
    })


# ---------------------------------------------------------------------------
# Social links (HTMX-powered add/edit/delete)
# ---------------------------------------------------------------------------


@login_required
def social_links(request):
    """List social links for the current user's profile (HTMX partial)."""
    profile = get_object_or_404(CreatorProfile, user=request.user)
    return render(request, "creators/_social_links.html", {
        "profile": profile,
        "links": profile.social_links.all(),
    })


@login_required
def add_social_link(request):
    """Add a social link via HTMX."""
    profile = get_object_or_404(CreatorProfile, user=request.user)

    if request.method == "POST":
        form = CreatorSocialLinkForm(request.POST)
        if form.is_valid():
            link = form.save(commit=False)
            link.creator = profile
            link.save()
            # Return the full link list so the UI updates
            return render(request, "creators/_social_links.html", {
                "profile": profile,
                "links": profile.social_links.all(),
            })
    else:
        form = CreatorSocialLinkForm()

    return render(request, "creators/_social_link_form.html", {
        "form": form,
        "action_url": "creators:add_social_link",
    })


@login_required
def edit_social_link(request, pk):
    """Edit an existing social link via HTMX."""
    profile = get_object_or_404(CreatorProfile, user=request.user)
    link = get_object_or_404(CreatorSocialLink, pk=pk, creator=profile)

    if request.method == "POST":
        form = CreatorSocialLinkForm(request.POST, instance=link)
        if form.is_valid():
            form.save()
            return render(request, "creators/_social_links.html", {
                "profile": profile,
                "links": profile.social_links.all(),
            })
    else:
        form = CreatorSocialLinkForm(instance=link)

    return render(request, "creators/_social_link_form.html", {
        "form": form,
        "action_url": "creators:edit_social_link",
        "link": link,
    })


@login_required
@require_POST
def delete_social_link(request, pk):
    """Delete a social link via HTMX."""
    profile = get_object_or_404(CreatorProfile, user=request.user)
    link = get_object_or_404(CreatorSocialLink, pk=pk, creator=profile)
    link.delete()
    return render(request, "creators/_social_links.html", {
        "profile": profile,
        "links": profile.social_links.all(),
    })
