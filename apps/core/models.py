import decimal
import re
import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify
from simple_history.models import HistoricalRecords


# ---------------------------------------------------------------------------
# Shared choices
# ---------------------------------------------------------------------------


class SocialPlatform(models.TextChoices):
    """Platform choices shared by creator and venue social links."""
    INSTAGRAM = "instagram", "Instagram"
    BANDCAMP = "bandcamp", "Bandcamp"
    SOUNDCLOUD = "soundcloud", "SoundCloud"
    SPOTIFY = "spotify", "Spotify"
    YOUTUBE = "youtube", "YouTube"
    FACEBOOK = "facebook", "Facebook"
    TIKTOK = "tiktok", "TikTok"
    MASTODON = "mastodon", "Mastodon"
    BLUESKY = "bluesky", "Bluesky"
    ETSY = "etsy", "Etsy"
    THREADS = "threads", "Threads"
    TWITTER_X = "twitter_x", "X / Twitter"
    LINKEDIN = "linkedin", "LinkedIn"
    GOOGLE_BUSINESS = "google_business", "Google Business"
    OTHER = "other", "Other"


# ---------------------------------------------------------------------------
# Address model (concrete, shared via ForeignKey)
# ---------------------------------------------------------------------------


class Address(models.Model):
    """
    A reusable, geocodable address. Linked from VenueProfile (required)
    and optionally from CreatorProfile and UserProfile for location-based
    discovery. Centralizes geocoding and distance queries in one place.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    street = models.TextField(blank=True, help_text="Street address / line 1")
    street_2 = models.CharField(max_length=255, blank=True, help_text="Apt, suite, unit, etc.")
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50)
    zip_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default="US")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    coordinates_manual = models.BooleanField(
        default=False,
        help_text="Coordinates placed by hand — auto-geocoding and the "
                  "clear-on-edit rule both leave them alone.",
    )

    class Meta:
        ordering = ["state", "city"]
        verbose_name_plural = "Addresses"

    def __str__(self):
        return self.short_display

    @property
    def short_display(self):
        """City, State format for compact display."""
        parts = [self.city, self.state]
        return ", ".join(p for p in parts if p)

    @property
    def full_display(self):
        """Full address for detail views."""
        parts = [self.street, self.street_2, self.city, self.state, self.zip_code]
        return ", ".join(p for p in parts if p)

    @property
    def has_coordinates(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def directions_url(self):
        """Google Maps directions link. Prefers the stored coordinates so
        it honors a manually-placed pin and lands on the real building,
        rather than handing Google the address text to re-geocode (which
        can reintroduce the small-town interpolation error we correct for).
        Falls back to the address text only when there are no coordinates.
        """
        if self.has_coordinates:
            dest = f"{self.latitude},{self.longitude}"
        elif self.full_display:
            from urllib.parse import quote_plus
            dest = quote_plus(self.full_display)
        else:
            return ""
        return f"https://www.google.com/maps/dir/?api=1&destination={dest}"

    _LOCATION_FIELDS = ["street", "street_2", "city", "state", "zip_code", "country"]

    @staticmethod
    def _as_decimal(value):
        """Normalize for comparison: a bare Python float compared against
        a Decimal fetched from the DB is almost never == due to binary
        floating-point imprecision (Decimal('41.4352') != 41.4352), even
        when both describe the same coordinate. Route through str() first.
        """
        if value is None or isinstance(value, decimal.Decimal):
            return value
        return decimal.Decimal(str(value))

    def save(self, *args, **kwargs):
        # If the place text changed but the coordinates weren't updated in
        # this same save, the old coordinates describe somewhere else now
        # and must not survive — geocode_all_pending() only ever re-geocodes
        # rows where latitude IS NULL, so a stale value here would silently
        # point at the wrong location forever. Clearing puts it back in the
        # geocoding queue instead. Manually-placed pins are exempt: a human
        # corrected the geocoder deliberately, so a later text tweak must not
        # wipe their work.
        if self.pk and not self.coordinates_manual:
            previous = Address.objects.filter(pk=self.pk).values(
                *self._LOCATION_FIELDS, "latitude", "longitude"
            ).first()
            if previous:
                location_changed = any(
                    getattr(self, f) != previous[f] for f in self._LOCATION_FIELDS
                )
                coords_untouched = (
                    self._as_decimal(self.latitude) == self._as_decimal(previous["latitude"])
                    and self._as_decimal(self.longitude) == self._as_decimal(previous["longitude"])
                )
                if location_changed and coords_untouched:
                    self.latitude = None
                    self.longitude = None
                    # A caller that restricted update_fields to the text
                    # columns would otherwise never persist the clear.
                    update_fields = kwargs.get("update_fields")
                    if update_fields is not None:
                        kwargs["update_fields"] = set(update_fields) | {
                            "latitude", "longitude",
                        }
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Abstract base for publishable profiles (Creator, Venue)
# ---------------------------------------------------------------------------


class PublishableProfile(models.Model):
    """
    Abstract base model for Creator and Venue profiles.
    Provides common fields: identity, images, publishing, Stripe,
    manager permissions, timestamps, and slug generation.
    """

    class PublishStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending Review"
        PUBLISHED = "published", "Published"
        # Hidden after a removal request from a non-consenting subject
        # (issue #90). Excluded everywhere by the publish_status="published"
        # filters, so it disappears from public views without query changes.
        # Reversible — set back to Published to restore.
        SUPPRESSED = "suppressed", "Suppressed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, unique=True)
    website = models.URLField(blank=True)
    profile_image = models.ImageField(upload_to="profiles/%(class)s/", blank=True)
    header_image = models.ImageField(upload_to="headers/%(class)s/", blank=True)
    publish_status = models.CharField(
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        help_text="Draft → Pending Review → Published",
    )
    submitted_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the profile was submitted for review",
    )

    # Stripe Connect
    stripe_account_id = models.CharField(max_length=255, blank=True)
    stripe_onboarded = models.BooleanField(default=False)

    # For unclaimed (admin-seeded) profiles: a known contact address that
    # helps verify the eventual claimant. Never displayed publicly.
    claim_contact_email = models.EmailField(
        blank=True,
        help_text="Contact for verifying a claim on this profile (not shown publicly)",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def is_published(self):
        """Backward-compatible property for views and templates."""
        return self.publish_status == self.PublishStatus.PUBLISHED

    @property
    def is_pending(self):
        return self.publish_status == self.PublishStatus.PENDING

    @property
    def is_draft(self):
        return self.publish_status == self.PublishStatus.DRAFT

    @property
    def is_suppressed(self):
        return self.publish_status == self.PublishStatus.SUPPRESSED

    def generate_unique_slug(self, source_text):
        """Generate a unique slug from source text, appending numbers if needed."""
        base_slug = slugify(source_text)
        slug = base_slug
        counter = 1
        while self.__class__.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug

    def save(self, *args, **kwargs):
        # Optimize images on upload
        from .image_utils import optimize_image, MAX_PROFILE_SIZE, MAX_HEADER_SIZE
        if self.profile_image:
            optimize_image(self.profile_image, MAX_PROFILE_SIZE)
        if self.header_image:
            optimize_image(self.header_image, MAX_HEADER_SIZE)
        super().save(*args, **kwargs)

    @property
    def can_accept_payments(self):
        return bool(self.stripe_account_id and self.stripe_onboarded)

    @property
    def is_claimed(self):
        return self.user_id is not None

    def can_be_edited_by(self, user):
        """
        Check if a user has permission to edit this profile.
        Requires child models to define `user` and `managers` fields.
        """
        if not user or not user.is_authenticated:
            return False
        return user == self.user or self.managers.filter(pk=user.pk).exists()


# ---------------------------------------------------------------------------
# UserProfile (for fans / community members)
# ---------------------------------------------------------------------------


class UserProfile(models.Model):
    """
    Lightweight profile for all users — fans, community members, and
    creators/venue owners alike. Auto-created on registration via signal.
    Provides community identity and follows without requiring a
    CreatorProfile or VenueProfile.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    display_name = models.CharField(
        max_length=255, blank=True,
        help_text="Public name; defaults to email prefix if blank",
    )
    avatar = models.ImageField(upload_to="avatars/", blank=True)
    bio = models.TextField(blank=True, max_length=500)
    location = models.CharField(max_length=255, blank=True, help_text="City or region")
    address = models.ForeignKey(
        Address,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profiles",
        help_text="Optional structured address for location-based features",
    )

    # Follows
    followed_creators = models.ManyToManyField(
        "creators.CreatorProfile", blank=True, related_name="followers"
    )
    followed_venues = models.ManyToManyField(
        "venues.VenueProfile", blank=True, related_name="followers"
    )

    # Blocking (issue #89): self-service safety. A block severs contact in
    # both directions — see apps.core.blocks.is_blocked_between.
    blocked_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="blocked_by",
    )

    # Moderation
    is_suspended = models.BooleanField(
        default=False,
        help_text="Suspended users cannot log in or interact with the platform",
    )

    # Preferences
    email_digest = models.BooleanField(
        default=True,
        help_text="Receive email updates about followed creators and events",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords(
        excluded_fields=["updated_at"],
        m2m_fields=[],  # follows are noisy and not security-sensitive
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.get_display_name()

    def get_display_name(self):
        """Return display_name, falling back to email prefix."""
        if self.display_name:
            return self.display_name
        if self.user.email:
            return self.user.email.split("@")[0]
        return f"User {self.user.pk}"

    def has_blocked(self, user):
        """True if this profile's owner has blocked the given user."""
        return bool(user) and self.blocked_users.filter(pk=user.pk).exists()


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class Notification(models.Model):
    """In-app notification for follows, likes, bookings, etc."""

    class NotificationType(models.TextChoices):
        FOLLOW = "follow", "New Follower"
        LIKE = "like", "Post Liked"
        REPLY = "reply", "New Reply"
        BOOKING = "booking", "Booking Update"
        PROFILE_APPROVED = "profile_approved", "Profile Approved"
        EVENT = "event", "Event Update"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="actions",
        null=True, blank=True,
    )
    notification_type = models.CharField(
        max_length=20, choices=NotificationType.choices,
    )
    message = models.CharField(max_length=500)
    url = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notification_type}: {self.message}"


