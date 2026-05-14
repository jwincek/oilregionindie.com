"""
Deploy-time invariant checks.

Wired into Django's ``manage.py check --deploy`` machinery, these fire
only when ``DEBUG=False`` and refuse to start the project if a deployer
has missed a step the setup wizard normally handles. The goal is to
catch "I forked the repo and edited .env by hand" mistakes before they
reach production — placeholder secrets, dev-mode Stripe keys, file-based
email backend leaking verification links into /tmp, and so on.

Each check returns a list of :class:`django.core.checks.Warning` or
:class:`django.core.checks.Error` instances; nothing is raised so all
checks always run and the user sees every problem at once.
"""

from django.conf import settings
from django.core.checks import Error, Warning, register, Tags

_DEV_SECRET_PLACEHOLDER = "change-me-to-a-real-secret-key"


@register(Tags.security, deploy=True)
def check_secret_key_not_placeholder(app_configs, **kwargs):
    # Empty/unset SECRET_KEY is already an ImproperlyConfigured error at
    # settings-load time, so we only need to catch the example value here.
    if settings.SECRET_KEY == _DEV_SECRET_PLACEHOLDER:
        return [Error(
            "DJANGO_SECRET_KEY is set to the example placeholder.",
            hint="Run `python manage.py setup` (it auto-generates a key) "
                 "or set DJANGO_SECRET_KEY in .env to a long random value.",
            id="oilregion.E001",
        )]
    return []


@register(Tags.security, deploy=True)
def check_allowed_hosts_not_default(app_configs, **kwargs):
    default_hosts = {"localhost", "127.0.0.1"}
    if set(settings.ALLOWED_HOSTS) <= default_hosts:
        return [Error(
            "DJANGO_ALLOWED_HOSTS is still at the dev default "
            "(localhost, 127.0.0.1).",
            hint="Set DJANGO_ALLOWED_HOSTS in .env to your real production "
                 "hostname(s), comma-separated.",
            id="oilregion.E002",
        )]
    return []


@register(Tags.security, deploy=True)
def check_email_backend_not_filebased(app_configs, **kwargs):
    if "filebased" in settings.EMAIL_BACKEND.lower():
        return [Error(
            "EMAIL_BACKEND is set to the file-based dev backend in production.",
            hint="Verification emails will be written to disk and never "
                 "delivered. Set EMAIL_BACKEND to "
                 "django.core.mail.backends.smtp.EmailBackend (or your "
                 "provider's backend) and configure EMAIL_HOST/EMAIL_PORT/"
                 "EMAIL_HOST_USER/EMAIL_HOST_PASSWORD.",
            id="oilregion.E003",
        )]
    return []


@register(Tags.security, deploy=True)
def check_stripe_keys_when_commerce_enabled(app_configs, **kwargs):
    if not getattr(settings, "FEATURE_COMMERCE", True):
        return []
    issues = []
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PUBLIC_KEY:
        issues.append(Error(
            "FEATURE_COMMERCE is enabled but Stripe keys are not set.",
            hint="Set STRIPE_PUBLIC_KEY, STRIPE_SECRET_KEY, and "
                 "STRIPE_WEBHOOK_SECRET in .env, or disable commerce "
                 "with FEATURE_COMMERCE=False.",
            id="oilregion.E004",
        ))
    else:
        if settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
            issues.append(Warning(
                "Stripe secret key is in test mode (sk_test_…) in production.",
                hint="Intentional during a soft launch — switch to your "
                     "sk_live_… key for real payments.",
                id="oilregion.W005",
            ))
        if settings.STRIPE_PUBLIC_KEY.startswith("pk_test_"):
            issues.append(Warning(
                "Stripe publishable key is in test mode (pk_test_…) in "
                "production.",
                hint="Pair with the matching pk_live_… key when going live.",
                id="oilregion.W006",
            ))
    return issues


@register(Tags.security, deploy=True)
def check_turnstile_configured(app_configs, **kwargs):
    if not (settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY):
        return [Warning(
            "Cloudflare Turnstile keys are not configured.",
            hint="Signups are unprotected from bot accounts. Set "
                 "TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY in .env, or "
                 "accept the risk for a small/closed community.",
            id="oilregion.W007",
        )]
    return []
