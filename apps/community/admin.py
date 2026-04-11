from django.contrib import admin

from .models import CommunityPost, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "post_type", "is_pinned", "created_at"]
    list_filter = ["post_type", "is_pinned", "created_at"]
    search_fields = ["title", "body"]