# ---------------------------------------------------------------------------
# Content reports
# ---------------------------------------------------------------------------


class Report(models.Model):
    """User-submitted report of problematic content or behavior."""

    class ContentType(models.TextChoices):
        PROFILE = "profile", "Profile"
        POST = "post", "Community Post"
        ENDORSEMENT = "endorsement", "Endorsement"
        USER = "user", "User"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Review"
        REVIEWED = "reviewed", "Reviewed"
        DISMISSED = "dismissed", "Dismissed"
        ACTION_TAKEN = "action_taken", "Action Taken"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reports_filed",
        null=True,
        blank=True,
        help_text="Null for anonymous feedback-form submissions; also "
                  "null after the reporter deletes their account.",
    )
    content_type = models.CharField(max_length=20, choices=ContentType.choices)
    content_id = models.CharField(
        max_length=255,
        help_text="UUID or identifier of the reported content",
    )
    content_url = models.CharField(max_length=500, blank=True)
    reason = models.TextField(help_text="Why is this being reported?")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    admin_notes = models.TextField(blank=True, help_text="Internal notes (not shown to reporter)")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report: {self.content_type} by {self.reporter}"


class ModerationEvent(models.Model):
    """
    Append-only log of safety-relevant actions (issue #93): reports, blocks,
    removal requests, suppressions, suspensions.

    This is the DURABLE tier of the tiered-retention model — never pruned —
    so routine change-history (simple_history) can age out on a short window
    while the accountability record persists. Evidence is snapshotted here at
    the moment of the action rather than reconstructed from mutable history.

    ``actor`` is SET_NULL and ``target`` is free text (not a FK) on purpose:
    the record must survive deletion of either party, so an account can't
    erase the log of what it did (or of what was done about it).
    """

    class EventType(models.TextChoices):
        REPORT_FILED = "report_filed", "Report filed"
        REMOVAL_REQUESTED = "removal_requested", "Removal requested"
        USER_BLOCKED = "user_blocked", "User blocked"
        USER_UNBLOCKED = "user_unblocked", "User unblocked"
        PROFILE_SUPPRESSED = "profile_suppressed", "Profile suppressed"
        ACCOUNT_SUSPENDED = "account_suspended", "Account suspended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="moderation_actions",
        help_text="Who took the action; null for anonymous or system.",
    )
    target = models.CharField(
        max_length=255, blank=True,
        help_text="Human-readable subject (profile slug, username, content id).",
    )
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_event_type_display()} — {self.target} ({self.created_at:%Y-%m-%d})"

    @classmethod
    def log(cls, event_type, actor=None, target="", detail=""):
        """Record a safety event. Safe to call with an AnonymousUser."""
        actor_obj = actor if getattr(actor, "is_authenticated", False) else None
        return cls.objects.create(
            event_type=event_type, actor=actor_obj,
            target=str(target)[:255], detail=detail,
        )


