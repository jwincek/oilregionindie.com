import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from wagtail.fields import RichTextField
from wagtail.search import index

from apps.core.models import Address, PublishableProfile, SocialPlatform


# ---------------------------------------------------------------------------
# Amenity
# ---------------------------------------------------------------------------


class Amenity(models.Model):
    """Venue amenity: PA System, Stage, Parking, Green Room, etc."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Amenities"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# VenueProfile
# ---------------------------------------------------------------------------


class VenueProfile(PublishableProfile, index.Indexed):
    """
    A venue, gallery, cafe, bar, or community space that hosts events.
    Inherits slug, images, publishing, Stripe, and permissions from PublishableProfile.
    """

    class VenueType(models.TextChoices):
        BAR = "bar", "Bar"
        CAFE = "cafe", "Café"
        GALLERY = "gallery", "Gallery"
        THEATER = "theater", "Theater"
        OUTDOOR = "outdoor", "Outdoor Space"
        COMMUNITY_SPACE = "community_space", "Community Space"
        OTHER = "other", "Other"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="venue_profiles",
        help_text="The owner/primary manager of this venue",
    )
    managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="managed_venue_profiles",
    )
    name = models.CharField(max_length=255)
    description = RichTextField(blank=True)
    venue_type = models.CharField(
        max_length=20, choices=VenueType.choices, default=VenueType.OTHER
    )

    # Address (structured, geocodable)
    address = models.ForeignKey(
        Address,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="venue_profiles",
    )

    # Legacy / convenience fields for quick access without joining Address
    # These can be auto-synced from the Address on save if desired
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50)

    capacity = models.PositiveIntegerField(null=True, blank=True)

    # Amenities (structured, filterable)
    amenities = models.ManyToManyField(Amenity, blank=True, related_name="venues")

    # booking_contact replaced by VenueContact model below

    # Search
    search_fields = [
        index.SearchField("name", boost=10),
        index.SearchField("description"),
        index.SearchField("city"),
        index.SearchField("state"),
        index.FilterField("is_published"),
        index.FilterField("venue_type"),
    ]

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("venues:detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.generate_unique_slug(self.name)
        super().save(*args, **kwargs)

    @property
    def full_address(self):
        """Use the Address model's full_display if available, otherwise fallback."""
        if self.address:
            return self.address.full_display
        parts = [self.city, self.state]
        return ", ".join(p for p in parts if p)

    @property
    def amenity_list(self):
        return ", ".join(a.name for a in self.amenities.all())

    @property
    def booking_email(self):
        """
        Return the primary booking email for notifications.
        Falls back to the venue owner's email if no booking contact exists.
        """
        booking_contact = self.contacts.filter(
            contact_type=VenueContact.ContactType.BOOKING,
            method=VenueContact.Method.EMAIL,
            is_public=True,
        ).first()
        if booking_contact:
            return booking_contact.value
        return self.user.email

    @property
    def public_contacts(self):
        """All public contacts grouped by type for display."""
        return self.contacts.filter(is_public=True).order_by("sort_order")

    @property
    def active_availabilities(self):
        """Active availability flags for this venue."""
        return (
            self.availabilities
            .filter(is_active=True)
            .select_related("availability_type")
            .order_by("availability_type__sort_order")
        )

    @property
    def is_accepting_bookings(self):
        """Quick check for the most common venue availability type."""
        return self.availabilities.filter(
            is_active=True,
            availability_type__slug="accepting-booking-requests",
        ).exists()


# ---------------------------------------------------------------------------
# VenueContact
# ---------------------------------------------------------------------------


class VenueContact(models.Model):
    """
    A contact method for a venue. Venues can have multiple contacts
    for different purposes (booking, general inquiries, press, technical)
    and multiple methods per purpose (email AND phone for booking).
    """

    class ContactType(models.TextChoices):
        BOOKING = "booking", "Booking"
        GENERAL = "general", "General Inquiries"
        PRESS = "press", "Press / Media"
        TECHNICAL = "technical", "Technical / Sound"
        GALLERY = "gallery", "Gallery / Exhibition"
        EVENTS = "events", "Events"
        OTHER = "other", "Other"

    class Method(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"
        FORM = "form", "Contact Form (URL)"

    venue = models.ForeignKey(
        VenueProfile, on_delete=models.CASCADE, related_name="contacts"
    )
    contact_type = models.CharField(max_length=20, choices=ContactType.choices)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.EMAIL)
    value = models.CharField(
        max_length=255,
        help_text="Email address, phone number, or URL depending on method",
    )
    name = models.CharField(
        max_length=255, blank=True,
        help_text="Contact person's name (optional)",
    )
    is_public = models.BooleanField(
        default=True,
        help_text="Show on public venue page. Uncheck for contacts only visible to confirmed performers.",
    )
    notes = models.CharField(
        max_length=255, blank=True,
        help_text="e.g., 'Best reached after 2pm', 'For shows only, not private events'",
    )
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "contact_type", "method"]

    def __str__(self):
        name_str = f" ({self.name})" if self.name else ""
        return f"{self.get_contact_type_display()} — {self.get_method_display()}{name_str}"

    @property
    def display_value(self):
        """Format the value for display based on method."""
        if self.method == self.Method.EMAIL:
            return self.value
        elif self.method == self.Method.PHONE:
            return self.value
        elif self.method == self.Method.FORM:
            return "Contact Form"
        return self.value


# ---------------------------------------------------------------------------
# Related models
# ---------------------------------------------------------------------------


class VenueSocialLink(models.Model):
    """A social media link on a venue's profile."""

    venue = models.ForeignKey(
        VenueProfile, on_delete=models.CASCADE, related_name="social_links"
    )
    platform = models.CharField(max_length=20, choices=SocialPlatform.choices)
    url = models.URLField()
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "platform"]

    def __str__(self):
        return f"{self.get_platform_display()} — {self.venue.name}"


class VenueArea(models.Model):
    """A distinct area within a venue: Main Stage, Gallery Room, Patio, etc."""

    venue = models.ForeignKey(
        VenueProfile, on_delete=models.CASCADE, related_name="areas"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["venue", "name"],
                name="unique_area_per_venue",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.venue.name})"
