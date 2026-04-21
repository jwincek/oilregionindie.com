import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from wagtail.fields import RichTextField
from wagtail.search import index

from apps.core.models import Address, PublishableProfile, SocialPlatform


# ---------------------------------------------------------------------------
# Taxonomy models
# ---------------------------------------------------------------------------


class Discipline(models.Model):
    """Creative discipline: Musician, Visual Artist, Jeweler, Ceramicist, etc."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    icon = models.CharField(
        max_length=50, blank=True,
        help_text="Icon identifier for UI (e.g., lucide icon name)",
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Genre(models.Model):
    """Musical/artistic genre or style."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Skill(models.Model):
    """A specific skill within a discipline."""

    name = models.CharField(max_length=100)
    slug = models.SlugField()
    discipline = models.ForeignKey(
        Discipline, on_delete=models.CASCADE, related_name="skills",
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["discipline__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "discipline"],
                name="unique_skill_per_discipline",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.discipline.name})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# CreatorProfile
# ---------------------------------------------------------------------------


class CreatorProfile(PublishableProfile, index.Indexed):
    """
    Unified profile for all types of creators: musicians, visual artists,
    jewelers, makers, bands, and collectives.
    Inherits slug, images, publishing, Stripe, and permissions from PublishableProfile.
    """

    class ProfileType(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        BAND = "band", "Band"
        COLLECTIVE = "collective", "Collective"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="creator_profile",
        help_text="The owner/primary manager of this profile",
    )
    managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="managed_creator_profiles",
    )
    display_name = models.CharField(max_length=255)
    profile_type = models.CharField(
        max_length=20,
        choices=ProfileType.choices,
        default=ProfileType.INDIVIDUAL,
    )
    bio = RichTextField(blank=True)
    disciplines = models.ManyToManyField(Discipline, blank=True, related_name="creators")
    genres = models.ManyToManyField(
        Genre, blank=True, related_name="creators",
        help_text="Optional; most relevant for musicians.",
    )
    skills = models.ManyToManyField(
        Skill, blank=True, related_name="creators",
        help_text="Specific skills across any discipline",
    )

    # Location — freeform fields for identity/homecoming context
    location = models.CharField(max_length=255, blank=True, help_text="Current city/region")
    home_region = models.CharField(max_length=255, blank=True, help_text="Origin/roots")

    # Structured address for geocoding and distance queries (optional)
    address = models.ForeignKey(
        Address,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="creator_profiles",
    )

    # Wagtail search index
    search_fields = [
        index.SearchField("display_name", boost=10),
        index.SearchField("bio"),
        index.SearchField("location"),
        index.SearchField("home_region"),
        index.FilterField("publish_status"),
        index.FilterField("profile_type"),
    ]

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.display_name

    def get_absolute_url(self):
        return reverse("creators:detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.generate_unique_slug(self.display_name)
        super().save(*args, **kwargs)

    # --- Properties ---

    @property
    def featured_media(self):
        return self.media_items.filter(is_featured=True).order_by("sort_order")

    @property
    def discipline_list(self):
        return ", ".join(d.name for d in self.disciplines.all())

    @property
    def skill_list(self):
        return ", ".join(s.name for s in self.skills.all())

    @property
    def skills_by_discipline(self):
        """Group this creator's skills by discipline for display."""
        grouped = {}
        for skill in self.skills.select_related("discipline").all():
            disc_name = skill.discipline.name
            if disc_name not in grouped:
                grouped[disc_name] = []
            grouped[disc_name].append(skill.name)
        return grouped

    def sync_disciplines_from_skills(self):
        """Add disciplines implied by selected skills (preserves manual ones)."""
        skill_disciplines = Discipline.objects.filter(
            skills__in=self.skills.all()
        ).distinct()
        for disc in skill_disciplines:
            self.disciplines.add(disc)

    @property
    def is_group(self):
        return self.profile_type in (self.ProfileType.BAND, self.ProfileType.COLLECTIVE)

    @property
    def active_members(self):
        return (
            self.members.filter(is_active=True)
            .select_related("member")
            .order_by("sort_order")
        )

    @property
    def active_memberships(self):
        return (
            self.memberships.filter(is_active=True)
            .select_related("group")
            .order_by("group__display_name")
        )

    @property
    def active_availabilities(self):
        """Active availability flags for this creator."""
        return (
            self.availabilities
            .filter(is_active=True)
            .select_related("availability_type")
            .order_by("availability_type__sort_order")
        )

    @property
    def is_available_for_booking(self):
        """Quick check for the most common availability type."""
        return self.availabilities.filter(
            is_active=True,
            availability_type__slug="available-for-booking",
        ).exists()


# ---------------------------------------------------------------------------
# Related models
# ---------------------------------------------------------------------------


class CreatorSocialLink(models.Model):
    """A social media link on a creator's profile."""

    creator = models.ForeignKey(
        CreatorProfile, on_delete=models.CASCADE, related_name="social_links"
    )
    platform = models.CharField(max_length=20, choices=SocialPlatform.choices)
    url = models.URLField()
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "platform"]

    def __str__(self):
        return f"{self.get_platform_display()} — {self.creator.display_name}"


class CreatorMembership(models.Model):
    """Links an individual creator to a band or collective with a role."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(
        CreatorProfile, on_delete=models.CASCADE, related_name="members",
        help_text="The band or collective",
    )
    member = models.ForeignKey(
        CreatorProfile, on_delete=models.CASCADE, related_name="memberships",
        help_text="The individual member",
    )
    role = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    joined_date = models.DateField(null=True, blank=True)
    left_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "member__display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "member"],
                name="unique_membership",
            ),
        ]
        verbose_name = "Membership"
        verbose_name_plural = "Memberships"

    def __str__(self):
        role_str = f" ({self.role})" if self.role else ""
        return f"{self.member.display_name} in {self.group.display_name}{role_str}"


class MediaItem(models.Model):
    """A piece of media on a creator's profile."""

    class MediaType(models.TextChoices):
        AUDIO = "audio", "Audio"
        VIDEO = "video", "Video"
        IMAGE = "image", "Image"
        EMBED = "embed", "Embed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(
        CreatorProfile, on_delete=models.CASCADE, related_name="media_items"
    )
    title = models.CharField(max_length=255)
    media_type = models.CharField(max_length=10, choices=MediaType.choices)
    file = models.FileField(upload_to="creators/media/", blank=True)
    embed_url = models.URLField(blank=True, help_text="URL from SoundCloud, Bandcamp, YouTube, or Vimeo")
    embed_html = models.TextField(blank=True, help_text="Cached oEmbed HTML")
    thumbnail = models.ImageField(upload_to="creators/thumbnails/", blank=True)
    description = models.TextField(blank=True)
    sort_order = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_media_type_display()})"