# ---------------------------------------------------------------------------
# Word filter
# ---------------------------------------------------------------------------


class BlockedWord(models.Model):
    """Words or phrases that are blocked from community posts."""

    word = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["word"]

    def __str__(self):
        return self.word

    # Fold common leetspeak / symbol substitutions to letters before matching,
    # so "m0lly" and "m@lly" normalize to the real word.
    _LEET = str.maketrans({
        "0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
        "7": "t", "@": "a", "$": "s", "!": "i",
    })

    @classmethod
    def check_content(cls, text):
        """
        Return the blocked words present in ``text``. Matching folds
        leetspeak, tolerates separator-gap evasions ("m o l l y",
        "m.o.l.l.y"), and anchors on word boundaries so it does not fire on
        innocent substrings — the Scunthorpe problem, where "class" must not
        match a blocked "ass". Still a speed bump, not a guarantee: the real
        backstop is report -> takedown.
        """
        if not text:
            return []
        normalized = text.lower().translate(cls._LEET)
        found = []
        for word in cls.objects.filter(is_active=True).values_list("word", flat=True):
            chars = [c for c in word.lower().translate(cls._LEET) if c.isalnum()]
            if not chars:
                continue
            # Allow optional separators between each character; require a word
            # boundary on both ends.
            pattern = r"\b" + r"[\W_]*".join(re.escape(c) for c in chars) + r"\b"
            if re.search(pattern, normalized):
                found.append(word)
        return found


