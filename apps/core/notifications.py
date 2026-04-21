from django.conf import settings
from django.core.mail import send_mail


def notify_admin_profile_submitted(profile):
    """
    Send an email to site admins when a profile is submitted for review.
    Works for both CreatorProfile and VenueProfile.
    """
    # Determine profile type and display name
    from apps.creators.models import CreatorProfile

    if isinstance(profile, CreatorProfile):
        profile_type = "Creator"
        name = profile.display_name
    else:
        profile_type = "Venue"
        name = profile.name

    subject = f"[Oil Region Hub] New {profile_type} profile submitted: {name}"
    message = (
        f"A new {profile_type.lower()} profile has been submitted for review.\n\n"
        f"Name: {name}\n"
        f"Slug: {profile.slug}\n"
        f"Submitted by: {profile.user.email}\n\n"
        f"Review it in the Django admin:\n"
        f"  /admin/{profile_type.lower()}s/{profile_type.lower()}profile/{profile.pk}/change/"
    )

    # Send to all ADMINS, fall back to DEFAULT_FROM_EMAIL recipient
    admin_emails = [email for _, email in getattr(settings, "ADMINS", [])]
    if not admin_emails:
        admin_emails = [getattr(settings, "DEFAULT_FROM_EMAIL", "admin@localhost")]

    send_mail(
        subject=subject,
        message=message,
        from_email=None,  # uses DEFAULT_FROM_EMAIL
        recipient_list=admin_emails,
        fail_silently=True,
    )
