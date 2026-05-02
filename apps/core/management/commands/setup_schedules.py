"""
Set up recurring Django Q schedules for the platform.

Usage:
    python manage.py setup_schedules
"""

from django.core.management.base import BaseCommand
from django_q.models import Schedule


class Command(BaseCommand):
    help = "Create or update recurring Django Q task schedules"

    def handle(self, *args, **options):
        # Weekly email digest — every Monday at 9:00 AM
        schedule, created = Schedule.objects.update_or_create(
            name="weekly-email-digest",
            defaults={
                "func": "apps.core.tasks.send_weekly_digests",
                "schedule_type": Schedule.WEEKLY,
                "repeats": -1,
            },
        )
        status = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f"  [{status}] Weekly email digest schedule"
        ))

        # Daily booking expiration — expire pending bookings older than 30 days
        schedule, created = Schedule.objects.update_or_create(
            name="daily-booking-expiration",
            defaults={
                "func": "apps.events.tasks.expire_old_bookings",
                "schedule_type": Schedule.DAILY,
                "repeats": -1,
            },
        )
        status = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(
            f"  [{status}] Daily booking expiration schedule"
        ))

        self.stdout.write(self.style.SUCCESS("\nSchedules configured."))
        self.stdout.write("Run 'python manage.py qcluster' to start processing.")
