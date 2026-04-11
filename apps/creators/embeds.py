"""
Embed rendering pipeline for MediaItem.

Uses Wagtail's embeds module to fetch oEmbed HTML from providers like
YouTube, Vimeo, SoundCloud, and Bandcamp. The HTML is cached in
MediaItem.embed_html to avoid API calls on each page load.

Usage:
    from apps.creators.embeds import refresh_embed

    # On a single item:
    refresh_embed(media_item)

    # Called automatically on save via signal (see signals.py)
"""

import logging

from wagtail.embeds import embeds as wagtail_embeds
from wagtail.embeds.exceptions import EmbedException

logger = logging.getLogger(__name__)

# Providers that return audio players (need different aspect ratio)
AUDIO_PROVIDERS = {"soundcloud", "bandcamp", "spotify"}


def fetch_embed(url):
    """
    Fetch oEmbed data for a URL via Wagtail's embeds system.
    Returns a dict with html, thumbnail_url, title, provider_name,
    or None if the URL isn't embeddable.
    """
    try:
        embed = wagtail_embeds.get_embed(url, max_width=800)
        return {
            "html": embed.html,
            "thumbnail_url": embed.thumbnail_url or "",
            "title": embed.title or "",
            "provider_name": (embed.provider_name or "").lower(),
            "type": embed.type or "",
        }
    except EmbedException as e:
        logger.warning("Failed to fetch embed for %s: %s", url, e)
        return None
    except Exception as e:
        logger.error("Unexpected error fetching embed for %s: %s", url, e)
        return None


def refresh_embed(media_item):
    """
    Fetch oEmbed HTML for a MediaItem and save it to embed_html.
    Also auto-detects the media_type if it's set to 'embed'.
    Returns True if the embed was fetched successfully.
    """
    if not media_item.embed_url:
        return False

    data = fetch_embed(media_item.embed_url)
    if data is None:
        return False

    media_item.embed_html = data["html"]

    # Auto-detect media type from provider if not explicitly set
    # or if the generic "embed" type was selected
    if media_item.media_type == "embed" or not media_item.media_type:
        provider = data["provider_name"]
        if provider in AUDIO_PROVIDERS:
            media_item.media_type = "audio"
        elif data["type"] == "video" or provider in {"youtube", "vimeo"}:
            media_item.media_type = "video"
        else:
            media_item.media_type = "embed"

    # Save without triggering the signal again
    media_item.save(update_fields=["embed_html", "media_type"])
    return True


def make_responsive(html, provider_name=""):
    """
    Wrap embed HTML in a responsive container.
    Audio embeds (SoundCloud, Bandcamp) get a fixed-height container.
    Video embeds get a 16:9 aspect ratio container.
    """
    if not html:
        return ""

    if provider_name in AUDIO_PROVIDERS:
        # Audio players: fixed height, full width
        return (
            f'<div class="embed-audio w-full">'
            f'{html}'
            f'</div>'
        )
    else:
        # Video: 16:9 responsive
        return (
            f'<div class="embed-video relative w-full" style="padding-bottom:56.25%">'
            f'<div class="absolute inset-0">{html}</div>'
            f'</div>'
        )
