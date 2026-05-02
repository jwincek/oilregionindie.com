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


def notify_profile_approved(profile):
    """
    Notify a creator or venue owner that their profile has been approved.
    Sends both an in-app notification and an email.
    """
    from apps.creators.models import CreatorProfile
    from .models import Notification

    if isinstance(profile, CreatorProfile):
        profile_type = "creator"
        name = profile.display_name
        url = profile.get_absolute_url()
    else:
        profile_type = "venue"
        name = profile.name
        url = profile.get_absolute_url()

    # In-app notification
    Notification.objects.create(
        recipient=profile.user,
        notification_type=Notification.NotificationType.PROFILE_APPROVED,
        message=f"Your {profile_type} profile \"{name}\" has been approved and is now live!",
        url=url,
    )

    # Email notification
    site_name = getattr(settings, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub")
    send_mail(
        subject=f"[{site_name}] Your {profile_type} profile is live!",
        message=(
            f"Great news — your {profile_type} profile \"{name}\" has been approved "
            f"and is now visible in the directory.\n\n"
            f"View your profile: {url}\n\n"
            f"You can continue editing your profile, adding media, setting availability, "
            f"and managing social links at any time.\n\n"
            f"Welcome to the community!\n"
            f"{site_name}"
        ),
        from_email=None,
        recipient_list=[profile.user.email],
        fail_silently=True,
    )


def notify_booking_status_changed(booking):
    """
    Send an email notification when a booking request is created or responded to.
    Notifies the receiving party.
    """
    creator_name = booking.creator.display_name
    venue_name = booking.venue.name

    if booking.status == "pending":
        # New request — notify the recipient
        recipient = booking.recipient_email
        if booking.is_creator_initiated:
            subject = f"[Oil Region Hub] Booking request from {creator_name}"
            message = (
                f"{creator_name} has sent a booking request to {venue_name}.\n\n"
                f"Event type: {booking.get_event_type_display()}\n"
                f"Preferred dates: {booking.preferred_dates}\n\n"
                f"Message:\n{booking.message}\n\n"
                f"View and respond to this request in your booking inbox."
            )
        else:
            subject = f"[Oil Region Hub] Booking invitation from {venue_name}"
            message = (
                f"{venue_name} has sent a booking invitation to {creator_name}.\n\n"
                f"Event type: {booking.get_event_type_display()}\n"
                f"Preferred dates: {booking.preferred_dates}\n\n"
                f"Message:\n{booking.message}\n\n"
                f"View and respond to this invitation in your booking inbox."
            )
    elif booking.status in ("accepted", "declined"):
        # Response — notify the initiator
        recipient = booking.initiated_by.email
        status_word = "accepted" if booking.status == "accepted" else "declined"
        if booking.is_creator_initiated:
            subject = f"[Oil Region Hub] {venue_name} {status_word} your booking request"
        else:
            subject = f"[Oil Region Hub] {creator_name} {status_word} your booking invitation"
        message = (
            f"Your booking request has been {status_word}.\n\n"
            f"Creator: {creator_name}\n"
            f"Venue: {venue_name}\n"
        )
        if booking.response_message:
            message += f"\nResponse:\n{booking.response_message}\n"
    else:
        return  # No notification for withdrawn/expired

    if not recipient:
        return

    send_mail(
        subject=subject,
        message=message,
        from_email=None,
        recipient_list=[recipient],
        fail_silently=True,
    )

    # Also create an in-app notification
    from .models import Notification

    if booking.status == "pending":
        # Notify the recipient
        if booking.is_creator_initiated:
            notif_recipient = booking.venue.user
            notif_message = f"{creator_name} sent a booking request to {venue_name}"
        else:
            notif_recipient = booking.creator.user
            notif_message = f"{venue_name} sent a booking invitation to {creator_name}"
    elif booking.status in ("accepted", "declined"):
        notif_recipient = booking.initiated_by
        status_word = "accepted" if booking.status == "accepted" else "declined"
        notif_message = f"Your booking with {creator_name} & {venue_name} was {status_word}"
    else:
        return

    Notification.objects.create(
        recipient=notif_recipient,
        actor=booking.initiated_by if booking.status == "pending" else None,
        notification_type=Notification.NotificationType.BOOKING,
        message=notif_message,
        url=f"/events/bookings/{booking.pk}/",
    )
