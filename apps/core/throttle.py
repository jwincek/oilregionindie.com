"""
Content-creation throttles and dedup (issue #86).

Deliberately DB-query-based, not cache-based: every guarded action is
authenticated, so per-user counting over ``created_at`` is the meaningful
axis, and the database is shared across gunicorn workers where the default
LocMemCache is not. This keeps the feed defended against volume spam
without adding a dependency or a cache-consistency assumption.
"""
from django.utils import timezone

# Accounts younger than this get the stricter limits — the burst-and-burn
# spam account never ages past it, while a genuine new member hits a cap
# they'd rarely reach in normal use.
NEW_ACCOUNT_AGE_HOURS = 24


def is_new_account(user):
    from datetime import timedelta
    return user.date_joined >= timezone.now() - timedelta(hours=NEW_ACCOUNT_AGE_HOURS)


def effective_limit(user, normal, strict):
    """The stricter cap for brand-new accounts, the normal cap otherwise."""
    return strict if is_new_account(user) else normal


def too_many_recent(model, window, limit, **filters):
    """
    True if ``limit`` or more rows matching ``filters`` were created within
    ``window`` (a timedelta). The model must have a ``created_at`` field.
    """
    cutoff = timezone.now() - window
    return model.objects.filter(created_at__gte=cutoff, **filters).count() >= limit


def is_duplicate(model, window, **fields):
    """
    True if an identical recent row (same ``fields``, typically same author
    and body) already exists within ``window`` — blocks the repeated repost.
    """
    cutoff = timezone.now() - window
    return model.objects.filter(created_at__gte=cutoff, **fields).exists()
