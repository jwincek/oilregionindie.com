from django.conf import settings


def site_settings(request):
    """Make site-wide settings available in all templates."""
    return {
        "SITE_NAME": getattr(settings, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub"),
        "STRIPE_PUBLIC_KEY": getattr(settings, "STRIPE_PUBLIC_KEY", ""),
        "SOFT_LAUNCH": getattr(settings, "SOFT_LAUNCH", False),
    }
