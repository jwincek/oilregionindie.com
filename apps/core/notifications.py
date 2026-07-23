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

    site_name = getattr(settings, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub")
    subject = f"[{site_name}] New {profile_type} profile submitted: {name}"
    message = (
        f"A new {profile_type.lower()} profile has been submitted for review.\n\n"
        f"Name: {name}\n"
        f"Slug: {profile.slug}\n"
        f"Submitted by: {profile.user.email if profile.user else '(unclaimed profile)'}\n\n"
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

    # Unclaimed (admin-seeded) profiles have no owner to notify.
    if profile.user is None:
        return

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
    site_name = getattr(settings, "WAGTAIL_SITE_NAME", "Oil Region Creative Hub")

    if booking.status == "pending":
        # New request — notify the recipient
        recipient = booking.recipient_email
        if booking.is_creator_initiated:
            subject = f"[{site_name}] Booking request from {creator_name}"
            message = (
                f"{creator_name} has sent a booking request to {venue_name}.\n\n"
                f"Event type: {booking.get_event_type_display()}\n"
                f"Preferred dates: {booking.preferred_dates}\n\n"
                f"Message:\n{booking.message}\n\n"
                f"View and respond to this request in your booking inbox."
            )
        else:
            subject = f"[{site_name}] Booking invitation from {venue_name}"
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
            subject = f"[{site_name}] {venue_name} {status_word} your booking request"
        else:
            subject = f"[{site_name}] {creator_name} {status_word} your booking invitation"
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


def _event_follower_profiles(event):
    """UserProfiles following either organizing profile of an event."""
    profiles = set()
    if event.organizing_creator:
        profiles.update(event.organizing_creator.followers.all())
    if event.organizing_venue:
        profiles.update(event.organizing_venue.followers.all())
    return profiles


def _event_notify_users(event):
    """
    Users to notify when an event changes: followers of the organizing
    profiles, plus anyone who RSVP'd to this specific event (issue #85).
    Deduped — a follower who also RSVP'd is notified once.
    """
    users = {p.user for p in _event_follower_profiles(event)}
    users.update(r.user for r in event.rsvps.select_related("user"))
    return users


def notify_event_status_changed(event):
    """
    In-app notification to followers and RSVPs when an event is
    cancelled or postponed (issues #20, #85).
    """
    from .models import Notification

    label = event.get_status_display().lower()
    for user in _event_notify_users(event):
        Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.EVENT,
            message=f'"{event.title}" has been {label}',
            url=event.get_absolute_url(),
        )


def notify_event_relocated(event, old_location):
    """
    In-app notification to followers and RSVPs when an event moves
    (issues #44, #85) — the rain-out that relocates rather than cancels.
    """
    from .models import Notification

    for user in _event_notify_users(event):
        Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.EVENT,
            message=(
                f'"{event.title}" has moved to {event.location_display} '
                f"(was {old_location})"
            ),
            url=event.get_absolute_url(),
        )


def notify_lineup_change(slot, verb, actor=None):
    """
    Tell the affected creator their place on a public bill changed
    (issue #44): added, removed, or cancelled. Guest performers and
    unclaimed profiles have no account to notify, and people aren't
    notified about their own actions.
    """
    from .models import Notification

    if not slot.creator or not slot.creator.user:
        return
    if actor is not None and slot.creator.user == actor:
        return

    messages = {
        "added": f'You’ve been added to the lineup for "{slot.event.title}"',
        "removed": f'You’ve been removed from the lineup for "{slot.event.title}"',
        "cancelled": f'Your slot at "{slot.event.title}" was cancelled',
    }
    Notification.objects.create(
        recipient=slot.creator.user,
        notification_type=Notification.NotificationType.EVENT,
        message=messages[verb],
        url=slot.event.get_absolute_url(),
    )
