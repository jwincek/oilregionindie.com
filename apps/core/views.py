from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import ProfileAvailabilityForm
from .models import Notification, ProfileAvailability, Report, UserProfile


def suspended(request):
    """Page shown to suspended users."""
    return render(request, "core/suspended.html")


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
# Availability management (HTMX)
# ---------------------------------------------------------------------------


def _get_availability_context(profile, profile_type):
    """Build context for availability HTMX partials."""
    return {
        "profile": profile,
        "availabilities": profile.availabilities.select_related("availability_type").all(),
        "profile_type": profile_type,
    }


@login_required
def availability_list(request, profile_type, slug):
    """List availability flags for a profile (HTMX partial)."""
    profile = _get_editable_profile(request, profile_type, slug)
    if profile is None:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    return render(request, "includes/_availability_list.html",
                  _get_availability_context(profile, profile_type))


@login_required
def add_availability(request, profile_type, slug):
    """Add an availability flag via HTMX."""
    profile = _get_editable_profile(request, profile_type, slug)
    if profile is None:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    if request.method == "POST":
        form = ProfileAvailabilityForm(request.POST, profile_type=profile_type)
        if form.is_valid():
            avail = form.save(commit=False)
            if profile_type == "creator":
                avail.creator = profile
            else:
                avail.venue = profile
            avail.save()
            return render(request, "includes/_availability_list.html",
                          _get_availability_context(profile, profile_type))
    else:
        form = ProfileAvailabilityForm(profile_type=profile_type)

    return render(request, "includes/_availability_form.html", {
        "form": form,
        "profile": profile,
        "profile_type": profile_type,
    })


@login_required
def edit_availability(request, profile_type, slug, pk):
    """Edit an availability flag via HTMX."""
    profile = _get_editable_profile(request, profile_type, slug)
    if profile is None:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    avail = get_object_or_404(ProfileAvailability, pk=pk)

    if request.method == "POST":
        form = ProfileAvailabilityForm(request.POST, instance=avail, profile_type=profile_type)
        if form.is_valid():
            form.save()
            return render(request, "includes/_availability_list.html",
                          _get_availability_context(profile, profile_type))
    else:
        form = ProfileAvailabilityForm(instance=avail, profile_type=profile_type)

    return render(request, "includes/_availability_form.html", {
        "form": form,
        "profile": profile,
        "profile_type": profile_type,
        "avail": avail,
    })


@login_required
@require_POST
def delete_availability(request, profile_type, slug, pk):
    """Remove an availability flag via HTMX."""
    profile = _get_editable_profile(request, profile_type, slug)
    if profile is None:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    avail = get_object_or_404(ProfileAvailability, pk=pk)
    avail.delete()
    return render(request, "includes/_availability_list.html",
                  _get_availability_context(profile, profile_type))


def _get_editable_profile(request, profile_type, slug):
    """Get a creator or venue profile the user can edit."""
    if profile_type == "creator":
        from apps.creators.models import CreatorProfile
        profile = get_object_or_404(CreatorProfile, slug=slug)
    else:
        from apps.venues.models import VenueProfile
        profile = get_object_or_404(VenueProfile, slug=slug)
    if not profile.can_be_edited_by(request.user):
        return None
    return profile


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


@login_required
@require_POST
def delete_account(request):
    """Delete the current user's account and all associated data."""
    from django.contrib.auth import logout as auth_logout
    from django.contrib import messages as msg

    confirmation = request.POST.get("confirm", "")
    if confirmation != "DELETE":
        msg.error(request, 'Please type "DELETE" to confirm account deletion.')
        return redirect("preferences")

    user = request.user
    auth_logout(request)
    user.delete()

    return render(request, "core/account_deleted.html")


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

        # Wagtail full-text search for indexed models (with ORM fallback)
        from wagtail.search.backends import get_search_backend
        backend = get_search_backend()

        creator_qs = CreatorProfile.objects.filter(publish_status="published")
        try:
            cr = backend.search(query, creator_qs)
            results["creators"] = cr[:8] if len(cr) > 0 else creator_qs.filter(
                Q(display_name__icontains=query) | Q(bio__icontains=query) | Q(location__icontains=query)
            ).distinct()[:8]
        except Exception:
            results["creators"] = creator_qs.filter(
                Q(display_name__icontains=query) | Q(bio__icontains=query)
            ).distinct()[:8]

        venue_qs = VenueProfile.objects.filter(publish_status="published")
        try:
            vr = backend.search(query, venue_qs)
            results["venues"] = vr[:8] if len(vr) > 0 else venue_qs.filter(
                Q(name__icontains=query) | Q(description__icontains=query) | Q(city__icontains=query)
            ).distinct()[:8]
        except Exception:
            results["venues"] = venue_qs.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            ).distinct()[:8]

        event_qs = Event.objects.filter(is_published=True, start_datetime__gte=timezone.now())
        try:
            er = backend.search(query, event_qs)
            results["events"] = er[:8] if len(er) > 0 else event_qs.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            ).select_related("venue").distinct()[:8]
        except Exception:
            results["events"] = event_qs.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            ).select_related("venue").distinct()[:8]

        # Community posts aren't Wagtail-indexed, use ORM search
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


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


