from django import forms

from apps.core.models import Address

from .models import VenueProfile


class VenueProfileForm(forms.ModelForm):
    """
    Venue profile form that also collects address fields inline.
    Creates or updates an Address object on save.
    """

    # Address fields presented inline (not as a nested FK chooser)
    street = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-textarea", "rows": 2, "placeholder": "Street address"}),
    )
    address_city = forms.CharField(
        label="City",
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    address_state = forms.CharField(
        label="State",
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    zip_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )

    class Meta:
        model = VenueProfile
        fields = [
            "name",
            "description",
            "venue_type",
            "capacity",
            "website",
            "amenities",
            "profile_image",
            "header_image",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input"}),
            "description": forms.Textarea(attrs={"class": "form-textarea", "rows": 6}),
            "venue_type": forms.Select(attrs={"class": "form-select"}),
            "capacity": forms.NumberInput(attrs={"class": "form-input"}),
            "website": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://"}),
            "amenities": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate address fields from existing Address FK
        if self.instance and self.instance.pk and self.instance.address:
            addr = self.instance.address
            self.fields["street"].initial = addr.street
            self.fields["address_city"].initial = addr.city
            self.fields["address_state"].initial = addr.state
            self.fields["zip_code"].initial = addr.zip_code
        elif self.instance and self.instance.pk:
            # Fallback to legacy city/state fields
            self.fields["address_city"].initial = self.instance.city
            self.fields["address_state"].initial = self.instance.state

    def save(self, commit=True):
        venue = super().save(commit=False)

        # Create or update the Address
        city = self.cleaned_data["address_city"]
        state = self.cleaned_data["address_state"]
        street = self.cleaned_data.get("street", "")
        zip_code = self.cleaned_data.get("zip_code", "")

        if venue.address:
            addr = venue.address
            addr.street = street
            addr.city = city
            addr.state = state
            addr.zip_code = zip_code
            addr.save()
        else:
            addr = Address.objects.create(
                street=street, city=city, state=state, zip_code=zip_code
            )
            venue.address = addr

        # Keep legacy city/state in sync for queries
        venue.city = city
        venue.state = state

        if commit:
            venue.save()
            self.save_m2m()
        return venue
