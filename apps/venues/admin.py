from django.contrib import admin

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
class VenueProfileAdmin(admin.ModelAdmin):
    list_display = ["name", "venue_type", "city", "state", "is_published", "created_at"]
    list_filter = ["is_published", "venue_type", "state", "amenities"]
    search_fields = ["name", "description", "city"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["amenities", "managers"]
    inlines = [VenueAvailabilityInline, VenueContactInline, VenueSocialLinkInline, VenueAreaInline]
    readonly_fields = ["stripe_account_id", "stripe_onboarded"]


@admin.register(VenueArea)
class VenueAreaAdmin(admin.ModelAdmin):
    list_display = ["name", "venue", "capacity", "sort_order"]
    list_filter = ["venue"]
    search_fields = ["name", "venue__name"]
