import json

from django import template
from django.utils.safestring import mark_safe

from apps.core.seo import structured_data

register = template.Library()


@register.simple_tag
def structured_data_script(obj):
    """Render an object's schema.org JSON-LD as a <script> tag. The
    <, >, & escaping is the same mitigation Django's json_script uses:
    user-controlled names/descriptions can't break out of the script."""
    data = structured_data(obj)
    if not data:
        return ""
    payload = (
        json.dumps(data)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return mark_safe(
        '<script type="application/ld+json">' + payload + "</script>"
    )
