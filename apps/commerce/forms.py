from django import forms

from .models import Product


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
