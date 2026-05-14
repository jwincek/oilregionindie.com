"""
Tests for the deploy-time invariant checks in apps.core.checks.

Each check is a tiny pure function over settings, so we can call them
directly and use override_settings to drive the branches. This sidesteps
the registry-machinery dance (Django's check framework runs these under
`manage.py check --deploy`; we just need to verify the rule logic).

The check IDs (oilregion.E001…W007) are part of the contract documented
in DEPLOYMENT.md, so we assert on the ids explicitly.
"""

from django.core.checks import Error, Warning
from django.test import SimpleTestCase, override_settings

from apps.core import checks


def _ids(issues):
    return [i.id for i in issues]


# ---------------------------------------------------------------------------
# E001 — DJANGO_SECRET_KEY
# ---------------------------------------------------------------------------


class SecretKeyCheckTest(SimpleTestCase):
    @override_settings(SECRET_KEY="some-real-long-random-value-here-1234567890")
    def test_passes_when_secret_is_real(self):
        self.assertEqual(checks.check_secret_key_not_placeholder(None), [])

    @override_settings(SECRET_KEY="change-me-to-a-real-secret-key")
    def test_fails_when_secret_is_example_placeholder(self):
        issues = checks.check_secret_key_not_placeholder(None)
        self.assertEqual(_ids(issues), ["oilregion.E001"])
        self.assertIsInstance(issues[0], Error)
        # Empty SECRET_KEY is already an ImproperlyConfigured at settings-
        # load time (Django guards it), so we don't test that branch here.


# ---------------------------------------------------------------------------
# E002 — DJANGO_ALLOWED_HOSTS
# ---------------------------------------------------------------------------


class AllowedHostsCheckTest(SimpleTestCase):
    @override_settings(ALLOWED_HOSTS=["oilregionindie.com"])
    def test_passes_when_real_host_set(self):
        self.assertEqual(checks.check_allowed_hosts_not_default(None), [])

    @override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1"])
    def test_fails_when_still_at_dev_default(self):
        issues = checks.check_allowed_hosts_not_default(None)
        self.assertEqual(_ids(issues), ["oilregion.E002"])
        self.assertIsInstance(issues[0], Error)

    @override_settings(ALLOWED_HOSTS=["localhost"])
    def test_fails_when_subset_of_dev_default(self):
        """Just 'localhost' alone still counts as the dev default."""
        issues = checks.check_allowed_hosts_not_default(None)
        self.assertEqual(_ids(issues), ["oilregion.E002"])

    @override_settings(ALLOWED_HOSTS=["localhost", "example.com"])
    def test_passes_when_dev_host_plus_real_host(self):
        """A real host alongside localhost is fine — devs commonly keep
        localhost in the list for ad-hoc local debugging."""
        self.assertEqual(checks.check_allowed_hosts_not_default(None), [])


# ---------------------------------------------------------------------------
# E003 — EMAIL_BACKEND
# ---------------------------------------------------------------------------


