from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def is_demo(obj):
    """Check if an object belongs to a demo/seed account (.example email).
    Works with profiles (have .user) and events (have .created_by).
    Only returns True when SOFT_LAUNCH mode is active."""
    if not getattr(settings, "SOFT_LAUNCH", False):
        return False
    if hasattr(obj, "user") and obj.user:
        return obj.user.email.endswith(".example")
    if hasattr(obj, "created_by") and obj.created_by:
        return obj.created_by.email.endswith(".example")
    if hasattr(obj, "author") and obj.author:
        return obj.author.email.endswith(".example")
    return False


@register.simple_tag
def demo_badge():
    """Render a small 'Demo' badge for sample profiles."""
    return mark_safe(
        '<span class="bg-amber-100 text-amber-700 text-xs font-medium px-1.5 py-0.5 rounded">Demo</span>'
    )
