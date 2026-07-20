from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from apps.core.models import ProfileAvailability

from .models import Amenity, VenueArea, VenueContact, VenueProfile, VenueSocialLink


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


class VenueSocialLinkInline(admin.TabularInline):
    model = VenueSocialLink
    extra = 1
    fields = ["platform", "url", "sort_order"]


class VenueContactInline(admin.TabularInline):
    model = VenueContact
    extra = 1
    fields = ["contact_type", "method", "value", "name", "is_public", "notes", "sort_order"]


class VenueAreaInline(admin.TabularInline):
    model = VenueArea
    extra = 1
    fields = ["name", "description", "capacity", "sort_order"]


class VenueAvailabilityInline(admin.TabularInline):
    model = ProfileAvailability
    fk_name = "venue"
    extra = 1
    fields = ["availability_type", "is_active", "note"]
    autocomplete_fields = ["availability_type"]
    verbose_name = "Availability"
    verbose_name_plural = "Availability"


@admin.register(VenueProfile)
class VenueProfileAdmin(SimpleHistoryAdmin):
    list_display = ["name", "venue_type", "city", "state", "publish_status", "claimed", "created_at"]

    @admin.display(boolean=True, description="Claimed")
    def claimed(self, obj):
        return obj.user_id is not None

    list_filter = ["publish_status", "venue_type", "state", "amenities"]
    search_fields = ["name", "description", "city"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["amenities", "managers"]
    inlines = [VenueAvailabilityInline, VenueContactInline, VenueSocialLinkInline, VenueAreaInline]
    readonly_fields = ["stripe_account_id", "stripe_onboarded", "submitted_at"]
    actions = ["approve_profiles"]

    @admin.action(description="Approve selected venues (publish)")
    def approve_profiles(self, request, queryset):
        from apps.core.notifications import notify_profile_approved
        profiles = queryset.exclude(publish_status="published")
        count = 0
        for profile in profiles:
            profile.publish_status = "published"
            profile.save(update_fields=["publish_status", "updated_at"])
            notify_profile_approved(profile)
            count += 1
        self.message_user(request, f"Approved {count} venue(s).")


@admin.register(VenueArea)
class VenueAreaAdmin(admin.ModelAdmin):
    list_display = ["name", "venue", "capacity", "sort_order"]
    list_filter = ["venue"]
    search_fields = ["name", "venue__name"]
