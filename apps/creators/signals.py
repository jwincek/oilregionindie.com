import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="creators.MediaItem")
def fetch_embed_on_save(sender, instance, created, update_fields, **kwargs):
    """
    When a MediaItem is saved with an embed_url and no cached embed_html,
    fetch the oEmbed HTML from the provider.

    Skips if:
    - No embed_url is set
    - embed_html is already populated (manually pasted or previously fetched)
    - This save was triggered by refresh_embed itself (update_fields check)
    """
    # Avoid recursion: refresh_embed() saves with update_fields
    if update_fields and "embed_html" in update_fields:
        return

    if not instance.embed_url:
        return

    if instance.embed_html:
        # Already has embed HTML — either manually pasted or previously fetched.
        # Don't overwrite. Users can manually refresh via admin action or
        # the refresh_embeds management command.
        return

    # Import here to avoid circular imports
    from apps.creators.embeds import refresh_embed

    try:
        success = refresh_embed(instance)
        if success:
            logger.info("Fetched embed for MediaItem %s: %s", instance.pk, instance.embed_url)
        else:
            logger.warning("Could not fetch embed for MediaItem %s: %s", instance.pk, instance.embed_url)
    except Exception as e:
        logger.error("Error fetching embed for MediaItem %s: %s", instance.pk, e)
