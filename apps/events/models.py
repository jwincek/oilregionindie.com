import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from simple_history.models import HistoricalRecords
from wagtail.fields import RichTextField
from wagtail.search import index

from apps.creators.models import CreatorProfile
from apps.venues.models import VenueProfile


class EventSeries(models.Model):
    """
    A grouping of events under one banner (issue #45): multi-venue
    festivals, pop-up crawls, gallery walks. Purely a grouping — member
    events keep their own venue/location, lineup, and times, and
    overlapping times are deliberately allowed (Porchfest-style
    simultaneous sets are the point, not a conflict). Admin-managed for
    beta; organizer-facing creation comes later without schema changes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = RichTextField(blank=True)
    poster_image = models.ImageField(upload_to="events/series/", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_event_series",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        verbose_name_plural = "Event series"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("events:series_detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while EventSeries.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


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

    # Venue (nullable for virtual events and off-platform locations)
    venue = models.ForeignKey(
        VenueProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )

    # Off-platform location (issue #17): freeform place for events not at
    # a listed venue — street fairs, one-off spots, house shows. Recurring
    # real places (parks, halls) belong in the venue directory as unclaimed
    # listings instead. Never combined with a venue (DB constraint below).
    location_name = models.CharField(
        max_length=255, blank=True,
        help_text='Where it happens when not at a listed venue (e.g., "Seneca Street, Oil City")',
    )
    # Optional, for directions. Its presence is what gates public display —
    # leave it empty for locations that shouldn't publish an address
    # (e.g., house shows).
    location_address = models.ForeignKey(
        "core.Address",
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

    # Series membership (issue #45): festivals and pop-up crawls group
    # many events under one banner. Grouping only — nothing else changes.
    series = models.ForeignKey(
        "EventSeries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
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

    # Lifecycle (issue #20): cancelled/postponed events stay listed with a
    # badge instead of vanishing — unpublishing reads as a data error.
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELLED = "cancelled", "Cancelled"
        POSTPONED = "postponed", "Postponed"

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED,
    )

    # Set automatically when an edit changes the place (issue #44): a
    # human-readable snapshot of where the event used to be, driving the
    # "New location / moved from X" notice so nobody drives to the old spot.
    previous_location = models.CharField(max_length=255, blank=True)

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
        constraints = [
            models.CheckConstraint(
                condition=~(models.Q(venue__isnull=False) & ~models.Q(location_name="")),
                name="event_venue_or_location_not_both",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def location_display(self):
        """Human-readable place: venue name, freeform location, or virtual."""
        if self.venue:
            return self.venue.name
        if self.location_name:
            return self.location_name
        if self.is_virtual:
            return "Virtual"
        return ""

    @property
    def map_address(self):
        """The Address to plot / route to — the host venue's, or the
        off-venue location. None for virtual or location-less events."""
        return self.venue.address if self.venue else self.location_address

    @property
    def directions_url(self):
        """Directions to wherever the event is, honoring the accurate
        stored coordinates (see Address.directions_url)."""
        return self.map_address.directions_url if self.map_address else ""

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
    # Exactly one of creator/guest_name is set (DB constraint below).
    # Guests are performers without hub profiles — touring headliners,
    # one-off acts — shown by name with no profile link (issue #18).
    creator = models.ForeignKey(
        CreatorProfile, on_delete=models.CASCADE, related_name="event_slots",
        null=True, blank=True,
    )
    guest_name = models.CharField(
        max_length=255, blank=True,
        help_text="Performer not on the hub (e.g., a touring act)",
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
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(creator__isnull=False, guest_name="")
                    | (models.Q(creator__isnull=True) & ~models.Q(guest_name=""))
                ),
                name="slot_creator_xor_guest",
            ),
        ]

    @property
    def performer_name(self):
        return self.creator.display_name if self.creator else self.guest_name

    def __str__(self):
        desc = f" — {self.set_description}" if self.set_description else ""
        return f"{self.performer_name} at {self.event.title}{desc}"


# ---------------------------------------------------------------------------
# BookingRequest (bidirectional: creator→venue or venue→creator)
# ---------------------------------------------------------------------------


class BookingRequest(models.Model):
    """
    A booking inquiry between a creator and a venue. Bidirectional:
    a creator can request to book at a venue, or a venue can invite
    a creator. The initiator is tracked to determine direction.
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
    # Deliberately freeform, not structured dates — rationale and revisit
    # criteria recorded in issue #25.
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

    history = HistoricalRecords(excluded_fields=["updated_at"])

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
        Venue-initiated → creator's booking email (falls back to account email).
        """
        if self.is_creator_initiated:
            return self.venue.booking_email
        return self.creator.booking_email or self.creator.user.email

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


class BookingFeedback(models.Model):
    """
    Private feedback left after a booking is completed.
    Each party can leave one feedback per booking — visible only to the other party.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(
        BookingRequest, on_delete=models.CASCADE, related_name="feedback",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="booking_feedback_given",
    )
    body = models.TextField(help_text="Private feedback visible only to the other party")
    would_work_again = models.BooleanField(
        default=True, help_text="Would you work with this creator/venue again?",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "author"],
                name="one_feedback_per_party_per_booking",
            ),
        ]

    def __str__(self):
        return f"Feedback on {self.booking} by {self.author}"


class Endorsement(models.Model):
    """
    A public endorsement between a creator and a venue.
    Positive-only — like a recommendation. Displayed on both profiles.
    No ratings or negative reviews by design; rationale in issue #26.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(
        "creators.CreatorProfile", on_delete=models.CASCADE, related_name="endorsements",
    )
    venue = models.ForeignKey(
        "venues.VenueProfile", on_delete=models.CASCADE, related_name="endorsements",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="endorsements_given",
    )
    body = models.TextField(help_text="A short recommendation or positive experience")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["creator", "venue", "author"],
                name="one_endorsement_per_relationship",
            ),
        ]

    def __str__(self):
        return f"Endorsement: {self.creator.display_name} & {self.venue.name}"

    @property
    def is_from_creator(self):
        return self.author == self.creator.user

    @property
    def is_from_venue(self):
        return self.author == self.venue.user


class EventRSVP(models.Model):
    """
    A fan's RSVP to an event — the event-level demand signal the app
    otherwise lacks (issue #85). Doubles as the attribution basis for
    "the festival drove this crowd" and as the precise audience for
    event-change notifications (people who said they'd go get told when
    it moves or cancels).
    """

    class Status(models.TextChoices):
        GOING = "going", "Going"
        INTERESTED = "interested", "Interested"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="rsvps"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="event_rsvps",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.GOING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"], name="unique_rsvp_per_user_event"
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.get_status_display()} — {self.event.title}"


class EventView(models.Model):
    """
    Daily view count for an event — the event-level analogue of core's
    ProfileView (issue #85). One row per event per day. Feeds the venue
    engagement dashboard's "the hub drove this crowd" attribution.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="view_counts"
    )
    date = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "date"], name="unique_event_view_per_day"
            ),
        ]

    def __str__(self):
        return f"{self.event.title} — {self.date}: {self.count} views"

    @classmethod
    def record_view(cls, event):
        """Increment today's view count for an event."""
        from django.utils import timezone
        obj, _ = cls.objects.get_or_create(event=event, date=timezone.now().date())
        cls.objects.filter(pk=obj.pk).update(count=models.F("count") + 1)
