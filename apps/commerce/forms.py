import bleach
from django import forms

from apps.core.models import BlockedWord

from .models import Product, ProductGroup, ProductImage

ALLOWED_TAGS = ["p", "br", "strong", "em", "a", "ul", "ol", "li", "h2", "h3", "h4"]
ALLOWED_ATTRS = {"a": ["href", "title", "target", "rel"]}


class ProductForm(forms.ModelForm):
    price_dollars = forms.DecimalField(
        max_digits=7,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-input",
            "placeholder": "0.00",
            "step": "0.01",
            "min": "0",
        }),
        label="Price ($)",
    )

    shipping_dollars = forms.DecimalField(
        required=False,
        max_digits=7,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-input",
            "placeholder": "0.00",
            "step": "0.01",
            "min": "0",
        }),
        label="Shipping ($)",
        help_text="Flat-rate shipping cost. Leave blank or 0 for free shipping.",
    )

    class Meta:
        model = Product
        fields = [
            "title",
            "description",
            "product_type",
            "is_digital",
            "file",
            "inventory_count",
            "shipping_note",
            "is_active",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "Product name"}),
            "description": forms.Textarea(attrs={"class": "form-textarea", "rows": 4, "placeholder": "Describe your product..."}),
            "product_type": forms.Select(attrs={"class": "form-select"}),
            "inventory_count": forms.NumberInput(attrs={"class": "form-input", "placeholder": "Leave blank for unlimited"}),
            "shipping_note": forms.Textarea(attrs={"class": "form-textarea", "rows": 2, "placeholder": "e.g., Ships within 3-5 business days"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.price_cents:
                self.fields["price_dollars"].initial = self.instance.price_cents / 100
            if self.instance.shipping_cents:
                self.fields["shipping_dollars"].initial = self.instance.shipping_cents / 100
        self.fields["is_active"].initial = True

    def clean(self):
        cleaned = super().clean()
        price = cleaned.get("price_dollars")
        cleaned["price_cents"] = int(price * 100) if price else 0
        shipping = cleaned.get("shipping_dollars")
        cleaned["shipping_cents"] = int(shipping * 100) if shipping else 0
        return cleaned

    def save(self, commit=True):
        product = super().save(commit=False)
        product.price_cents = self.cleaned_data.get("price_cents", 0)
        product.shipping_cents = self.cleaned_data.get("shipping_cents", 0)
        if commit:
            product.save()
            self.save_m2m()
        return product

    def clean_description(self):
        value = self.cleaned_data.get("description", "")
        if value:
            if BlockedWord.check_content(value):
                raise forms.ValidationError(
                    "This field contains content that isn't allowed."
                )
            value = bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
        return value


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "sort_order"]
        widgets = {
            "alt_text": forms.TextInput(attrs={"class": "form-input", "placeholder": "Describe the image"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-input w-20"}),
        }


class ProductGroupForm(forms.ModelForm):
    bundle_price_dollars = forms.DecimalField(
        max_digits=7,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-input",
            "placeholder": "0.00",
            "step": "0.01",
            "min": "0",
        }),
        label="Bundle Price ($)",
    )

    class Meta:
        model = ProductGroup
        fields = [
            "title",
            "description",
            "group_type",
            "image",
            "is_active",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g., Appalachian Sessions, Wildflower Tea Set"}),
            "description": forms.Textarea(attrs={"class": "form-textarea", "rows": 4, "placeholder": "Describe this collection or set..."}),
            "group_type": forms.RadioSelect(),
        }

    def __init__(self, *args, creator=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.bundle_price_cents:
            self.fields["bundle_price_dollars"].initial = self.instance.bundle_price_cents / 100
        self._creator = creator

    def clean(self):
        cleaned = super().clean()
        price = cleaned.get("bundle_price_dollars")
        if price:
            cleaned["bundle_price_cents"] = int(price * 100)
        else:
            cleaned["bundle_price_cents"] = 0
        return cleaned

    def clean_description(self):
        value = self.cleaned_data.get("description", "")
        if value:
            if BlockedWord.check_content(value):
                raise forms.ValidationError("This field contains content that isn't allowed.")
            value = bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
        return value

    def save(self, commit=True):
        group = super().save(commit=False)
        group.bundle_price_cents = self.cleaned_data.get("bundle_price_cents", 0)
        if self._creator:
            group.creator = self._creator
        if commit:
            group.save()
            self.save_m2m()
        return group
