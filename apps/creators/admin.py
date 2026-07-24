from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from apps.core.models import ProfileAvailability

from .models import (
    CreatorMembership, CreatorProfile, CreatorSocialLink,
    Discipline, Genre, MediaItem, Skill,
)


@admin.register(Discipline)
class DisciplineAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "skill_count"]
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Skills")
    def skill_count(self, obj):
        return obj.skills.count()


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ["name", "discipline", "slug"]
    list_filter = ["discipline"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


class MediaItemInline(admin.TabularInline):
    model = MediaItem
    extra = 0
    fields = ["title", "media_type", "file", "embed_url", "embed_html", "sort_order", "is_featured"]


@admin.register(MediaItem)
class MediaItemAdmin(admin.ModelAdmin):
    list_display = ["title", "creator", "media_type", "has_embed", "is_featured", "created_at"]
    list_filter = ["media_type", "is_featured"]
    search_fields = ["title", "creator__display_name", "description"]
    actions = ["refresh_embed_html"]

    @admin.display(boolean=True, description="Embed cached")
    def has_embed(self, obj):
        return bool(obj.embed_html)

    @admin.action(description="Re-fetch oEmbed HTML for selected items")
    def refresh_embed_html(self, request, queryset):
        from apps.creators.embeds import refresh_embed
        success = 0
        for item in queryset.exclude(embed_url=""):
            if refresh_embed(item):
                success += 1
        self.message_user(request, f"Refreshed {success} of {queryset.count()} items.")


class SocialLinkInline(admin.TabularInline):
    model = CreatorSocialLink
    extra = 1
    fields = ["platform", "url", "sort_order"]


class MemberInline(admin.TabularInline):
    """Members of this band/collective."""
    model = CreatorMembership
    fk_name = "group"
    extra = 1
    fields = ["member", "guest_name", "guest_email", "role", "is_active", "sort_order", "joined_date", "left_date"]
    autocomplete_fields = ["member"]
    verbose_name = "Member"
    verbose_name_plural = "Members"


class MembershipInline(admin.TabularInline):
    """Bands/collectives this individual belongs to."""
    model = CreatorMembership
    fk_name = "member"
    extra = 0
    fields = ["group", "role", "is_active", "sort_order"]
    autocomplete_fields = ["group"]
    verbose_name = "Membership"
    verbose_name_plural = "Member Of"


class CreatorAvailabilityInline(admin.TabularInline):
    model = ProfileAvailability
    fk_name = "creator"
    extra = 1
    fields = ["availability_type", "is_active", "note"]
    autocomplete_fields = ["availability_type"]
    verbose_name = "Availability"
    verbose_name_plural = "Availability"


@admin.register(CreatorProfile)
class CreatorProfileAdmin(SimpleHistoryAdmin):
    list_display = ["display_name", "profile_type", "discipline_list", "location", "publish_status", "claimed", "created_at"]
    list_filter = ["publish_status", "profile_type", "disciplines", "created_at"]
    search_fields = ["display_name", "bio", "location", "home_region"]
    prepopulated_fields = {"slug": ("display_name",)}
    filter_horizontal = ["disciplines", "genres", "skills", "managers"]
    inlines = [CreatorAvailabilityInline, SocialLinkInline, MediaItemInline, MemberInline, MembershipInline]
    readonly_fields = ["stripe_account_id", "stripe_onboarded", "submitted_at"]
    actions = ["approve_profiles", "adopt_guest_memberships", "suppress_profiles"]

    @admin.display(boolean=True, description="Claimed")
    def claimed(self, obj):
        return obj.user_id is not None

    @admin.action(description="Adopt guest membership rows matching the owner's email")
    def adopt_guest_memberships(self, request, queryset):
        """
        After a claim: convert guest CreatorMembership rows whose
        guest_email matches the profile owner's email into real
        memberships pointing at the profile (issue #16 claim path).
        """
        converted = skipped = 0
        for profile in queryset.filter(user__isnull=False):
            rows = CreatorMembership.objects.filter(
                member__isnull=True, guest_email__iexact=profile.user.email,
            )
            for row in rows:
                if CreatorMembership.objects.filter(
                    group=row.group, member=profile,
                ).exists():
                    skipped += 1  # already a real member of that group
                    continue
                row.member = profile
                row.guest_name = ""
                row.guest_email = ""
                row.save(update_fields=["member", "guest_name", "guest_email"])
                converted += 1
        self.message_user(
            request,
            f"Adopted {converted} guest membership(s); skipped {skipped} duplicate(s).",
        )

    @admin.action(description="Approve selected profiles (publish)")
    def approve_profiles(self, request, queryset):
        from apps.core.notifications import notify_profile_approved
        profiles = queryset.exclude(publish_status="published")
        count = 0
        for profile in profiles:
            profile.publish_status = "published"
            profile.save(update_fields=["publish_status", "updated_at"])
            notify_profile_approved(profile)
            count += 1
        self.message_user(request, f"Approved {count} profile(s).")

    @admin.action(description="Suppress selected profiles (hide after removal request)")
    def suppress_profiles(self, request, queryset):
        from apps.core.models import ModerationEvent
        count = 0
        for profile in queryset:
            profile.publish_status = "suppressed"
            profile.save(update_fields=["publish_status", "updated_at"])
            ModerationEvent.log(
                ModerationEvent.EventType.PROFILE_SUPPRESSED,
                actor=request.user, target=f"creator:{profile.slug}",
            )
            count += 1
        self.message_user(request, f"Suppressed {count} profile(s). Set back to Published to restore.")

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # After M2M relations are saved, sync disciplines from skills
        form.instance.sync_disciplines_from_skills()
