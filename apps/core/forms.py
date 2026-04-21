import httpx
from allauth.account.forms import SignupForm
from django import forms
from django.conf import settings


class TurnstileSignupForm(SignupForm):
    """
    Extends allauth's SignupForm to add Cloudflare Turnstile validation.
    If TURNSTILE_SECRET_KEY is not configured, the check is skipped
    (so local dev works without keys).
    """

    cf_turnstile_response = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )

    def clean_cf_turnstile_response(self):
        token = self.cleaned_data.get("cf_turnstile_response", "")
        secret = getattr(settings, "TURNSTILE_SECRET_KEY", "")

        # Skip validation if Turnstile isn't configured (local dev)
        if not secret:
            return token

        if not token:
            raise forms.ValidationError(
                "Please complete the security check."
            )

        # Verify the token with Cloudflare
        response = httpx.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret, "response": token},
            timeout=5,
        )

        result = response.json()
        if not result.get("success"):
            raise forms.ValidationError(
                "Security check failed. Please try again."
            )

        return token
