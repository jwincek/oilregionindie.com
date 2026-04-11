from django import forms

from .models import Event


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
