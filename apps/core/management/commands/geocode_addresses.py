"""
Geocode addresses that don't have coordinates yet.

Usage:
    python manage.py geocode_addresses           # Geocode all pending
    python manage.py geocode_addresses --dry-run # Preview without geocoding
"""

from django.core.management.base import BaseCommand

from apps.core.models import Address


class Command(BaseCommand):
    help = "Geocode addresses without latitude/longitude using OpenStreetMap Nominatim"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview addresses that would be geocoded",
        )

    def handle(self, *args, **options):
        pending = Address.objects.filter(latitude__isnull=True)
        count = pending.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("All addresses have coordinates."))
            return

        if options["dry_run"]:
            self.stdout.write(f"Would geocode {count} address(es):")
            for addr in pending:
                self.stdout.write(f"  {addr.full_display}")
        else:
            from apps.core.geocoding import geocode_all_pending
            self.stdout.write(f"Geocoding {count} address(es)...")
            success, total = geocode_all_pending()
            self.stdout.write(self.style.SUCCESS(
                f"Geocoded {success} of {total} address(es)."
            ))
