from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def turnstile_script():
    """Render the Cloudflare Turnstile script tag. Outputs nothing if not configured."""
    if not getattr(settings, "TURNSTILE_SITE_KEY", ""):
        return ""
    return mark_safe(
        '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>'
    )


@register.simple_tag
def turnstile_widget():
    """Render the Turnstile widget div. Outputs nothing if not configured."""
    site_key = getattr(settings, "TURNSTILE_SITE_KEY", "")
    if not site_key:
        return ""
    return mark_safe(
        f'<div class="cf-turnstile" data-sitekey="{site_key}" '
        f'data-callback="onTurnstileSuccess" data-theme="light"></div>\n'
        f'<script>function onTurnstileSuccess(token) {{\n'
        f'  document.querySelector(\'[name="cf_turnstile_response"]\').value = token;\n'
        f'}}</script>'
    )
