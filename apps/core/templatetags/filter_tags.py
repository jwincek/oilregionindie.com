import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def searchable_options_json(queryset, value_field="slug", label_field="name", group_field=""):
    """Serialize a queryset to JSON for the searchable select Alpine component."""
    options = []
    for obj in queryset:
        label = getattr(obj, label_field, str(obj))
        value = getattr(obj, value_field, "")
        entry = {"value": str(value), "label": str(label)}
        if group_field:
            group = getattr(obj, group_field, None)
            if group:
                entry["label"] = f"{label} ({group})"
        options.append(entry)
    return mark_safe(json.dumps(options))
