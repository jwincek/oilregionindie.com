import bleach
from django import forms

from apps.core.models import BlockedWord

from .models import Product

ALLOWED_TAGS = ["p", "br", "strong", "em", "a", "ul", "ol", "li", "h2", "h3", "h4"]
ALLOWED_ATTRS = {"a": ["href", "title", "target", "rel"]}


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "title",
            "slug",
            "description",
            "product_type",
            "price_cents",
            "is_digital",
            "file",
            "inventory_count",
            "shipping_note",
            "is_active",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input"}),
            "slug": forms.TextInput(attrs={"class": "form-input"}),
            "description": forms.Textarea(attrs={"class": "form-textarea", "rows": 4}),
            "product_type": forms.Select(attrs={"class": "form-select"}),
            "price_cents": forms.NumberInput(attrs={"class": "form-input", "placeholder": "e.g., 1000 for $10.00"}),
            "inventory_count": forms.NumberInput(attrs={"class": "form-input", "placeholder": "Leave blank for unlimited"}),
            "shipping_note": forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
        }

    def clean_description(self):
        value = self.cleaned_data.get("description", "")
        if value:
            if BlockedWord.check_content(value):
                raise forms.ValidationError(
                    "This field contains content that isn't allowed."
                )
            value = bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
        return value