@login_required
@require_POST
def report_content(request):
    """Submit a report about problematic content."""
    from django.contrib import messages as msg

    content_type = request.POST.get("content_type", "")
    content_id = request.POST.get("content_id", "")
    content_url = request.POST.get("content_url", "")
    reason = request.POST.get("reason", "").strip()

    if not reason or not content_type or not content_id:
        msg.error(request, "Please provide a reason for your report.")
        return redirect(content_url or "/")

    Report.objects.create(
        reporter=request.user,
        content_type=content_type,
        content_id=content_id,
        content_url=content_url,
        reason=reason,
    )

    # Notify admins
    from apps.core.notifications import notify_admin_profile_submitted
    from django.conf import settings as conf
    from django.core.mail import send_mail

    admin_emails = [email for _, email in getattr(conf, "ADMINS", [])]
    if admin_emails:
        site_name = getattr(conf, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub")
        send_mail(
            subject=f"[{site_name}] New {content_type} report",
            message=f"A {content_type} has been reported.\n\nReason: {reason}\n\nURL: {content_url}",
            from_email=None,
            recipient_list=admin_emails,
            fail_silently=True,
        )

    msg.success(request, "Thank you. Your report has been submitted and will be reviewed.")
    return redirect(content_url or "/")


# ---------------------------------------------------------------------------
# Feedback form
# ---------------------------------------------------------------------------


@require_POST
def submit_feedback(request):
    """Handle inline feedback form submission from the feedback page."""
    from django.contrib import messages as msg
    from django.conf import settings as conf
    from django.core.mail import send_mail

    feedback_type = request.POST.get("feedback_type", "general")
    body = request.POST.get("body", "").strip()
    email = request.POST.get("email", "").strip()

    if not body:
        msg.error(request, "Please describe your feedback.")
        return redirect("/feedback/")

    sender = email or (request.user.email if request.user.is_authenticated else "anonymous")

    # Store as a report for the admin queue
    Report.objects.create(
        reporter=request.user if request.user.is_authenticated else None,
        content_type="user",
        content_id="feedback",
        content_url="/feedback/",
        reason=f"[{feedback_type.upper()}] {body}\n\nFrom: {sender}",
    )

    # Email admins
    admin_emails = [e for _, e in getattr(conf, "ADMINS", [])]
    if admin_emails:
        site_name = getattr(conf, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub")
        send_mail(
            subject=f"[{site_name}] {feedback_type.title()} feedback",
            message=f"Type: {feedback_type}\nFrom: {sender}\n\n{body}",
            from_email=None,
            recipient_list=admin_emails,
            fail_silently=True,
        )

    msg.success(request, "Thank you for your feedback!")
    return redirect("/feedback/")


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------


@login_required
def admin_dashboard(request):
    """Overview dashboard for site administrators."""
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    from datetime import timedelta
    from django.contrib.auth import get_user_model
    from django.utils import timezone as tz
    from apps.creators.models import CreatorProfile
    from apps.venues.models import VenueProfile
    from apps.events.models import BookingRequest, Event
    from apps.community.models import CommunityPost

    User = get_user_model()
    now = tz.now()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    # Pending reviews
    pending_creators = CreatorProfile.objects.filter(publish_status="pending").select_related("user")
    pending_venues = VenueProfile.objects.filter(publish_status="pending").select_related("user")

    # Open reports
    open_reports = Report.objects.filter(status="pending").order_by("-created_at")[:10]

    # Recent signups
    recent_users = User.objects.order_by("-date_joined")[:10]

    # Key metrics
    metrics = {
        "total_users": User.objects.count(),
        "users_7d": User.objects.filter(date_joined__gte=seven_days_ago).count(),
        "total_creators": CreatorProfile.objects.filter(publish_status="published").count(),
        "total_venues": VenueProfile.objects.filter(publish_status="published").count(),
        "upcoming_events": Event.objects.filter(is_published=True, start_datetime__gte=now).count(),
        "posts_30d": CommunityPost.objects.filter(parent__isnull=True, created_at__gte=thirty_days_ago).count(),
        "pending_bookings": BookingRequest.objects.filter(status="pending").count(),
        "open_reports": Report.objects.filter(status="pending").count(),
    }

    return render(request, "core/admin_dashboard.html", {
        "pending_creators": pending_creators,
        "pending_venues": pending_venues,
        "open_reports": open_reports,
        "recent_users": recent_users,
        "metrics": metrics,
    })
