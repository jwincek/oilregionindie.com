from django.contrib import admin

from .models import Address, AvailabilityType, BlockedWord, Notification, ProfileAvailability, Report, UserProfile


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ["short_display", "street", "zip_code"]
    search_fields = ["city", "state", "street", "zip_code"]
    list_filter = ["state"]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["get_display_name", "user", "location", "is_suspended", "email_digest", "created_at"]
    search_fields = ["display_name", "user__email", "location"]
    list_filter = ["is_suspended", "email_digest", "created_at"]
    filter_horizontal = ["followed_creators", "followed_venues"]
    readonly_fields = ["user"]
    actions = ["suspend_users", "unsuspend_users"]

    @admin.action(description="Suspend selected users")
    def suspend_users(self, request, queryset):
        updated = queryset.update(is_suspended=True)
        self.message_user(request, f"Suspended {updated} user(s).")

    @admin.action(description="Unsuspend selected users")
    def unsuspend_users(self, request, queryset):
        updated = queryset.update(is_suspended=False)
        self.message_user(request, f"Unsuspended {updated} user(s).")


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


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["content_type", "reporter", "status", "created_at"]
    list_filter = ["status", "content_type", "created_at"]
    search_fields = ["reason", "admin_notes", "reporter__email"]
    readonly_fields = ["reporter", "content_type", "content_id", "content_url", "reason", "created_at"]
    actions = ["mark_reviewed", "mark_dismissed", "mark_action_taken"]

    @admin.action(description="Mark as reviewed")
    def mark_reviewed(self, request, queryset):
        from django.utils import timezone
        queryset.update(status="reviewed", resolved_at=timezone.now())

    @admin.action(description="Dismiss selected reports")
    def mark_dismissed(self, request, queryset):
        from django.utils import timezone
        queryset.update(status="dismissed", resolved_at=timezone.now())

    @admin.action(description="Mark action taken")
    def mark_action_taken(self, request, queryset):
        from django.utils import timezone
        queryset.update(status="action_taken", resolved_at=timezone.now())


@admin.register(BlockedWord)
class BlockedWordAdmin(admin.ModelAdmin):
    list_display = ["word", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["word"]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["notification_type", "recipient", "message", "is_read", "created_at"]
    list_filter = ["notification_type", "is_read", "created_at"]
    search_fields = ["message", "recipient__email"]
    readonly_fields = ["recipient", "actor", "notification_type", "message", "url", "created_at"]
