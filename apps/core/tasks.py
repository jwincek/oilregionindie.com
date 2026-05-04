"""
Django Q async tasks for the core app.
"""

from apps.core.digest import send_all_digests


def send_weekly_digests():
    """
    Task for Django Q scheduler — sends weekly digests.
    Schedule this via Django Q's Schedule model or admin.
    """
    sent, skipped = send_all_digests()
    return f"Sent {sent} digests, skipped {skipped}"


def remind_unverified_users():
    """
    Task for Django Q scheduler — reminds users who haven't verified
    their email after 24 hours (up to 7 days old).
    """
    from datetime import timedelta

    from django.conf import settings
    from django.core.mail import send_mail
    from django.utils import timezone

    from allauth.account.models import EmailAddress

    cutoff = timezone.now() - timedelta(hours=24)
    max_age = timezone.now() - timedelta(days=7)

    unverified = EmailAddress.objects.filter(
        verified=False,
        user__date_joined__lt=cutoff,
        user__date_joined__gt=max_age,
    ).select_related("user")

    verified_user_ids = EmailAddress.objects.filter(
        verified=True,
    ).values_list("user_id", flat=True)
    unverified = unverified.exclude(user_id__in=verified_user_ids)

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

    return f"Sent {sent} verification reminder(s)"
