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
