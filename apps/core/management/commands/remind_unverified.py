"""
Send reminder emails to users who signed up but haven't verified their email.

Usage:
    python manage.py remind_unverified              # Remind users who signed up 24+ hours ago
    python manage.py remind_unverified --hours 48   # Custom threshold
    python manage.py remind_unverified --dry-run    # Preview without sending
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = "Send verification reminder to users who haven't confirmed their email"

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Remind users who signed up more than this many hours ago (default: 24)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview without sending emails",
        )

    def handle(self, *args, **options):
        from allauth.account.models import EmailAddress

        cutoff = timezone.now() - timedelta(hours=options["hours"])
        # Don't remind users who signed up more than 7 days ago — they're probably gone
        max_age = timezone.now() - timedelta(days=7)

        unverified = EmailAddress.objects.filter(
            verified=False,
            user__date_joined__lt=cutoff,
            user__date_joined__gt=max_age,
        ).select_related("user")

        # Exclude users who have any verified email
        verified_user_ids = EmailAddress.objects.filter(
            verified=True,
        ).values_list("user_id", flat=True)
        unverified = unverified.exclude(user_id__in=verified_user_ids)

        count = unverified.count()

        if options["dry_run"]:
            self.stdout.write(f"Would remind {count} user(s):")
            for email_obj in unverified:
                self.stdout.write(f"  {email_obj.email} (joined {email_obj.user.date_joined.strftime('%Y-%m-%d')})")
        else:
            site_name = getattr(settings, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub")
            sent = 0
            for email_obj in unverified:
                send_mail(
                    subject=f"[{site_name}] Don't forget to verify your email",
                    message=(
                        f"Hi!\n\n"
                        f"You signed up for {site_name} but haven't verified your email address yet. "
                        f"Without verification, you won't be able to create a profile or interact with the community.\n\n"
                        f"Check your inbox for the original verification email, or sign in to request a new one.\n\n"
                        f"If you didn't sign up, you can ignore this message.\n\n"
                        f"{site_name}"
                    ),
                    from_email=None,
                    recipient_list=[email_obj.email],
                    fail_silently=True,
                )
                sent += 1

            self.stdout.write(self.style.SUCCESS(f"Sent {sent} reminder(s)."))
