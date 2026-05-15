"""
Tests for the apps.core.management.commands.setup wizard.

The EnvFile round-trip is covered separately in test_setup_envfile.py.
This module exercises the Command class and the _prompt/_confirm
helpers it uses to drive the interactive sections.

Two patching strategies:
  - For _prompt and _confirm themselves, patch builtins.input and
    getpass.getpass at module level.
  - For Command.* methods, patch _prompt/_confirm at the module path
    `apps.core.management.commands.setup._prompt/_confirm` so the
    Command's calls to them route through our stubs.

`settings.BASE_DIR` is overridden per-test to point at a tempdir so
the wizard writes to throwaway .env files rather than the project's
real one.
"""

import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, SimpleTestCase, override_settings

from apps.core.management.commands import setup as setup_mod
from apps.pages.models import HomePage, SiteBranding

User = get_user_model()


# ---------------------------------------------------------------------------
# _prompt
# ---------------------------------------------------------------------------


class PromptHelperTest(SimpleTestCase):
    def test_returns_default_when_input_blank(self):
        with mock.patch("builtins.input", return_value=""):
            self.assertEqual(setup_mod._prompt("label", "fallback"), "fallback")

    def test_returns_stripped_user_input(self):
        with mock.patch("builtins.input", return_value="  typed value  "):
            self.assertEqual(setup_mod._prompt("label", "d"), "typed value")

    def test_secret_mode_uses_getpass(self):
        with mock.patch("apps.core.management.commands.setup.getpass") as gp:
            gp.getpass.return_value = "shh"
            result = setup_mod._prompt("Password", "", secret=True)
        gp.getpass.assert_called_once()
        self.assertEqual(result, "shh")

    def test_secret_label_shows_keep_existing_when_default_truthy(self):
        with mock.patch("apps.core.management.commands.setup.getpass") as gp:
            gp.getpass.return_value = ""
            setup_mod._prompt("Password", "existing-value", secret=True)
            args = gp.getpass.call_args.args[0]
        self.assertIn("[keep existing]", args)
        # Crucially, the actual secret value isn't echoed in the prompt.
        self.assertNotIn("existing-value", args)

    def test_secret_label_shows_blank_when_default_empty(self):
        with mock.patch("apps.core.management.commands.setup.getpass") as gp:
            gp.getpass.return_value = ""
            setup_mod._prompt("Password", "", secret=True)
            args = gp.getpass.call_args.args[0]
        self.assertIn("[blank]", args)

    def test_plain_label_shows_default_in_brackets(self):
        with mock.patch("builtins.input", return_value="") as inp:
            setup_mod._prompt("Host", "localhost")
            args = inp.call_args.args[0]
        self.assertIn("[localhost]", args)

    def test_plain_label_shows_blank_when_default_empty(self):
        with mock.patch("builtins.input", return_value="") as inp:
            setup_mod._prompt("Optional", "")
            args = inp.call_args.args[0]
        self.assertIn("[blank]", args)


# ---------------------------------------------------------------------------
# _confirm
# ---------------------------------------------------------------------------


class ConfirmHelperTest(SimpleTestCase):
    def test_returns_default_when_empty(self):
        with mock.patch("builtins.input", return_value=""):
            self.assertTrue(setup_mod._confirm("OK?", default=True))
            self.assertFalse(setup_mod._confirm("OK?", default=False))

    def test_y_returns_true(self):
        for typed in ("y", "Y", "yes", "Yeah"):
            with mock.patch("builtins.input", return_value=typed):
                self.assertTrue(setup_mod._confirm("OK?", default=False),
                                f"expected True for {typed!r}")

    def test_non_y_returns_false(self):
        for typed in ("n", "no", "nope", "x"):
            with mock.patch("builtins.input", return_value=typed):
                self.assertFalse(setup_mod._confirm("OK?", default=True),
                                 f"expected False for {typed!r}")

    def test_default_true_shows_capital_Y_first(self):
        with mock.patch("builtins.input", return_value="") as inp:
            setup_mod._confirm("OK?", default=True)
            self.assertIn("[Y/n]", inp.call_args.args[0])

    def test_default_false_shows_capital_N_first(self):
        with mock.patch("builtins.input", return_value="") as inp:
            setup_mod._confirm("OK?", default=False)
            self.assertIn("[y/N]", inp.call_args.args[0])


# ---------------------------------------------------------------------------
# Command — skip flags + needs_* helpers
# ---------------------------------------------------------------------------


