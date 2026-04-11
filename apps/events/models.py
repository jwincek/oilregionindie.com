import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from wagtail.fields import RichTextField
from wagtail.search import index

from apps.creators.models import CreatorProfile
from apps.venues.models import VenueProfile


class Event(index.Indexed, models.Model):
    """A concert, art show, maker market, festival, or other gathering."""

    class EventType(models.TextChoices):
        CONCERT = "concert", "Concert"
        ART_SHOW = "art_show", "Art Show"
        MARKET = "market", "Maker Market"
        FESTIVAL = "festival", "Festival"
        OPEN_MIC = "open_mic", "Open Mic"
        WORKSHOP = "workshop", "Workshop"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = RichTextField(blank=True)
    event_type = models.CharField(
        max_length=20, choices=EventType.choices, default=EventType.CONCERT
    )

    # Venue (nullable for virtual events)
    venue = models.ForeignKey(
        VenueProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )

    # Organizers — an event can be organized by a creator, a venue, or both.
    # The created_by user is always tracked for permission purposes.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_events",
        help_text="The user who created this event (for permissions)",
    )
    organizing_creator = models.ForeignKey(
        CreatorProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organized_events",
        help_text="Creator or collective organizing this event",
    )
    organizing_venue = models.ForeignKey(
        VenueProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organized_events",
        help_text="Venue organizing this event (can differ from host venue)",
    )

    # Timing
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
    doors_time = models.TimeField(null=True, blank=True)

    # Admission
    is_free = models.BooleanField(default=True)
    ticket_price_cents = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Price in cents (e.g., 1500 = $15.00)",
    )
    ticket_url = models.URLField(blank=True, help_text="External ticket link")

    # Media
    poster_image = models.ImageField(upload_to="events/posters/", blank=True)

    # Creators performing/exhibiting (through EventSlot for scheduling)
    creators = models.ManyToManyField(
        CreatorProfile, through="EventSlot", blank=True, related_name="events"
    )

    # Status
    is_published = models.BooleanField(default=False)

    # Virtual event support
    is_virtual = models.BooleanField(default=False)
    stream_url = models.URLField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Search
    search_fields = [
        index.SearchField("title", boost=10),
        index.SearchField("description"),
        index.FilterField("is_published"),
        index.FilterField("event_type"),
        index.FilterField("start_datetime"),
    ]

    class Meta:
        ordering = ["start_datetime"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("events:detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def can_be_edited_by(self, user):
        """Check if a user has permission to edit this event."""
        if user == self.created_by:
            return True
        if self.organizing_creator and self.organizing_creator.can_be_edited_by(user):
            return True
        if self.organizing_venue and self.organizing_venue.can_be_edited_by(user):
            return True
        return False

    @property
    def ticket_price_display(self):
        if self.is_free:
            return "Free"
        if self.ticket_price_cents:
            return f"${self.ticket_price_cents / 100:.2f}"
        return "TBA"

    @property
    def lineup(self):
        return self.slots.select_related("creator", "venue_area").order_by("sort_order", "start_time")

    @property
    def organizer_display(self):
        """Human-readable organizer name for templates."""
        parts = []
        if self.organizing_creator:
            parts.append(self.organizing_creator.display_name)
        if self.organizing_venue:
            parts.append(self.organizing_venue.name)
        return " & ".join(parts) if parts else ""


class EventSlot(models.Model):
    """
    A creator's slot within an event. Supports multi-stage, multi-area
    scheduling. No unique constraint on (event, creator) — a creator can
    have multiple slots (e.g., acoustic set at 6pm, electric set at 10pm).
    """

    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        PENDING = "pending", "Pending"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="slots")
    creator = models.ForeignKey(
        CreatorProfile, on_delete=models.CASCADE, related_name="event_slots"
    )

    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    venue_area = models.ForeignKey(
        "venues.VenueArea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_slots",
        help_text="The area within the venue (e.g., Main Stage, Gallery Room)",
    )
    set_description = models.CharField(
        max_length=255, blank=True,
        help_text="e.g., Acoustic Set, DJ Set, Live Painting",
    )
    sort_order = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    class Meta:
        ordering = ["sort_order", "start_time"]

    def __str__(self):
        desc = f" — {self.set_description}" if self.set_description else ""
        return f"{self.creator.display_name} at {self.event.title}{desc}"


# ---------------------------------------------------------------------------
# BookingRequest (bidirectional: creator→venue or venue→creator)
# ---------------------------------------------------------------------------


class BookingRequest(models.Model):
    """
    A booking inquiry between a creator and a venue. Bidirectional:
    a creator can request to play at a venue, or a venue can invite
    a creator to perform. The initiator is tracked to determine direction.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        WITHDRAWN = "withdrawn", "Withdrawn"
        EXPIRED = "expired", "Expired"

    class Direction(models.TextChoices):
        CREATOR_TO_VENUE = "creator_to_venue", "Creator → Venue"
        VENUE_TO_CREATOR = "venue_to_creator", "Venue → Creator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Both parties are always set regardless of who initiated
    venue = models.ForeignKey(
        VenueProfile,
        on_delete=models.CASCADE,
        related_name="booking_requests",
    )
    creator = models.ForeignKey(
        CreatorProfile,
        on_delete=models.CASCADE,
        related_name="booking_requests",
    )

    # Who started this conversation
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="initiated_booking_requests",
    )
    direction = models.CharField(
        max_length=20,
        choices=Direction.choices,
        help_text="Whether the creator reached out or the venue did",
    )

    # Request details
    event_type = models.CharField(
        max_length=20,
        choices=Event.EventType.choices,
        default=Event.EventType.CONCERT,
    )
    preferred_dates = models.TextField(
        help_text="Preferred dates or date ranges, freeform text",
    )
    message = models.TextField(
        help_text="Introduction, details about the proposed event",
    )

    # Response
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    response_message = models.TextField(
        blank=True,
        help_text="Reply from the receiving party",
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    # If accepted, link to the resulting event
    resulting_event = models.ForeignKey(
        Event,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_requests",
        help_text="The event created from this booking, if any",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        arrow = "→" if self.direction == self.Direction.CREATOR_TO_VENUE else "←"
        return f"{self.creator.display_name} {arrow} {self.venue.name} ({self.get_status_display()})"

    @property
    def is_creator_initiated(self):
        return self.direction == self.Direction.CREATOR_TO_VENUE

    @property
    def is_venue_initiated(self):
        return self.direction == self.Direction.VENUE_TO_CREATOR

    @property
    def recipient_email(self):
        """
        Return the email address of the party who should be notified.
        Creator-initiated → venue's booking email.
        Venue-initiated → creator's user email.
        """
        if self.is_creator_initiated:
            return self.venue.booking_email
        return self.creator.user.email

    def can_be_viewed_by(self, user):
        """Both parties and their managers can view the request."""
        if user == self.initiated_by:
            return True
        if self.creator.can_be_edited_by(user):
            return True
        if self.venue.can_be_edited_by(user):
            return True
        return False

    def can_be_responded_to_by(self, user):
        """Only the receiving party (not the initiator) can accept/decline."""
        if self.is_creator_initiated:
            return self.venue.can_be_edited_by(user)
        return self.creator.can_be_edited_by(user)
