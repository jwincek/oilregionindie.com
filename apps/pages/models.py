from django.db import models

from modelcluster.fields import ParentalKey
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page, Orderable
from wagtail import blocks
from wagtail.images.blocks import ImageChooserBlock


def _theme_choices():
    # Lazy: discover at call time so themes added on disk show up without
    # a code change. Returning a list (not a generator) so Django's
    # migration autodetector serializes consistently.
    from apps.core.theming import theme_choices
    return theme_choices()


@register_setting(icon="cog")
class SiteBranding(BaseGenericSetting):
    """
    Site-wide branding and contact info, editable from the Wagtail admin.
    Populated initially by the `setup` management command; can be tweaked
    later under Settings → Site branding.
    """

    site_name = models.CharField(
        max_length=120,
        default="Oil Region Creative Hub",
        help_text="Displayed in the page title, footer, and emails.",
    )
    active_theme = models.CharField(
        max_length=80,
        default="default",
        choices=_theme_choices,
        help_text="Picks a theme directory under ./themes/. Overrides only "
                  "CSS variables and (optionally) templates — no code runs.",
    )
    tagline = models.CharField(
        max_length=200,
        blank=True,
        help_text="Short phrase used in social/OG meta tags.",
    )
    origin_story = models.TextField(
        blank=True,
        help_text="One-paragraph blurb shown in the site footer.",
    )
    contact_email = models.EmailField(
        blank=True,
        help_text="Address shown to suspended users and in 'contact us' links.",
    )
    source_repo_url = models.URLField(
        blank=True,
        help_text="Link to the source code repository (footer + soft-launch banner).",
    )
    logo = models.ForeignKey(
        "wagtailimages.Image",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    og_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Default Open Graph / social-share image.",
    )

    panels = [
        MultiFieldPanel(
            [FieldPanel("site_name"), FieldPanel("tagline"), FieldPanel("origin_story")],
            heading="Identity",
        ),
        MultiFieldPanel(
            [FieldPanel("contact_email"), FieldPanel("source_repo_url")],
            heading="Contact & links",
        ),
        MultiFieldPanel(
            [FieldPanel("logo"), FieldPanel("og_image")],
            heading="Imagery",
        ),
        MultiFieldPanel(
            [FieldPanel("active_theme")],
            heading="Theme",
        ),
    ]

    class Meta:
        verbose_name = "Site branding"


class HomePage(Page):
    """
    The site homepage — managed through Wagtail admin.
    Shows featured creators, upcoming events, and editorial content.
    """

    subtitle = models.CharField(max_length=255, blank=True)
    hero_text = RichTextField(blank=True)
    hero_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    body = StreamField(
        [
            ("heading", blocks.CharBlock(form_classname="title")),
            ("paragraph", blocks.RichTextBlock()),
            ("image", ImageChooserBlock()),
            ("featured_section", blocks.StructBlock([
                ("title", blocks.CharBlock()),
                ("text", blocks.RichTextBlock()),
                ("link_url", blocks.URLBlock(required=False)),
                ("link_text", blocks.CharBlock(required=False)),
            ])),
        ],
        blank=True,
        use_json_field=True,
    )

    content_panels = Page.content_panels + [
        FieldPanel("subtitle"),
        FieldPanel("hero_text"),
        FieldPanel("hero_image"),
        FieldPanel("body"),
        InlinePanel("featured_creators", label="Featured Creators"),
        InlinePanel("featured_venues", label="Featured Venues"),
    ]

    max_count = 1

    class Meta:
        verbose_name = "Home Page"

    def get_context(self, request):
        from django.utils import timezone
        from apps.creators.models import CreatorProfile
        from apps.venues.models import VenueProfile
        from apps.events.models import Event

        context = super().get_context(request)

        # Upcoming events (next 5)
        context["upcoming_events"] = Event.objects.filter(
            is_published=True,
            start_datetime__gte=timezone.now(),
        ).select_related("venue").order_by("start_datetime")[:5]

        # Recently joined creators (latest 4 published, not already featured)
        featured_ids = list(
            self.featured_creators.values_list("creator_id", flat=True)
        )
        context["recent_creators"] = CreatorProfile.objects.filter(
            publish_status="published",
        ).exclude(pk__in=featured_ids).order_by("-created_at")[:4]

        # Recently joined venues (latest 4 published, not already featured)
        featured_venue_ids = list(
            self.featured_venues.values_list("venue_id", flat=True)
        )
        context["recent_venues"] = VenueProfile.objects.filter(
            publish_status="published",
        ).exclude(pk__in=featured_venue_ids).order_by("-created_at")[:4]

        return context


