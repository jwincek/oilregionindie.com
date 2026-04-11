import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Tag(models.Model):
    """Community post tag."""

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


class CommunityPost(models.Model):
    """
    Phase 3: Community discussion posts.
    Uses plain TextField (not Wagtail RichTextField) since these are
    rendered through Django views, not Wagtail pages.
    """

    class PostType(models.TextChoices):
        DISCUSSION = "discussion", "Discussion"
        ANNOUNCEMENT = "announcement", "Announcement"
        OPPORTUNITY = "opportunity", "Opportunity"
        REVIEW = "review", "Review"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="community_posts",
    )
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    post_type = models.CharField(
        max_length=20, choices=PostType.choices, default=PostType.DISCUSSION
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="posts")
    is_pinned = models.BooleanField(default=False)

    # Threaded replies
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return self.title or f"Post by {self.author}"
