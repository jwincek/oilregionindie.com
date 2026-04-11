from django import template
from django.utils.safestring import mark_safe

from apps.creators.embeds import AUDIO_PROVIDERS, make_responsive

register = template.Library()


@register.filter
def render_embed(media_item):
    """
    Render a MediaItem's embed HTML in a responsive container.
    Uses cached embed_html if available, otherwise shows the raw URL as a link.

    Usage: {{ item|render_embed }}
    """
    if media_item.embed_html:
        # Detect provider from the HTML content for responsive wrapping
        html = media_item.embed_html
        provider = ""
        for audio_provider in AUDIO_PROVIDERS:
            if audio_provider in html.lower():
                provider = audio_provider
                break
        return mark_safe(make_responsive(html, provider))

    if media_item.embed_url:
        # Fallback: show as a link if embed fetch hasn't happened yet
        url = media_item.embed_url
        return mark_safe(
            f'<a href="{url}" target="_blank" rel="noopener" '
            f'class="text-brand-600 hover:underline text-sm">'
            f'{url}</a>'
        )

    return ""
