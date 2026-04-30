"""
Send weekly email digests to users who follow creators or venues.

Usage:
    python manage.py send_digests              # Send digests for the last 7 days
    python manage.py send_digests --days 3     # Send digests for the last 3 days
    python manage.py send_digests --dry-run    # Preview without sending
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.digest import compile_digest, send_all_digests
from apps.core.models import UserProfile


class Command(BaseCommand):
    help = "Send weekly email digests to users following creators or venues"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days of activity to include (default: 7)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview digest counts without sending emails",
        )

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(days=options["days"])
        self.stdout.write(
            f"Compiling digests for activity since {since.strftime('%Y-%m-%d %H:%M')}..."
        )

        if options["dry_run"]:
            profiles = UserProfile.objects.filter(
                email_digest=True,
            ).select_related("user").prefetch_related(
                "followed_creators", "followed_venues"
            )
            would_send = 0
            would_skip = 0
            for profile in profiles:
                activity = compile_digest(profile, since)
                if activity:
                    event_count = activity["new_events"].count() if activity["new_events"] else 0
                    post_count = activity["new_posts"].count() if activity["new_posts"] else 0
                    upcoming_count = activity["upcoming_events"].count() if activity["upcoming_events"] else 0
                    self.stdout.write(
                        f"  {profile.user.email}: "
                        f"{event_count} new events, {post_count} posts, "
                        f"{upcoming_count} upcoming"
                    )
                    would_send += 1
                else:
                    would_skip += 1

            self.stdout.write(self.style.SUCCESS(
                f"\nDry run: would send {would_send}, skip {would_skip}"
            ))
        else:
            sent, skipped = send_all_digests(since)
            self.stdout.write(self.style.SUCCESS(
                f"Done: sent {sent} digests, skipped {skipped} (no activity)"
            ))
