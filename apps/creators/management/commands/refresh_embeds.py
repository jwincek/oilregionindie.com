"""
Fetch oEmbed HTML for all MediaItems that have an embed_url but no cached embed_html.

Usage:
    python manage.py refresh_embeds          # Only items missing embed_html
    python manage.py refresh_embeds --all    # Re-fetch all items with embed_url
"""

from django.core.management.base import BaseCommand

from apps.creators.embeds import refresh_embed
from apps.creators.models import MediaItem


class Command(BaseCommand):
    help = "Fetch oEmbed HTML for MediaItems with embed URLs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Re-fetch all embeds, even ones already cached",
        )

    def handle(self, *args, **options):
        items = MediaItem.objects.exclude(embed_url="")

        if not options["all"]:
            items = items.filter(embed_html="")

        total = items.count()
        if total == 0:
            self.stdout.write("No media items to process.")
            return

        self.stdout.write(f"Processing {total} media items...")

        success = 0
        failed = 0
        for item in items:
            self.stdout.write(f"  [{item.creator.display_name}] {item.title}: {item.embed_url}")
            if refresh_embed(item):
                success += 1
                self.stdout.write(self.style.SUCCESS(f"    ✓ Fetched ({item.media_type})"))
            else:
                failed += 1
                self.stdout.write(self.style.WARNING(f"    ✗ Failed"))

        self.stdout.write(self.style.SUCCESS(
            f"\nDone: {success} fetched, {failed} failed out of {total} total."
        ))
