from django import forms

from .models import CreatorMembership, CreatorProfile, CreatorSocialLink, MediaItem, Skill


class GroupedSkillWidget(forms.CheckboxSelectMultiple):
    """
    Renders skills grouped by discipline for easier selection.
    Uses the standard CheckboxSelectMultiple but the template can
    access skill.discipline for grouping.
    """
    pass


class CreatorProfileForm(forms.ModelForm):
    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.select_related("discipline").order_by("discipline__name", "name"),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        help_text="Select your specific skills. Disciplines will be set automatically based on your choices.",
    )

    class Meta:
        model = CreatorProfile
        fields = [
            "display_name",
            "profile_type",
            "bio",
            "skills",
            "disciplines",
            "genres",
            "location",
            "home_region",
            "website",
            "profile_image",
            "header_image",
            "is_published",
        ]
        widgets = {
            "display_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "Your name, band name, or collective name"}),
            "profile_type": forms.RadioSelect(),
            "bio": forms.Textarea(attrs={"class": "form-textarea", "rows": 6}),
            "disciplines": forms.CheckboxSelectMultiple(),
            "genres": forms.CheckboxSelectMultiple(),
            "location": forms.TextInput(attrs={"class": "form-input", "placeholder": "Where you are now"}),
            "home_region": forms.TextInput(attrs={"class": "form-input", "placeholder": "Where you're from"}),
            "website": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://"}),
        }
        help_texts = {
            "disciplines": "Auto-filled from skills, but you can add more if needed.",
        }

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit:
            # After saving m2m relations, sync disciplines from skills
            profile.sync_disciplines_from_skills()
        return profile


class MediaItemForm(forms.ModelForm):
    embed_code = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-textarea",
            "rows": 4,
            "placeholder": 'Paste embed code here (e.g., Bandcamp\'s <iframe> code from Share/Embed)',
        }),
        help_text=(
            "For providers that don't support automatic embedding (like Bandcamp), "
            "paste the embed code directly. Use the Share/Embed button on the provider's site. "
            "If you provide both a URL and an embed code, the embed code takes priority."
        ),
    )

    class Meta:
        model = MediaItem
        fields = [
            "title",
            "media_type",
            "file",
            "embed_url",
            "embed_code",
            "thumbnail",
            "description",
            "sort_order",
            "is_featured",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-input"}),
            "media_type": forms.Select(attrs={"class": "form-select"}),
            "embed_url": forms.URLInput(attrs={
                "class": "form-input",
                "placeholder": "YouTube, SoundCloud, or Vimeo URL (auto-embeds)",
            }),
            "description": forms.Textarea(attrs={"class": "form-textarea", "rows": 3}),
            "sort_order": forms.NumberInput(attrs={"class": "form-input w-20"}),
        }
        help_texts = {
            "embed_url": "Works automatically with YouTube, SoundCloud, Vimeo, and other oEmbed providers.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate embed_code from existing embed_html if editing
        if self.instance and self.instance.pk and self.instance.embed_html:
            # Only show if it wasn't auto-fetched (heuristic: if there's no embed_url,
            # or the embed_html doesn't look like it was from oEmbed)
            if not self.instance.embed_url:
                self.fields["embed_code"].initial = self.instance.embed_html

    def clean_embed_code(self):
        """Basic sanitization — only allow iframe and similar embed tags."""
        code = self.cleaned_data.get("embed_code", "").strip()
        if not code:
            return ""
        # Must contain an iframe or common embed pattern
        code_lower = code.lower()
        if not any(tag in code_lower for tag in ["<iframe", "<embed", "<object", "<audio", "<video"]):
            raise forms.ValidationError(
                "Embed code must contain an <iframe>, <embed>, <object>, <audio>, or <video> tag. "
                "Copy the full embed code from the provider's Share/Embed option."
            )
        return code

    def save(self, commit=True):
        item = super().save(commit=False)
        embed_code = self.cleaned_data.get("embed_code", "")
        if embed_code:
            # Direct embed code takes priority over oEmbed fetch
            item.embed_html = embed_code
        if commit:
            item.save()
        return item


class CreatorMembershipForm(forms.ModelForm):
    class Meta:
        model = CreatorMembership
        fields = ["member", "role", "is_active", "sort_order"]
        widgets = {
            "member": forms.Select(attrs={"class": "form-select"}),
            "role": forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g., Guitar, Vocals, Visual Director"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-input w-20"}),
        }


class CreatorSocialLinkForm(forms.ModelForm):
    class Meta:
        model = CreatorSocialLink
        fields = ["platform", "url", "sort_order"]
        widgets = {
            "platform": forms.Select(attrs={"class": "form-select"}),
            "url": forms.URLInput(attrs={"class": "form-input", "placeholder": "https://"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-input w-20"}),
        }