class CommandSkipFlagsTest(TestCase):
    def test_all_three_sections_skipped_just_prints_banner(self):
        out = StringIO()
        call_command(
            "setup",
            "--skip-infrastructure", "--skip-branding", "--skip-bootstrap",
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("Site setup wizard", text)
        self.assertIn("Setup complete", text)
        # None of the sub-section headers appear.
        self.assertNotIn("-- Infrastructure", text)
        self.assertNotIn("-- Branding", text)
        self.assertNotIn("-- Bootstrap", text)


class NeedsSuperuserTest(TestCase):
    def test_true_when_no_superusers(self):
        # Confirm clean DB has no superusers.
        self.assertFalse(User.objects.filter(is_superuser=True).exists())
        self.assertTrue(setup_mod.Command._needs_superuser())

    def test_false_when_a_superuser_exists(self):
        User.objects.create_user(
            "admin", "admin@example.com", "pw", is_superuser=True,
        )
        self.assertFalse(setup_mod.Command._needs_superuser())


class NeedsStarterPagesTest(SimpleTestCase):
    """Tests the helper's logic without depending on Wagtail's page-tree
    state in the test DB. The helper just asks HomePage.objects.exists()."""

    def test_true_when_no_homepage_exists(self):
        with mock.patch.object(HomePage.objects, "exists", return_value=False):
            self.assertTrue(setup_mod.Command._needs_starter_pages())

    def test_false_when_homepage_exists(self):
        with mock.patch.object(HomePage.objects, "exists", return_value=True):
            self.assertFalse(setup_mod.Command._needs_starter_pages())

    def test_returns_true_on_import_failure(self):
        """Defensive: if HomePage can't be imported for some reason
        (early-bootstrap state), the wizard defaults to assuming
        starter pages are needed."""
        with mock.patch.object(
            HomePage.objects, "exists", side_effect=Exception("DB not ready"),
        ):
            self.assertTrue(setup_mod.Command._needs_starter_pages())


# ---------------------------------------------------------------------------
# Command._infrastructure
# ---------------------------------------------------------------------------


class InfrastructureSectionTest(TestCase):
    """The infrastructure section drives the .env write end-to-end. We
    override BASE_DIR to a tempdir so each test gets a fresh .env."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.env_path = Path(self.tmp) / ".env"
        # Patch every interactive helper so we don't block on stdin.
        # Default behavior: _prompt returns its default arg unchanged,
        # _confirm returns its default arg unchanged. Individual tests
        # override via side_effect when they need different answers.
        self._prompt_patch = mock.patch(
            "apps.core.management.commands.setup._prompt",
            side_effect=lambda label, default="", **kw: default,
        )
        self._confirm_patch = mock.patch(
            "apps.core.management.commands.setup._confirm",
            side_effect=lambda label, default=True: default,
        )
        self.mock_prompt = self._prompt_patch.start()
        self.mock_confirm = self._confirm_patch.start()
        self.addCleanup(self._prompt_patch.stop)
        self.addCleanup(self._confirm_patch.stop)

    def _run_infra(self, **extra):
        """Run the wizard with --skip-branding and --skip-bootstrap so
        only the infrastructure section fires."""
        with override_settings(BASE_DIR=self.tmp):
            out = StringIO()
            call_command(
                "setup",
                "--skip-branding", "--skip-bootstrap",
                stdout=out, **extra,
            )
            return out.getvalue()

    def test_missing_env_gets_auto_generated_secret_key(self):
        self._run_infra()
        contents = self.env_path.read_text()
        # Real keys are URL-safe base64 ≥ 50 chars; the placeholder
        # would be the example value, which we reject.
        self.assertIn("DJANGO_SECRET_KEY=", contents)
        secret = next(
            line.split("=", 1)[1] for line in contents.splitlines()
            if line.startswith("DJANGO_SECRET_KEY=")
        )
        self.assertGreater(len(secret), 40)
        self.assertNotEqual(secret, "change-me-to-a-real-secret-key")

    def test_placeholder_secret_key_is_regenerated(self):
        # Seed the .env with the placeholder the wizard rejects.
        self.env_path.write_text("DJANGO_SECRET_KEY=change-me-to-a-real-secret-key\n")
        self._run_infra()
        # Should now have a real secret (no longer the placeholder).
        new_secret = next(
            line.split("=", 1)[1] for line in self.env_path.read_text().splitlines()
            if line.startswith("DJANGO_SECRET_KEY=")
        )
        self.assertNotEqual(new_secret, "change-me-to-a-real-secret-key")
        self.assertGreater(len(new_secret), 40)

    def test_existing_real_secret_key_is_preserved_when_not_regenerating(self):
        existing = "a" * 60
        self.env_path.write_text(f"DJANGO_SECRET_KEY={existing}\n")
        # default of regenerate prompt is False → answering with default
        # (which our _confirm stub does) preserves the key.
        self._run_infra()
        secret = next(
            line.split("=", 1)[1] for line in self.env_path.read_text().splitlines()
            if line.startswith("DJANGO_SECRET_KEY=")
        )
        self.assertEqual(secret, existing)

    def test_feature_toggle_defaults_to_true_when_absent(self):
        self._run_infra()
        contents = self.env_path.read_text()
        self.assertIn("FEATURE_COMMERCE=True", contents)
        self.assertIn("FEATURE_COMMUNITY=True", contents)

    def test_feature_toggle_default_picked_up_from_existing_env(self):
        self.env_path.write_text(
            "DJANGO_SECRET_KEY=" + ("a" * 60) + "\n"
            "FEATURE_COMMERCE=False\n"
            "FEATURE_COMMUNITY=False\n"
        )
        self._run_infra()
        contents = self.env_path.read_text()
        self.assertIn("FEATURE_COMMERCE=False", contents)
        self.assertIn("FEATURE_COMMUNITY=False", contents)

    def test_optional_sections_when_confirm_returns_true(self):
        """Pressing Y at each optional-section prompt walks through the
        email/Stripe/Turnstile/S3 sub-sections."""
        # confirm() answers True except for the very last "Write changes
        # to .env?" which we also let default to True.
        self.mock_confirm.side_effect = lambda label, default=True: True
        self._run_infra()
        contents = self.env_path.read_text()
        self.assertIn("EMAIL_HOST=", contents)
        self.assertIn("STRIPE_SECRET_KEY=", contents)
        self.assertIn("TURNSTILE_SITE_KEY=", contents)
        self.assertIn("AWS_STORAGE_BUCKET_NAME=", contents)

    def test_write_skipped_when_final_confirm_is_no(self):
        """A final 'no' on the 'Write changes to .env?' prompt leaves
        the file alone."""
        # Start with a known file we don't want overwritten.
        self.env_path.write_text(
            "DJANGO_SECRET_KEY=" + ("b" * 60) + "\nMARKER=untouched\n"
        )
        # All confirms False — including the write confirm.
        self.mock_confirm.side_effect = lambda label, default=True: False
        text = self._run_infra()
        # File still contains the marker; no .backup created.
        self.assertIn("MARKER=untouched", self.env_path.read_text())
        self.assertFalse(self.env_path.with_suffix(".env.backup").exists())
        self.assertIn("Skipped", text)


# ---------------------------------------------------------------------------
# Command._branding
# ---------------------------------------------------------------------------


class BrandingSectionTest(TestCase):
    """Branding writes to the SiteBranding singleton. Migrations have
    already created the row for us."""

    def setUp(self):
        self._prompt_patch = mock.patch(
            "apps.core.management.commands.setup._prompt",
            side_effect=lambda label, default="", **kw: default,
        )
        self.mock_prompt = self._prompt_patch.start()
        self.addCleanup(self._prompt_patch.stop)

    def _run_branding(self):
        out = StringIO()
        call_command(
            "setup",
            "--skip-infrastructure", "--skip-bootstrap",
            stdout=out,
        )
        return out.getvalue()

    def test_saves_changes_to_sitebranding(self):
        """When _prompt is asked for a value, we return a marker so we
        can assert it lands on the model."""
        def prompt_with_marker(label, default="", **kw):
            if "Site name" in label:
                return "Marker Site"
            if "Tagline" in label:
                return "Marker Tagline"
            return default
        self.mock_prompt.side_effect = prompt_with_marker

        self._run_branding()
        b = SiteBranding.load()
        self.assertEqual(b.site_name, "Marker Site")
        self.assertEqual(b.tagline, "Marker Tagline")

    def test_theme_picker_accepts_valid_theme(self):
        def prompt_pick_midnight(label, default="", **kw):
            if "Active theme" in label:
                return "midnight"
            return default
        self.mock_prompt.side_effect = prompt_pick_midnight
        text = self._run_branding()
        self.assertEqual(SiteBranding.load().active_theme, "midnight")
        # Reset so subsequent tests in this suite see the default.
        b = SiteBranding.load()
        b.active_theme = "default"
        b.save()

    def test_unknown_theme_keeps_current_and_warns(self):
        original_theme = SiteBranding.load().active_theme
        def prompt_pick_invalid(label, default="", **kw):
            if "Active theme" in label:
                return "nonexistent"
            return default
        self.mock_prompt.side_effect = prompt_pick_invalid
        text = self._run_branding()
        self.assertEqual(SiteBranding.load().active_theme, original_theme)
        self.assertIn("not found on disk", text)


# ---------------------------------------------------------------------------
# Command._bootstrap
# ---------------------------------------------------------------------------


class BootstrapSectionTest(TestCase):
    """The bootstrap section dispatches to migrate / createsuperuser /
    seed_data / setup_schedules via call_command. Each is conditional
    on the matching _confirm prompt."""

    def _run_bootstrap(self, confirm_value):
        with mock.patch(
            "apps.core.management.commands.setup._confirm",
            side_effect=lambda label, default=True: confirm_value,
        ), mock.patch(
            "apps.core.management.commands.setup.call_command",
        ) as mock_call:
            out = StringIO()
            call_command(
                "setup",
                "--skip-infrastructure", "--skip-branding",
                stdout=out,
            )
        return mock_call

    def test_all_yes_runs_every_subcommand(self):
        mock_call = self._run_bootstrap(confirm_value=True)
        names = [c.args[0] for c in mock_call.call_args_list]
        self.assertEqual(
            names,
            ["migrate", "createsuperuser", "seed_data", "setup_schedules"],
        )
        # migrate is invoked with interactive=False
        migrate_call = mock_call.call_args_list[0]
        self.assertEqual(migrate_call.kwargs.get("interactive"), False)
        # seed_data is invoked with --pages
        seed_call = mock_call.call_args_list[2]
        self.assertEqual(seed_call.args, ("seed_data", "--pages"))

    def test_all_no_runs_nothing(self):
        mock_call = self._run_bootstrap(confirm_value=False)
        self.assertEqual(mock_call.call_args_list, [])
