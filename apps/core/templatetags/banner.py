import hashlib

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Background + foreground pattern color pairs
_PALETTES = [
    ("#1a3a5c", "#243f5f"),  # ink deep
    ("#334e68", "#3d5a75"),  # ink mid
    ("#654e15", "#755e25"),  # brand warm
    ("#3f310d", "#4f411d"),  # brand deep
    ("#486581", "#527191"),  # ink steel
    ("#0d1f2d", "#172a38"),  # ink darkest
    ("#8a6c1f", "#9a7c2f"),  # brand gold
    ("#1a3a5c", "#2a4a6c"),  # ink blue
]

# SVG pattern generators — each returns the <pattern> + <rect> markup
_PATTERNS = [
    # Diagonal lines
    lambda bg, fg, seed: (
        f'<pattern id="p{seed}" width="10" height="10" patternUnits="userSpaceOnUse" '
        f'patternTransform="rotate(45)">'
        f'<line x1="0" y1="0" x2="0" y2="10" stroke="{fg}" stroke-width="2"/>'
        f'</pattern>'
    ),
    # Dots
    lambda bg, fg, seed: (
        f'<pattern id="p{seed}" width="16" height="16" patternUnits="userSpaceOnUse">'
        f'<circle cx="8" cy="8" r="2" fill="{fg}"/>'
        f'</pattern>'
    ),
    # Crosses
    lambda bg, fg, seed: (
        f'<pattern id="p{seed}" width="20" height="20" patternUnits="userSpaceOnUse">'
        f'<line x1="10" y1="5" x2="10" y2="15" stroke="{fg}" stroke-width="1.5"/>'
        f'<line x1="5" y1="10" x2="15" y2="10" stroke="{fg}" stroke-width="1.5"/>'
        f'</pattern>'
    ),
    # Chevrons
    lambda bg, fg, seed: (
        f'<pattern id="p{seed}" width="16" height="12" patternUnits="userSpaceOnUse">'
        f'<polyline points="0,6 8,0 16,6" fill="none" stroke="{fg}" stroke-width="1.5"/>'
        f'</pattern>'
    ),
    # Horizontal lines
    lambda bg, fg, seed: (
        f'<pattern id="p{seed}" width="10" height="8" patternUnits="userSpaceOnUse">'
        f'<line x1="0" y1="4" x2="10" y2="4" stroke="{fg}" stroke-width="1"/>'
        f'</pattern>'
    ),
    # Diamonds
    lambda bg, fg, seed: (
        f'<pattern id="p{seed}" width="16" height="16" patternUnits="userSpaceOnUse">'
        f'<polygon points="8,2 14,8 8,14 2,8" fill="none" stroke="{fg}" stroke-width="1"/>'
        f'</pattern>'
    ),
]


def _hash_name(name):
    return int(hashlib.md5(name.encode()).hexdigest(), 16)


@register.simple_tag
def banner_pattern(name):
    """Render an inline SVG banner with a deterministic geometric pattern."""
    h = _hash_name(name)
    bg, fg = _PALETTES[h % len(_PALETTES)]
    pattern_fn = _PATTERNS[(h >> 8) % len(_PATTERNS)]
    seed = h % 100000  # Unique ID for this pattern element

    pattern_markup = pattern_fn(bg, fg, seed)

    return mark_safe(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" '
        f'preserveAspectRatio="xMidYMid slice" style="display:block">'
        f'<rect width="100%" height="100%" fill="{bg}"/>'
        f'<defs>{pattern_markup}</defs>'
        f'<rect width="100%" height="100%" fill="url(#p{seed})"/>'
        f'</svg>'
    )
