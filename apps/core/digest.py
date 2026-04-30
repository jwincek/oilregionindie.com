"""
Email digest compilation — gathers recent activity for a user's followed
creators and venues, and sends a summary email.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from .models import UserProfile


def compile_digest(user_profile, since):
    """
    Gather recent activity for a user's followed creators and venues.
    Returns a dict of activity sections, or None if there's nothing to report.
    """
    from apps.community.models import CommunityPost
    from apps.events.models import Event

    followed_creators = user_profile.followed_creators.all()
    followed_venues = user_profile.followed_venues.all()

    if not followed_creators.exists() and not followed_venues.exists():
        return None

    # New events from followed venues or featuring followed creators
    new_events = Event.objects.filter(
        is_published=True,
        created_at__gte=since,
    ).filter(
        Q(venue__in=followed_venues) | Q(creators__in=followed_creators)
    ).select_related("venue").distinct()[:10]

    # Community posts from followed creators' users
    followed_user_ids = list(followed_creators.values_list("user_id", flat=True))
    new_posts = CommunityPost.objects.filter(
        author_id__in=followed_user_ids,
        parent__isnull=True,
        created_at__gte=since,
    ).select_related("author")[:10]

    # Upcoming events at followed venues (next 14 days)
    upcoming_cutoff = timezone.now() + timedelta(days=14)
    upcoming_events = Event.objects.filter(
        is_published=True,
        venue__in=followed_venues,
        start_datetime__gte=timezone.now(),
        start_datetime__lte=upcoming_cutoff,
    ).select_related("venue").order_by("start_datetime")[:5]

    if not new_events.exists() and not new_posts.exists() and not upcoming_events.exists():
        return None

    return {
        "new_events": new_events,
        "new_posts": new_posts,
        "upcoming_events": upcoming_events,
        "followed_creators": followed_creators,
        "followed_venues": followed_venues,
    }


def send_digest(user_profile, since=None):
    """
    Compile and send a digest email to a single user.
    Returns True if sent, False if nothing to report.
    """
    if since is None:
        since = timezone.now() - timedelta(days=7)

    activity = compile_digest(user_profile, since)
    if not activity:
        return False

    site_name = getattr(settings, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub")
    subject = f"[{site_name}] Your weekly digest"

    context = {
        "user_profile": user_profile,
        "site_name": site_name,
        **activity,
    }
    text_body = render_to_string("core/emails/digest.txt", context)

    send_mail(
        subject=subject,
        message=text_body,
        from_email=None,
        recipient_list=[user_profile.user.email],
        fail_silently=True,
    )
    return True


def send_all_digests(since=None):
    """
    Send digest emails to all users who have email_digest enabled
    and are following at least one creator or venue.
    Returns (sent_count, skipped_count).
    """
    if since is None:
        since = timezone.now() - timedelta(days=7)

    profiles = UserProfile.objects.filter(
        email_digest=True,
    ).select_related("user").prefetch_related(
        "followed_creators", "followed_venues"
    )

    sent = 0
    skipped = 0

    for profile in profiles:
        if send_digest(profile, since):
            sent += 1
        else:
            skipped += 1

    return sent, skipped