class EmailBackendCheckTest(SimpleTestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    def test_passes_for_smtp(self):
        self.assertEqual(checks.check_email_backend_not_filebased(None), [])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.filebased.EmailBackend")
    def test_fails_for_filebased(self):
        issues = checks.check_email_backend_not_filebased(None)
        self.assertEqual(_ids(issues), ["oilregion.E003"])
        self.assertIsInstance(issues[0], Error)

    @override_settings(EMAIL_BACKEND="anymail.backends.mailgun.EmailBackend")
    def test_passes_for_third_party_smtp_wrapper(self):
        """Any backend that doesn't have 'filebased' in its dotted path
        is acceptable — covers anymail, sendgrid, mailgun, etc."""
        self.assertEqual(checks.check_email_backend_not_filebased(None), [])


# ---------------------------------------------------------------------------
# E004 / W005 / W006 — Stripe
# ---------------------------------------------------------------------------


class StripeKeyCheckTest(SimpleTestCase):
    @override_settings(
        FEATURE_COMMERCE=False,
        STRIPE_SECRET_KEY="",
        STRIPE_PUBLIC_KEY="",
    )
    def test_silent_when_commerce_disabled_regardless_of_keys(self):
        self.assertEqual(checks.check_stripe_keys_when_commerce_enabled(None), [])

    @override_settings(
        FEATURE_COMMERCE=True,
        STRIPE_SECRET_KEY="",
        STRIPE_PUBLIC_KEY="",
    )
    def test_e004_when_commerce_enabled_but_keys_blank(self):
        issues = checks.check_stripe_keys_when_commerce_enabled(None)
        self.assertEqual(_ids(issues), ["oilregion.E004"])
        self.assertIsInstance(issues[0], Error)

    @override_settings(
        FEATURE_COMMERCE=True,
        STRIPE_SECRET_KEY="sk_live_real_secret",
        STRIPE_PUBLIC_KEY="",
    )
    def test_e004_when_only_one_key_is_missing(self):
        """Both keys are required when commerce is enabled."""
        issues = checks.check_stripe_keys_when_commerce_enabled(None)
        self.assertEqual(_ids(issues), ["oilregion.E004"])

    @override_settings(
        FEATURE_COMMERCE=True,
        STRIPE_SECRET_KEY="sk_test_xxxxx",
        STRIPE_PUBLIC_KEY="pk_test_xxxxx",
    )
    def test_w005_w006_when_both_keys_in_test_mode(self):
        issues = checks.check_stripe_keys_when_commerce_enabled(None)
        self.assertEqual(_ids(issues), ["oilregion.W005", "oilregion.W006"])
        for w in issues:
            self.assertIsInstance(w, Warning)

    @override_settings(
        FEATURE_COMMERCE=True,
        STRIPE_SECRET_KEY="sk_test_xxxxx",
        STRIPE_PUBLIC_KEY="pk_live_real",
    )
    def test_w005_only_when_just_secret_is_test_mode(self):
        issues = checks.check_stripe_keys_when_commerce_enabled(None)
        self.assertEqual(_ids(issues), ["oilregion.W005"])

    @override_settings(
        FEATURE_COMMERCE=True,
        STRIPE_SECRET_KEY="sk_live_real",
        STRIPE_PUBLIC_KEY="pk_test_xxxxx",
    )
    def test_w006_only_when_just_public_is_test_mode(self):
        issues = checks.check_stripe_keys_when_commerce_enabled(None)
        self.assertEqual(_ids(issues), ["oilregion.W006"])

    @override_settings(
        FEATURE_COMMERCE=True,
        STRIPE_SECRET_KEY="sk_live_real",
        STRIPE_PUBLIC_KEY="pk_live_real",
    )
    def test_silent_when_both_keys_in_live_mode(self):
        self.assertEqual(checks.check_stripe_keys_when_commerce_enabled(None), [])


# ---------------------------------------------------------------------------
# W007 — Turnstile
# ---------------------------------------------------------------------------


class TurnstileCheckTest(SimpleTestCase):
    @override_settings(
        TURNSTILE_SITE_KEY="0x4AAAAAAA_real_site",
        TURNSTILE_SECRET_KEY="0x4AAAAAAA_real_secret",
    )
    def test_passes_when_both_keys_set(self):
        self.assertEqual(checks.check_turnstile_configured(None), [])

    @override_settings(TURNSTILE_SITE_KEY="", TURNSTILE_SECRET_KEY="")
    def test_warns_when_both_blank(self):
        issues = checks.check_turnstile_configured(None)
        self.assertEqual(_ids(issues), ["oilregion.W007"])
        self.assertIsInstance(issues[0], Warning)

    @override_settings(
        TURNSTILE_SITE_KEY="0x4AAAAAAA",
        TURNSTILE_SECRET_KEY="",
    )
    def test_warns_when_only_one_is_set(self):
        """Half-configured Turnstile (one key set, the other blank) is
        non-functional and should be flagged the same as missing both."""
        issues = checks.check_turnstile_configured(None)
        self.assertEqual(_ids(issues), ["oilregion.W007"])


# ---------------------------------------------------------------------------
# Integration smoke: confirm the checks are actually registered with
# Django's framework so `manage.py check --deploy` would invoke them.
# ---------------------------------------------------------------------------


class ChecksAreRegisteredTest(SimpleTestCase):
    def test_all_oilregion_checks_are_in_the_registry(self):
        from django.core.checks.registry import registry
        # `deploy=True` checks live in deployment_checks, not the main set.
        registered = registry.get_checks(include_deployment_checks=True)
        names = {fn.__name__ for fn in registered}
        for expected in (
            "check_secret_key_not_placeholder",
            "check_allowed_hosts_not_default",
            "check_email_backend_not_filebased",
            "check_stripe_keys_when_commerce_enabled",
            "check_turnstile_configured",
        ):
            self.assertIn(expected, names, f"{expected} not registered")
