from django import forms

from .models import BookingFeedback, BookingRequest, Endorsement, Event, EventSlot


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "event_type",
            "venue",
            "organizing_creator",
            "organizing_venue",
            "start_datetime",
            "end_datetime",
            "doors_time",
            "is_free",
            "ticket_price_cents",
            "ticket_url",
            "poster_image",
            "is_virtual",
            "stream_url",
            "is_published",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input"}),
            "description": forms.Textarea(attrs={"class": "form-textarea", "rows": 6}),
            "event_type": forms.Select(attrs={"class": "form-select"}),
            "venue": forms.Select(attrs={"class": "form-select"}),
            "organizing_creator": forms.Select(attrs={"class": "form-select"}),
            "organizing_venue": forms.Select(attrs={"class": "form-select"}),
            "start_datetime": forms.DateTimeInput(attrs={"class": "form-input", "type": "datetime-local"}),
            "end_datetime": forms.DateTimeInput(attrs={"class": "form-input", "type": "datetime-local"}),
            "doors_time": forms.TimeInput(attrs={"class": "form-input", "type": "time"}),
            "ticket_price_cents": forms.NumberInput(attrs={"class": "form-input", "placeholder": "e.g., 1500 for $15.00"}),
            "ticket_url": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://"}),
            "stream_url": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://"}),
        }


class BookingRequestForm(forms.ModelForm):
    """Form for creating a new booking request."""

    class Meta:
        model = BookingRequest
        fields = [
            "event_type",
            "preferred_dates",
            "message",
        ]
        widgets = {
            "event_type": forms.Select(attrs={"class": "form-select"}),
            "preferred_dates": forms.Textarea(attrs={
                "class": "form-textarea", "rows": 3,
                "placeholder": "e.g., Any Friday in August, or specific dates",
            }),
            "message": forms.Textarea(attrs={
                "class": "form-textarea", "rows": 5,
                "placeholder": "Introduce yourself and describe what you have in mind.",
            }),
        }


class BookingResponseForm(forms.Form):
    """Form for responding to a booking request (accept or decline)."""

    action = forms.ChoiceField(
        choices=[("accept", "Accept"), ("decline", "Decline")],
        widget=forms.HiddenInput(),
    )
    response_message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-textarea", "rows": 4,
            "placeholder": "Optional — add a message with your response.",
        }),
    )


class EventSlotForm(forms.ModelForm):
    """Form for adding/editing a slot in an event lineup."""

    class Meta:
        model = EventSlot
        fields = [
            "creator",
            "start_time",
            "end_time",
            "venue_area",
            "set_description",
            "sort_order",
            "status",
        ]
        widgets = {
            "creator": forms.Select(attrs={"class": "form-select"}),
            "start_time": forms.TimeInput(attrs={"class": "form-input", "type": "time"}),
            "end_time": forms.TimeInput(attrs={"class": "form-input", "type": "time"}),
            "venue_area": forms.Select(attrs={"class": "form-select"}),
            "set_description": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., Acoustic Set, Live Painting",
            }),
            "sort_order": forms.NumberInput(attrs={"class": "form-input w-20"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit venue_area choices to the event's venue (if any)
        if event and event.venue:
            self.fields["venue_area"].queryset = event.venue.areas.all()
        else:
            self.fields["venue_area"].queryset = self.fields["venue_area"].queryset.none()
            self.fields["venue_area"].widget = forms.HiddenInput()
        # Only show published creators
        from apps.creators.models import CreatorProfile
        self.fields["creator"].queryset = CreatorProfile.objects.filter(
            publish_status="published"
        ).order_by("display_name")


class BookingFeedbackForm(forms.ModelForm):
    class Meta:
        model = BookingFeedback
        fields = ["body", "would_work_again"]
        widgets = {
            "body": forms.Textarea(attrs={
                "class": "form-textarea", "rows": 4,
                "placeholder": "Share your experience — only the other party will see this.",
            }),
        }
        labels = {
            "would_work_again": "Would you work together again?",
        }


class EndorsementForm(forms.ModelForm):
    class Meta:
        model = Endorsement
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={
                "class": "form-textarea", "rows": 3,
                "placeholder": "A short recommendation based on your experience working together.",
            }),
        }
        labels = {
            "body": "Endorsement",
        }
