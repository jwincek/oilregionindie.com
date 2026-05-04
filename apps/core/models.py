import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify


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
        on_delete=models.CASCADE,
        related_name="reports_filed",
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

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report: {self.content_type} by {self.reporter}"


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

    @classmethod
    def check_content(cls, text):
        """Return a list of blocked words found in the text."""
        if not text:
            return []
        text_lower = text.lower()
        blocked = cls.objects.filter(is_active=True).values_list("word", flat=True)
        return [w for w in blocked if w.lower() in text_lower]


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
