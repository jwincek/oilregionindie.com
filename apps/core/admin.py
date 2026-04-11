from django.contrib import admin

from .models import Address, AvailabilityType, ProfileAvailability, UserProfile


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ["short_display", "street", "zip_code"]
    search_fields = ["city", "state", "street", "zip_code"]
    list_filter = ["state"]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["get_display_name", "user", "location", "email_digest", "created_at"]
    search_fields = ["display_name", "user__email", "location"]
    list_filter = ["email_digest", "created_at"]
    filter_horizontal = ["followed_creators", "followed_venues"]
    readonly_fields = ["user"]


@admin.register(AvailabilityType)
class AvailabilityTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "applies_to", "slug", "sort_order"]
    list_filter = ["applies_to"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ProfileAvailability)
class ProfileAvailabilityAdmin(admin.ModelAdmin):
    list_display = ["__str__", "is_active", "note", "created_at"]
    list_filter = ["is_active", "availability_type"]
    search_fields = ["creator__display_name", "venue__name", "note"]
    autocomplete_fields = ["availability_type", "creator", "venue"]
