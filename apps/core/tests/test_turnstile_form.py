"""
Turnstile verification on the signup form.

The interesting cases are the failure modes: Cloudflare being
unreachable (or returning garbage) must surface as a form validation
error — fail closed with a retry message — never as an unhandled
exception that 500s the signup page.
"""
from unittest.mock import Mock, patch

import httpx
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.core.forms import TurnstileSignupForm


@override_settings(TURNSTILE_SECRET_KEY="test-secret")
class TurnstileVerificationTests(TestCase):
    def _clean_token(self, token="tok"):
        form = TurnstileSignupForm()
        form.cleaned_data = {"cf_turnstile_response": token}
        return form.clean_cf_turnstile_response()

    def test_valid_token_passes(self):
        response = Mock()
        response.json.return_value = {"success": True}
        with patch("apps.core.forms.httpx.post", return_value=response):
            self.assertEqual(self._clean_token("tok"), "tok")

    def test_rejected_token_raises_validation_error(self):
        response = Mock()
        response.json.return_value = {"success": False}
        with patch("apps.core.forms.httpx.post", return_value=response):
            with self.assertRaisesMessage(ValidationError, "Security check failed"):
                self._clean_token()

    def test_network_error_is_validation_error_not_500(self):
        with patch(
            "apps.core.forms.httpx.post",
            side_effect=httpx.ConnectTimeout("cloudflare unreachable"),
        ):
            with self.assertRaisesMessage(ValidationError, "could not be verified"):
                self._clean_token()

    def test_garbage_response_body_is_validation_error(self):
        response = Mock()
        response.json.side_effect = ValueError("not json")
        with patch("apps.core.forms.httpx.post", return_value=response):
            with self.assertRaisesMessage(ValidationError, "could not be verified"):
                self._clean_token()

    @override_settings(TURNSTILE_SECRET_KEY="")
    def test_unconfigured_turnstile_skips_verification(self):
        with patch("apps.core.forms.httpx.post") as mock_post:
            self.assertEqual(self._clean_token(""), "")
            mock_post.assert_not_called()
