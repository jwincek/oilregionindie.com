from django.conf import settings


def site_settings(request):
    """Make site-wide settings available in all templates."""
    ctx = {
        "SITE_NAME": getattr(settings, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub"),
        "STRIPE_PUBLIC_KEY": getattr(settings, "STRIPE_PUBLIC_KEY", ""),
        "SOFT_LAUNCH": getattr(settings, "SOFT_LAUNCH", False),
    }
    if hasattr(request, "user") and request.user.is_authenticated:
        ctx["unread_notification_count"] = request.user.notifications.filter(
            is_read=False
        ).count()
    return ctx
