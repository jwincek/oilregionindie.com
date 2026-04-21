from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def is_demo(profile):
    """Check if a profile belongs to a demo/seed account (@example.com email).
    Only returns True when SOFT_LAUNCH mode is active."""
    if not getattr(settings, "SOFT_LAUNCH", False):
        return False
    return hasattr(profile, "user") and profile.user.email.endswith("@example.com")


@register.simple_tag
def demo_badge():
    """Render a small 'Demo' badge for sample profiles."""
    return mark_safe(
        '<span class="bg-amber-100 text-amber-700 text-xs font-medium px-1.5 py-0.5 rounded">Demo</span>'
    )
