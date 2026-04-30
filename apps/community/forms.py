from django import forms

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
