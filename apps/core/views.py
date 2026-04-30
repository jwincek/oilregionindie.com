from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import Notification, UserProfile


@login_required
def welcome(request):
    """Post-signup interstitial — let the user choose what to do next."""
    # If user already has a creator profile, send them to edit
    if hasattr(request.user, "creator_profile"):
        return redirect("creators:edit")

    return render(request, "core/welcome.html")


# ---------------------------------------------------------------------------
# Follow / Unfollow
# ---------------------------------------------------------------------------


@login_required
@require_POST
def follow_creator(request, slug):
    """Follow or unfollow a creator profile."""
    from apps.creators.models import CreatorProfile
    creator = get_object_or_404(CreatorProfile, slug=slug, publish_status="published")
    profile = request.user.profile

    if profile.followed_creators.filter(pk=creator.pk).exists():
        profile.followed_creators.remove(creator)
        following = False
    else:
        profile.followed_creators.add(creator)
        following = True
        # Create notification for the creator
        Notification.objects.create(
            recipient=creator.user,
            actor=request.user,
            notification_type=Notification.NotificationType.FOLLOW,
            message=f"{profile.get_display_name()} started following you",
            url=creator.get_absolute_url(),
        )

    if request.htmx:
        return render(request, "includes/_follow_button.html", {
            "target": creator,
            "following": following,
            "follow_url_name": "follow_creator",
        })
    return redirect(creator.get_absolute_url())


@login_required
@require_POST
def follow_venue(request, slug):
    """Follow or unfollow a venue profile."""
    from apps.venues.models import VenueProfile
    venue = get_object_or_404(VenueProfile, slug=slug, publish_status="published")
    profile = request.user.profile

    if profile.followed_venues.filter(pk=venue.pk).exists():
        profile.followed_venues.remove(venue)
        following = False
    else:
        profile.followed_venues.add(venue)
        following = True
        Notification.objects.create(
            recipient=venue.user,
            actor=request.user,
            notification_type=Notification.NotificationType.FOLLOW,
            message=f"{profile.get_display_name()} started following {venue.name}",
            url=f"/venues/{venue.slug}/",
        )

    if request.htmx:
        return render(request, "includes/_follow_button.html", {
            "target": venue,
            "following": following,
            "follow_url_name": "follow_venue",
        })
    return redirect(venue.get_absolute_url())


# ---------------------------------------------------------------------------
# Likes
# ---------------------------------------------------------------------------


@login_required
@require_POST
def toggle_like(request, pk):
    """Like or unlike a community post."""
    from apps.community.models import CommunityPost
    post = get_object_or_404(CommunityPost, pk=pk)

    if post.liked_by.filter(pk=request.user.pk).exists():
        post.liked_by.remove(request.user)
        liked = False
    else:
        post.liked_by.add(request.user)
        liked = True
        # Notify the post author (don't notify yourself)
        if post.author != request.user:
            display_name = request.user.profile.get_display_name()
            Notification.objects.create(
                recipient=post.author,
                actor=request.user,
                notification_type=Notification.NotificationType.LIKE,
                message=f"{display_name} liked your post{': ' + post.title if post.title else ''}",
                url=f"/community/{post.pk}/",
            )

    if request.htmx:
        return render(request, "community/_like_button.html", {
            "post": post,
            "liked": liked,
        })
    # Redirect to parent post if this is a reply
    target_pk = post.parent.pk if post.parent else post.pk
    return redirect("community:detail", pk=target_pk)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


@login_required
def notification_inbox(request):
    """Show all notifications for the current user."""
    notifications = request.user.notifications.all()[:50]
    # Mark all as read on view
    unread = request.user.notifications.filter(is_read=False)
    unread_count = unread.count()
    unread.update(is_read=True)

    return render(request, "core/notifications.html", {
        "notifications": notifications,
        "unread_count": unread_count,
    })


@login_required
@require_POST
def mark_all_read(request):
    """Mark all notifications as read."""
    request.user.notifications.filter(is_read=False).update(is_read=True)
    if request.htmx:
        return HttpResponse("")
    return redirect("notifications")


# ---------------------------------------------------------------------------
# Account preferences
# ---------------------------------------------------------------------------


@login_required
def preferences(request):
    """User preferences — digest settings, etc."""
    from django.contrib import messages

    profile = request.user.profile

    if request.method == "POST":
        profile.email_digest = "email_digest" in request.POST
        profile.save(update_fields=["email_digest", "updated_at"])
        messages.success(request, "Preferences saved.")
        return redirect("preferences")

    return render(request, "core/preferences.html", {"profile": profile})


# ---------------------------------------------------------------------------
# Global search
# ---------------------------------------------------------------------------


@require_GET
def search(request):
    """Search across creators, venues, events, and community posts."""
    query = request.GET.get("q", "").strip()

    results = {
        "creators": [],
        "venues": [],
        "events": [],
        "posts": [],
    }

    if query:
        from apps.creators.models import CreatorProfile
        from apps.venues.models import VenueProfile
        from apps.events.models import Event
        from apps.community.models import CommunityPost
        from django.utils import timezone

        results["creators"] = CreatorProfile.objects.filter(
            publish_status="published",
        ).filter(
            Q(display_name__icontains=query)
            | Q(bio__icontains=query)
            | Q(location__icontains=query)
            | Q(disciplines__name__icontains=query)
            | Q(skills__name__icontains=query)
            | Q(genres__name__icontains=query)
        ).distinct()[:8]

        results["venues"] = VenueProfile.objects.filter(
            publish_status="published",
        ).filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(city__icontains=query)
            | Q(amenities__name__icontains=query)
        ).distinct()[:8]

        results["events"] = Event.objects.filter(
            is_published=True,
            start_datetime__gte=timezone.now(),
        ).filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(venue__name__icontains=query)
        ).select_related("venue").distinct()[:8]

        results["posts"] = CommunityPost.objects.filter(
            parent__isnull=True,
        ).filter(
            Q(title__icontains=query)
            | Q(body__icontains=query)
        ).select_related("author")[:8]

    total = sum(len(r) for r in results.values())

    return render(request, "core/search.html", {
        "query": query,
        "results": results,
        "total": total,
    })