class HomePageFeaturedCreator(Orderable):
    """Featured creator on the homepage — linked to actual CreatorProfile."""

    page = ParentalKey(HomePage, on_delete=models.CASCADE, related_name="featured_creators")
    creator = models.ForeignKey(
        "creators.CreatorProfile",
        on_delete=models.CASCADE,
        related_name="+",
    )
    blurb = models.TextField(blank=True, help_text="Short feature text")

    panels = [
        FieldPanel("creator"),
        FieldPanel("blurb"),
    ]

    def __str__(self):
        return self.creator.display_name


class HomePageFeaturedVenue(Orderable):
    """Featured venue on the homepage — linked to actual VenueProfile."""

    page = ParentalKey(HomePage, on_delete=models.CASCADE, related_name="featured_venues")
    venue = models.ForeignKey(
        "venues.VenueProfile",
        on_delete=models.CASCADE,
        related_name="+",
    )
    blurb = models.TextField(blank=True, help_text="Short feature text")

    panels = [
        FieldPanel("venue"),
        FieldPanel("blurb"),
    ]

    def __str__(self):
        return self.venue.name


class ContentPage(Page):
    """
    General-purpose content page for About, Festival History, FAQ, etc.
    """

    subtitle = models.CharField(max_length=255, blank=True)
    body = StreamField(
        [
            ("heading", blocks.CharBlock(form_classname="title")),
            ("paragraph", blocks.RichTextBlock()),
            ("image", ImageChooserBlock()),
            ("quote", blocks.BlockQuoteBlock()),
            ("embed", blocks.RawHTMLBlock(help_text="For embedding external content")),
        ],
        use_json_field=True,
    )
    header_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    content_panels = Page.content_panels + [
        FieldPanel("subtitle"),
        FieldPanel("header_image"),
        FieldPanel("body"),
    ]

    class Meta:
        verbose_name = "Content Page"


class BlogIndexPage(Page):
    """Blog listing page — parent for BlogPost pages."""

    intro = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
    ]

    max_count = 1

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["posts"] = (
            BlogPost.objects.live().public().descendant_of(self).order_by("-first_published_at")
        )
        return context

    class Meta:
        verbose_name = "Blog Index"


class BlogPost(Page):
    """Individual blog post / news article / creator spotlight."""

    subtitle = models.CharField(max_length=255, blank=True)
    header_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    body = StreamField(
        [
            ("heading", blocks.CharBlock(form_classname="title")),
            ("paragraph", blocks.RichTextBlock()),
            ("image", ImageChooserBlock()),
            ("quote", blocks.BlockQuoteBlock()),
            ("embed", blocks.RawHTMLBlock()),
        ],
        use_json_field=True,
    )
    author_name = models.CharField(max_length=255, blank=True)
    tags = models.CharField(
        max_length=500, blank=True,
        help_text="Comma-separated tags",
    )

    content_panels = Page.content_panels + [
        FieldPanel("subtitle"),
        FieldPanel("header_image"),
        FieldPanel("body"),
        MultiFieldPanel(
            [FieldPanel("author_name"), FieldPanel("tags")],
            heading="Metadata",
        ),
    ]

    parent_page_types = ["pages.BlogIndexPage"]

    class Meta:
        verbose_name = "Blog Post"

    @property
    def tag_list(self):
        """Split comma-separated tags into a clean list for templates."""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]
