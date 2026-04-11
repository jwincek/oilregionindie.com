from django.contrib import admin

from .models import BookingRequest, Event, EventSlot


class EventSlotInline(admin.TabularInline):
    model = EventSlot
    extra = 1
    fields = ["creator", "start_time", "end_time", "venue_area", "set_description", "sort_order", "status"]
    autocomplete_fields = ["creator", "venue_area"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "event_type", "venue", "start_datetime", "is_free", "is_published"]
    list_filter = ["is_published", "event_type", "is_free", "is_virtual", "start_datetime"]
    search_fields = ["title", "description"]
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ["venue", "organizing_creator", "organizing_venue"]
    inlines = [EventSlotInline]
    date_hierarchy = "start_datetime"
    exclude = ["created_by"]

    def save_model(self, request, obj, form, change):
        if not change:  # Only set on creation, not on edit
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(BookingRequest)
class BookingRequestAdmin(admin.ModelAdmin):
    list_display = ["__str__", "direction", "event_type", "status", "created_at"]
    list_filter = ["status", "direction", "event_type", "created_at"]
    search_fields = [
        "creator__display_name", "venue__name", "message", "preferred_dates",
    ]
    autocomplete_fields = ["venue", "creator", "resulting_event"]
    readonly_fields = ["initiated_by", "direction", "created_at", "updated_at"]
    date_hierarchy = "created_at"
