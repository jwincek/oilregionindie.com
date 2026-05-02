"""
Django Q async tasks for the events app.
"""

from datetime import timedelta

from django.utils import timezone

from .models import BookingRequest


def expire_old_bookings(days=30):
    """Expire pending booking requests older than the specified number of days."""
    cutoff = timezone.now() - timedelta(days=days)
    count = BookingRequest.objects.filter(
        status=BookingRequest.Status.PENDING,
        created_at__lt=cutoff,
    ).update(status=BookingRequest.Status.EXPIRED)
    return f"Expired {count} booking(s)"
