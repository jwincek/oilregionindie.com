"""
Expire pending booking requests older than a specified number of days.

Usage:
    python manage.py expire_bookings           # Expire bookings older than 30 days
    python manage.py expire_bookings --days 14 # Expire bookings older than 14 days
    python manage.py expire_bookings --dry-run # Preview without expiring
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.events.models import BookingRequest


class Command(BaseCommand):
    help = "Expire pending booking requests that have been waiting too long"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Expire bookings older than this many days (default: 30)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be expired without making changes",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["days"])
        pending = BookingRequest.objects.filter(
            status=BookingRequest.Status.PENDING,
            created_at__lt=cutoff,
        ).select_related("creator", "venue")

        count = pending.count()

        if options["dry_run"]:
            self.stdout.write(f"Would expire {count} booking(s) older than {options['days']} days:")
            for booking in pending:
                self.stdout.write(
                    f"  {booking.creator.display_name} & {booking.venue.name} "
                    f"(created {booking.created_at.strftime('%Y-%m-%d')})"
                )
        else:
            pending.update(status=BookingRequest.Status.EXPIRED)
            self.stdout.write(self.style.SUCCESS(
                f"Expired {count} booking(s) older than {options['days']} days."
            ))