# ---------------------------------------------------------------------------
# Availability (shared across Creator and Venue profiles)
# ---------------------------------------------------------------------------


class ProfileView(models.Model):
    """
    Daily view count for a profile. One row per profile per day.
    Keeps the table small while providing useful analytics.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(
        "creators.CreatorProfile",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="view_counts",
    )
    venue = models.ForeignKey(
        "venues.VenueProfile",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="view_counts",
    )
    date = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["creator", "date"],
                condition=models.Q(creator__isnull=False),
                name="unique_creator_view_per_day",
            ),
            models.UniqueConstraint(
                fields=["venue", "date"],
                condition=models.Q(venue__isnull=False),
                name="unique_venue_view_per_day",
            ),
        ]

    def __str__(self):
        profile = self.creator or self.venue
        return f"{profile} — {self.date}: {self.count} views"

    @classmethod
    def record_view(cls, creator=None, venue=None):
        """Increment today's view count for a profile."""
        from django.utils import timezone
        today = timezone.now().date()
        if creator:
            obj, _ = cls.objects.get_or_create(creator=creator, date=today)
        elif venue:
            obj, _ = cls.objects.get_or_create(venue=venue, date=today)
        else:
            return
        cls.objects.filter(pk=obj.pk).update(count=models.F("count") + 1)


class AvailabilityType(models.Model):
    """
    A type of availability signal: "Available for Booking", "Accepting
    Commissions", "Gallery Space Available", etc. Seeded via seed_data,
    new types can be added without migrations.
    """

    class AppliesTo(models.TextChoices):
        CREATOR = "creator", "Creator"
        VENUE = "venue", "Venue"
        BOTH = "both", "Both"

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    applies_to = models.CharField(
        max_length=10,
        choices=AppliesTo.choices,
        default=AppliesTo.BOTH,
        help_text="Which profile types can use this availability flag",
    )
    description = models.TextField(
        blank=True,
        help_text="Shown to users when selecting this availability type",
    )
    icon = models.CharField(max_length=50, blank=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Availability Type"
        verbose_name_plural = "Availability Types"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @classmethod
    def for_creators(cls):
        return cls.objects.filter(applies_to__in=[cls.AppliesTo.CREATOR, cls.AppliesTo.BOTH])

    @classmethod
    def for_venues(cls):
        return cls.objects.filter(applies_to__in=[cls.AppliesTo.VENUE, cls.AppliesTo.BOTH])


class ProfileAvailability(models.Model):
    """
    A specific availability signal set by a creator or venue.
    e.g., "Alice is Available for Booking" with a note "Weekends only, July–September".
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    availability_type = models.ForeignKey(
        AvailabilityType,
        on_delete=models.CASCADE,
        related_name="profile_availabilities",
    )

    # One of these will be set, not both
    creator = models.ForeignKey(
        "creators.CreatorProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="availabilities",
    )
    venue = models.ForeignKey(
        "venues.VenueProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="availabilities",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Toggle off to pause without deleting",
    )
    note = models.CharField(
        max_length=255,
        blank=True,
        help_text='e.g., "Weekends only", "Booked through June, open July onward"',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["availability_type__sort_order"]
        verbose_name = "Profile Availability"
        verbose_name_plural = "Profile Availabilities"
        constraints = [
            models.UniqueConstraint(
                fields=["availability_type", "creator"],
                condition=models.Q(creator__isnull=False),
                name="unique_availability_per_creator",
            ),
            models.UniqueConstraint(
                fields=["availability_type", "venue"],
                condition=models.Q(venue__isnull=False),
                name="unique_availability_per_venue",
            ),
        ]

    def __str__(self):
        profile = self.creator or self.venue
        status = "Active" if self.is_active else "Paused"
        return f"{profile} — {self.availability_type.name} [{status}]"

    @property
    def profile(self):
        """Return whichever profile this availability belongs to."""
        return self.creator or self.venue
