"""
Interactive setup wizard for first-time deploy and reconfiguration.

Walks through three sections:
  - Infrastructure  → writes .env (database, secret key, email, Stripe, …)
  - Branding        → writes the SiteBranding model (site name, footer copy, …)
  - Bootstrap       → runs migrate, optionally creates a superuser, seeds
                      starter pages, and registers Django Q schedules.

Idempotent: re-running shows current values as defaults; pressing Enter past
any prompt keeps the existing value. Backs up .env to .env.backup before
overwriting.

Usage:
    python manage.py setup
    python manage.py setup --skip-branding
    python manage.py setup --skip-infrastructure --skip-bootstrap
"""

import getpass
import re
import secrets
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


_KV_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


class EnvFile:
    """Round-trip an .env file: preserves comments, blank lines, and key order."""

    def __init__(self, path: Path):
        self.path = path
        self._lines: list[str] = []
        self._index: dict[str, int] = {}
        if path.exists():
            self._lines = path.read_text().splitlines()
            for i, line in enumerate(self._lines):
                m = _KV_RE.match(line)
                if m:
                    self._index[m.group(1)] = i

    def get(self, key: str, default: str = "") -> str:
        if key not in self._index:
            return default
        raw = _KV_RE.match(self._lines[self._index[key]]).group(2)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
            raw = raw[1:-1]
        return raw

    def set(self, key: str, value: str) -> None:
        formatted = self._format(value)
        line = f"{key}={formatted}"
        if key in self._index:
            self._lines[self._index[key]] = line
        else:
            self._index[key] = len(self._lines)
            self._lines.append(line)

    @staticmethod
    def _format(value: str) -> str:
        if value == "":
            return ""
        if any(c in value for c in " \t#\"'") and not (value.startswith('"') and value.endswith('"')):
            escaped = value.replace('"', '\\"')
            return f'"{escaped}"'
        return value

    def write(self) -> None:
        backup = self.path.with_suffix(self.path.suffix + ".backup")
        if self.path.exists():
            shutil.copy2(self.path, backup)
        text = "\n".join(self._lines)
        if not text.endswith("\n"):
            text += "\n"
        self.path.write_text(text)


def _prompt(label: str, default: str = "", *, secret: bool = False) -> str:
    if secret:
        shown = "[keep existing]" if default else "[blank]"
    else:
        shown = f"[{default}]" if default else "[blank]"
    raw_input_fn = getpass.getpass if secret else input
    raw = raw_input_fn(f"  {label} {shown}: ").strip()
    return raw if raw else default


def _confirm(label: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"  {label} {suffix}: ").strip().lower()
    if not raw:
        return default
    return raw[0] == "y"


