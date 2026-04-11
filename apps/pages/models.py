from django.db import models

from modelcluster.fields import ParentalKey
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page, Orderable
from wagtail import blocks
from wagtail.images.blocks import ImageChooserBlock


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
    ]

    max_count = 1

    class Meta:
        verbose_name = "Home Page"


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
