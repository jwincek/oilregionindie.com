from django import forms

from apps.core.models import BlockedWord

from .models import CommunityPost


class CommunityPostForm(forms.ModelForm):
    class Meta:
        model = CommunityPost
        fields = ["title", "body", "post_type", "tags"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Post title (optional for discussions)",
            }),
            "body": forms.Textarea(attrs={
                "class": "form-textarea", "rows": 6,
                "placeholder": "What's on your mind?",
            }),
            "post_type": forms.Select(attrs={"class": "form-select"}),
            "tags": forms.CheckboxSelectMultiple(),
        }

    def clean_body(self):
        body = self.cleaned_data.get("body", "")
        blocked = BlockedWord.check_content(body)
        if blocked:
            raise forms.ValidationError(
                "Your post contains content that isn't allowed. "
                "Please review our Code of Conduct."
            )
        return body


class ReplyForm(forms.ModelForm):
    class Meta:
        model = CommunityPost
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={
                "class": "form-textarea", "rows": 3,
                "placeholder": "Write a reply...",
            }),
        }

    def clean_body(self):
        body = self.cleaned_data.get("body", "")
        blocked = BlockedWord.check_content(body)
        if blocked:
            raise forms.ValidationError(
                "Your reply contains content that isn't allowed. "
                "Please review our Code of Conduct."
            )
        return body