class Command(BaseCommand):
    help = "Interactive setup wizard for first-time deploy and reconfiguration."

    def add_arguments(self, parser):
        parser.add_argument("--skip-infrastructure", action="store_true",
            help="Skip the .env section.")
        parser.add_argument("--skip-branding", action="store_true",
            help="Skip the SiteBranding section.")
        parser.add_argument("--skip-bootstrap", action="store_true",
            help="Skip migrate / superuser / seed_data / setup_schedules.")

    def handle(self, *args, **opts):
        self.stdout.write(self.style.NOTICE("\n=== Site setup wizard ===\n"))
        self.stdout.write("Press Enter to keep the [bracketed] default. Ctrl-C to abort.\n")

        if not opts["skip_infrastructure"]:
            self._infrastructure()
        if not opts["skip_branding"]:
            self._branding()
        if not opts["skip_bootstrap"]:
            self._bootstrap()

        self.stdout.write(self.style.SUCCESS("\nSetup complete.\n"))

    # ------------------------------------------------------------------ infra
    def _infrastructure(self):
        self.stdout.write(self.style.NOTICE("\n-- Infrastructure (.env) --"))
        env = EnvFile(Path(settings.BASE_DIR) / ".env")

        # Secret key: auto-generate if missing, otherwise offer to regenerate.
        existing_secret = env.get("DJANGO_SECRET_KEY")
        if not existing_secret or existing_secret == "change-me-to-a-real-secret-key":
            env.set("DJANGO_SECRET_KEY", secrets.token_urlsafe(50))
            self.stdout.write("  DJANGO_SECRET_KEY: generated.")
        elif _confirm("Regenerate DJANGO_SECRET_KEY? (logs all users out)", default=False):
            env.set("DJANGO_SECRET_KEY", secrets.token_urlsafe(50))

        # Core flags
        debug_default = env.get("DJANGO_DEBUG", "False").lower() in ("true", "1", "yes")
        debug = _confirm("Enable DEBUG mode?", default=debug_default)
        env.set("DJANGO_DEBUG", "True" if debug else "False")

        env.set("DJANGO_ALLOWED_HOSTS", _prompt(
            "Allowed hosts (comma-separated)",
            env.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"),
        ))

        soft_default = env.get("SOFT_LAUNCH", "False").lower() in ("true", "1", "yes")
        env.set("SOFT_LAUNCH", "True" if _confirm("Show soft-launch banner?", default=soft_default) else "False")

        # Database & cache
        env.set("DATABASE_URL", _prompt(
            "DATABASE_URL",
            env.get("DATABASE_URL", "sqlite:///db.sqlite3"),
        ))
        env.set("REDIS_URL", _prompt(
            "REDIS_URL (blank to disable)",
            env.get("REDIS_URL"),
        ))

        # Optional sections
        if _confirm("\nConfigure SMTP email?", default=bool(env.get("EMAIL_HOST"))):
            self._email_section(env)
        if _confirm("\nConfigure Stripe (payments)?", default=bool(env.get("STRIPE_SECRET_KEY"))):
            self._stripe_section(env)
        if _confirm("\nConfigure Cloudflare Turnstile (signup bot protection)?",
                    default=bool(env.get("TURNSTILE_SITE_KEY"))):
            env.set("TURNSTILE_SITE_KEY", _prompt("TURNSTILE_SITE_KEY", env.get("TURNSTILE_SITE_KEY")))
            env.set("TURNSTILE_SECRET_KEY", _prompt(
                "TURNSTILE_SECRET_KEY", env.get("TURNSTILE_SECRET_KEY"), secret=True,
            ))
        if _confirm("\nConfigure S3-compatible storage?",
                    default=bool(env.get("AWS_STORAGE_BUCKET_NAME"))):
            self._s3_section(env)

        if _confirm("\nWrite changes to .env?", default=True):
            env.write()
            self.stdout.write(self.style.SUCCESS(f"  Wrote {env.path} (backup at {env.path}.backup)."))
        else:
            self.stdout.write(self.style.WARNING("  Skipped — .env not modified."))

    def _email_section(self, env: EnvFile):
        env.set("EMAIL_HOST", _prompt("EMAIL_HOST", env.get("EMAIL_HOST", "localhost")))
        env.set("EMAIL_PORT", _prompt("EMAIL_PORT", env.get("EMAIL_PORT", "587")))
        env.set("EMAIL_HOST_USER", _prompt("EMAIL_HOST_USER", env.get("EMAIL_HOST_USER")))
        env.set("EMAIL_HOST_PASSWORD", _prompt(
            "EMAIL_HOST_PASSWORD", env.get("EMAIL_HOST_PASSWORD"), secret=True,
        ))
        tls_default = env.get("EMAIL_USE_TLS", "True").lower() in ("true", "1", "yes")
        env.set("EMAIL_USE_TLS", "True" if _confirm("Use TLS?", default=tls_default) else "False")
        env.set("DEFAULT_FROM_EMAIL", _prompt(
            "DEFAULT_FROM_EMAIL", env.get("DEFAULT_FROM_EMAIL", "noreply@example.com"),
        ))
        env.set("SERVER_EMAIL", _prompt(
            "SERVER_EMAIL (sender for error notifications)",
            env.get("SERVER_EMAIL", env.get("DEFAULT_FROM_EMAIL", "errors@example.com")),
        ))
        env.set("DJANGO_ADMINS", _prompt(
            "DJANGO_ADMINS (Name:email,Name:email)", env.get("DJANGO_ADMINS"),
        ))

    def _stripe_section(self, env: EnvFile):
        env.set("STRIPE_PUBLIC_KEY", _prompt("STRIPE_PUBLIC_KEY", env.get("STRIPE_PUBLIC_KEY")))
        env.set("STRIPE_SECRET_KEY", _prompt(
            "STRIPE_SECRET_KEY", env.get("STRIPE_SECRET_KEY"), secret=True,
        ))
        env.set("STRIPE_WEBHOOK_SECRET", _prompt(
            "STRIPE_WEBHOOK_SECRET", env.get("STRIPE_WEBHOOK_SECRET"), secret=True,
        ))
        env.set("STRIPE_PLATFORM_FEE_PERCENT", _prompt(
            "STRIPE_PLATFORM_FEE_PERCENT", env.get("STRIPE_PLATFORM_FEE_PERCENT", "0"),
        ))

    def _s3_section(self, env: EnvFile):
        env.set("AWS_STORAGE_BUCKET_NAME", _prompt(
            "AWS_STORAGE_BUCKET_NAME", env.get("AWS_STORAGE_BUCKET_NAME"),
        ))
        env.set("AWS_ACCESS_KEY_ID", _prompt(
            "AWS_ACCESS_KEY_ID", env.get("AWS_ACCESS_KEY_ID"),
        ))
        env.set("AWS_SECRET_ACCESS_KEY", _prompt(
            "AWS_SECRET_ACCESS_KEY", env.get("AWS_SECRET_ACCESS_KEY"), secret=True,
        ))
        env.set("AWS_S3_ENDPOINT_URL", _prompt(
            "AWS_S3_ENDPOINT_URL (blank for AWS, e.g. https://… for R2/Backblaze)",
            env.get("AWS_S3_ENDPOINT_URL"),
        ))
        env.set("AWS_S3_REGION_NAME", _prompt(
            "AWS_S3_REGION_NAME", env.get("AWS_S3_REGION_NAME", "us-east-1"),
        ))

    # --------------------------------------------------------------- branding
    def _branding(self):
        self.stdout.write(self.style.NOTICE("\n-- Branding (Wagtail SiteBranding) --"))
        from apps.pages.models import SiteBranding

        try:
            b = SiteBranding.load()
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"  Could not load SiteBranding ({exc}). Run migrations first, then re-run."
            ))
            return

        b.site_name = _prompt("Site name", b.site_name)
        b.tagline = _prompt("Tagline (one line)", b.tagline)
        b.origin_story = _prompt(
            "Footer blurb (one paragraph; edit longer copy in /cms/)", b.origin_story,
        )
        b.contact_email = _prompt("Contact email", b.contact_email)
        b.source_repo_url = _prompt("Source repo URL (blank to hide)", b.source_repo_url)
        b.save()
        self.stdout.write(self.style.SUCCESS("  SiteBranding updated."))

    # -------------------------------------------------------------- bootstrap
    def _bootstrap(self):
        self.stdout.write(self.style.NOTICE("\n-- Bootstrap --"))

        if _confirm("Run database migrations?", default=True):
            call_command("migrate", interactive=False)

        if _confirm("Create a superuser?", default=self._needs_superuser()):
            call_command("createsuperuser")

        if _confirm("Seed Wagtail starter pages?", default=self._needs_starter_pages()):
            call_command("seed_data", "--pages")

        if _confirm("Register Django Q recurring schedules?", default=True):
            call_command("setup_schedules")

    @staticmethod
    def _needs_superuser() -> bool:
        from django.contrib.auth import get_user_model
        return not get_user_model().objects.filter(is_superuser=True).exists()

    @staticmethod
    def _needs_starter_pages() -> bool:
        try:
            from apps.pages.models import HomePage
            return not HomePage.objects.exists()
        except Exception:
            return True
