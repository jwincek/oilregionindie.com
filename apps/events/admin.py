from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    BookingFeedback, BookingRequest, Endorsement, Event, EventRSVP,
    EventSeries, EventSlot,
)


class SeriesEventInline(admin.TabularInline):
    """Member events of a series — links out, never deletes."""
    model = Event
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ["title", "start_datetime", "status", "is_published"]
    readonly_fields = ["title", "start_datetime", "status", "is_published"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EventSeries)
class EventSeriesAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "event_count", "created_at"]
    search_fields = ["title"]
    prepopulated_fields = {"slug": ("title",)}
    inlines = [SeriesEventInline]
    exclude = ["created_by"]

    @admin.display(description="Events")
    def event_count(self, obj):
        return obj.events.count()

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class EventSlotInline(admin.TabularInline):
    model = EventSlot
    extra = 1
    fields = ["creator", "start_time", "end_time", "venue_area", "set_description", "sort_order", "status"]
    autocomplete_fields = ["creator", "venue_area"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "event_type", "venue", "start_datetime", "is_free", "is_published"]
    list_filter = ["is_published", "event_type", "series", "is_free", "is_virtual", "start_datetime"]
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
class BookingRequestAdmin(SimpleHistoryAdmin):
    list_display = ["__str__", "direction", "event_type", "status", "created_at"]
    list_filter = ["status", "direction", "event_type", "created_at"]
    search_fields = [
        "creator__display_name", "venue__name", "message", "preferred_dates",
    ]
    autocomplete_fields = ["venue", "creator", "resulting_event"]
    readonly_fields = ["initiated_by", "direction", "created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(BookingFeedback)
class BookingFeedbackAdmin(admin.ModelAdmin):
    list_display = ["booking", "author", "would_work_again", "created_at"]
    list_filter = ["would_work_again", "created_at"]
    search_fields = ["body", "author__email"]
    readonly_fields = ["booking", "author", "created_at"]


@admin.register(Endorsement)
class EndorsementAdmin(admin.ModelAdmin):
    list_display = ["creator", "venue", "author", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["body", "creator__display_name", "venue__name"]
    readonly_fields = ["creator", "venue", "author", "created_at"]


@admin.register(EventRSVP)
class EventRSVPAdmin(admin.ModelAdmin):
    list_display = ["event", "user", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["event__title", "user__email"]
    readonly_fields = ["event", "user", "created_at", "updated_at"]
