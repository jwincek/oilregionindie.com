import json
from urllib.parse import urlencode

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


@register.simple_tag
def searchable_select_data(options_json, current_value="", current_label=""):
    """Render the full x-data attribute value for a searchable select.
    Uses single quotes throughout to avoid conflicts with the HTML
    attribute's double quotes."""
    # Convert JSON double quotes to single quotes for embedding in HTML attribute
    options_str = str(options_json).replace('"', "'")
    safe_label = (current_label or "").replace("'", "\\'")
    safe_value = (current_value or "").replace("'", "\\'")
    return mark_safe(
        f"searchableSelect({{options: {options_str}, "
        f"selectedValue: '{safe_value}', "
        f"selectedLabel: '{safe_label}'}})"
    )


@register.simple_tag(takes_context=True)
def url_without_param(context, base_url, exclude_param):
    """Build a URL with all current GET params except the excluded one."""
    request = context.get("request")
    if not request:
        return base_url
    params = {k: v for k, v in request.GET.items() if k != exclude_param and v}
    if params:
        return f"{base_url}?{urlencode(params)}"
    return base_url
