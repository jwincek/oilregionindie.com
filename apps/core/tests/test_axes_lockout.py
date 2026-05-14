"""
Smoke test for django-axes brute-force lockout.

We trust axes' own test suite to verify the lockout mechanics; this
test exists just to confirm the wiring (INSTALLED_APPS, middleware
order, authentication backend) holds together in *our* configuration
and that a burst of failed logins against allauth's endpoint actually
triggers axes' lockout response.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

User = get_user_model()


@override_settings(
    # Allauth's signup confirmation is mandatory in production settings —
    # we just want a user we can fail to authenticate against.
    ACCOUNT_EMAIL_VERIFICATION="none",
)
class AxesLockoutTest(TestCase):
    def setUp(self):
        from axes.utils import reset
        reset()
        self.addCleanup(reset)
        self.user = User.objects.create_user(
            username="locktest", email="locktest@example.com",
            password="correct-password",
        )

    def test_burst_of_failed_logins_triggers_lockout(self):
        """Beyond AXES_FAILURE_LIMIT failures, allauth's login endpoint
        must return a 4xx lockout response (axes uses 429 by default;
        we accept any 403/429 to be tolerant of axes-version drift)."""
        from axes.models import AccessAttempt
        responses = []
        # Two attempts past the limit — guarantees at least one is blocked
        # regardless of whether axes locks at the limit-th or limit+1-th.
        for _ in range(settings.AXES_FAILURE_LIMIT + 2):
            responses.append(self.client.post(
                reverse("account_login"),
                {"login": "locktest", "password": "wrong"},
            ).status_code)
        # At least one response was a lockout response.
        self.assertTrue(
            any(code in (403, 429) for code in responses),
            f"No lockout response observed in {responses}",
        )
        # And axes recorded the failures (so wiring is correct).
        self.assertTrue(AccessAttempt.objects.exists())
