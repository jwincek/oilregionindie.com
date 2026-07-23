from django.conf import settings


def site_settings(request):
    """Make site-wide settings available in all templates."""
    from .models import SiteBranding
    branding = SiteBranding.load(request_or_site=request)
    ctx = {
        "site_branding": branding,
        "SITE_NAME": branding.site_name or getattr(settings, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub"),
        # Canonical absolute base (no trailing slash) for OpenGraph image
        # URLs — matches apps.core.seo.site_url so OG and JSON-LD agree.
        "CANONICAL_BASE_URL": getattr(settings, "WAGTAILADMIN_BASE_URL", "").rstrip("/"),
        "STRIPE_PUBLIC_KEY": getattr(settings, "STRIPE_PUBLIC_KEY", ""),
        "SOFT_LAUNCH": getattr(settings, "SOFT_LAUNCH", False),
        "FEATURE_COMMERCE": getattr(settings, "FEATURE_COMMERCE", True),
        "FEATURE_COMMUNITY": getattr(settings, "FEATURE_COMMUNITY", True),
        "active_theme": branding.active_theme or "default",
    }
    if hasattr(request, "user") and request.user.is_authenticated:
        ctx["unread_notification_count"] = request.user.notifications.filter(
            is_read=False
        ).count()

        # Count pending booking requests needing response
        from django.db.models import Q
        from apps.events.models import BookingRequest
        booking_filters = Q()
        if hasattr(request.user, "creator_profile"):
            booking_filters |= Q(creator=request.user.creator_profile)
        venue_ids = list(request.user.venue_profiles.values_list("pk", flat=True))
        managed_ids = list(request.user.managed_venue_profiles.values_list("pk", flat=True))
        for vid in set(venue_ids + managed_ids):
            booking_filters |= Q(venue_id=vid)
        if booking_filters:
            ctx["pending_booking_count"] = BookingRequest.objects.filter(
                booking_filters, status="pending"
            ).exclude(initiated_by=request.user).distinct().count()
        else:
            ctx["pending_booking_count"] = 0

    return ctx
