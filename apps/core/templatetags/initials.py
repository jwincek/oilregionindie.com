import hashlib

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Palette of background colors — deterministic per name
_COLORS = [
    ("#1a3a5c", "#e8e0d4"),  # ink-800 / brand-100
    ("#654e15", "#f5f1eb"),  # brand-700 / brand-50
    ("#486581", "#d9e2ec"),  # ink-600 / ink-100
    ("#3f310d", "#e8e0d4"),  # brand-800 / brand-100
    ("#334e68", "#d9e2ec"),  # ink-700 / ink-100
    ("#8a6c1f", "#f5f1eb"),  # brand-600 / brand-50
    ("#0d1f2d", "#bcccdc"),  # ink-900 / ink-200
    ("#b08a2a", "#f5f1eb"),  # brand-500 / brand-50
]


def _get_initials(name):
    """Extract up to 2 initials from a display name."""
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    elif parts:
        return parts[0][0].upper()
    return "?"


def _pick_color(name):
    """Deterministic color from the name so it's consistent across renders."""
    index = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(_COLORS)
    return _COLORS[index]


@register.simple_tag
def initials_avatar(name, size=64):
    """Render an inline SVG initials avatar."""
    initials = _get_initials(name)
    bg, fg = _pick_color(name)
    font_size = round(size * 0.4)

    return mark_safe(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'<rect width="{size}" height="{size}" rx="{size // 2}" fill="{bg}"/>'
        f'<text x="50%" y="50%" dy=".1em" fill="{fg}" font-family="system-ui, sans-serif" '
        f'font-size="{font_size}" font-weight="600" text-anchor="middle" dominant-baseline="central">'
        f'{initials}</text></svg>'
    )
