"""
User-to-user blocking (issue #89).

A block is one-sided intent with two-sided effect: if A blocks B, neither
can book, follow, or notify the other. This is the self-service safety
primitive that doesn't depend on an admin being awake — enforced at the
booking, follow, and notification boundaries.
"""


def is_blocked_between(user_a, user_b):
    """True if either user has blocked the other."""
    from apps.core.models import UserProfile

    if not (user_a and user_b):
        return False
    if not getattr(user_a, "is_authenticated", False):
        return False
    if not getattr(user_b, "is_authenticated", False):
        return False
    if user_a.pk == user_b.pk:
        return False
    return (
        UserProfile.objects.filter(user=user_a, blocked_users=user_b).exists()
        or UserProfile.objects.filter(user=user_b, blocked_users=user_a).exists()
    )
