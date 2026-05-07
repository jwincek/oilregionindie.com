"""
Tests for the EnvFile helper used by `manage.py setup`.

Covers: round-trip preservation of comments and key order, get/set semantics,
quoting of values that contain whitespace, and overwrite-with-backup on write.
"""

import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.core.management.commands.setup import EnvFile


SAMPLE = """\
# Django
DJANGO_SECRET_KEY=abc123
DJANGO_DEBUG=True

# Database (commented out — falls back to sqlite in settings.py)
# DATABASE_URL=postgres://user:pass@host/db

# Plain value
SITE_NAME=Oil Region

# Quoted value
TAGLINE="An open-source hub"

# Empty value
REDIS_URL=
"""


class EnvFileTest(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".env", delete=False
        )
        self.tmp.write(SAMPLE)
        self.tmp.close()
        self.path = Path(self.tmp.name)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        self.path.unlink(missing_ok=True)
        self.path.with_suffix(self.path.suffix + ".backup").unlink(missing_ok=True)

    def test_get_returns_existing_value(self):
        env = EnvFile(self.path)
        self.assertEqual(env.get("DJANGO_SECRET_KEY"), "abc123")
        self.assertEqual(env.get("SITE_NAME"), "Oil Region")

    def test_get_strips_quotes_from_quoted_values(self):
        env = EnvFile(self.path)
        self.assertEqual(env.get("TAGLINE"), "An open-source hub")

    def test_get_returns_empty_string_for_blank_value(self):
        env = EnvFile(self.path)
        self.assertEqual(env.get("REDIS_URL"), "")

    def test_get_returns_default_for_missing_key(self):
        env = EnvFile(self.path)
        self.assertEqual(env.get("NOT_THERE", "fallback"), "fallback")

    def test_get_ignores_commented_lines(self):
        """A `# DATABASE_URL=...` line must not register DATABASE_URL as set."""
        env = EnvFile(self.path)
        self.assertEqual(env.get("DATABASE_URL", "default"), "default")

    def test_set_replaces_existing_key_in_place(self):
        env = EnvFile(self.path)
        env.set("DJANGO_DEBUG", "False")
        env.write()
        text = self.path.read_text()
        self.assertEqual(text.count("DJANGO_DEBUG="), 1)
        self.assertIn("DJANGO_DEBUG=False", text)

    def test_set_appends_new_key_at_end(self):
        env = EnvFile(self.path)
        env.set("BRAND_NEW", "value")
        env.write()
        lines = self.path.read_text().splitlines()
        self.assertEqual(lines[-1], "BRAND_NEW=value")

    def test_set_quotes_values_with_spaces(self):
        env = EnvFile(self.path)
        env.set("ADMIN", "Jerome:jerome@example.com,Other:o@example.com")
        env.set("WITH_SPACE", "hello world")
        env.write()
        text = self.path.read_text()
        self.assertIn('WITH_SPACE="hello world"', text)
        self.assertIn(  # commas alone don't trigger quoting
            "ADMIN=Jerome:jerome@example.com,Other:o@example.com", text
        )

    def test_write_preserves_comments_and_blank_lines(self):
        env = EnvFile(self.path)
        env.set("DJANGO_DEBUG", "False")  # one in-place edit
        env.write()
        out = self.path.read_text()
        # All four section comments survive.
        for comment in (
            "# Django",
            "# Database (commented out",
            "# Plain value",
            "# Quoted value",
            "# Empty value",
        ):
            self.assertIn(comment, out)
        # Comment-line keys remain commented out (not promoted to real keys).
        self.assertIn("# DATABASE_URL=", out)
        self.assertNotIn("\nDATABASE_URL=", out)

    def test_write_creates_backup_of_prior_file(self):
        env = EnvFile(self.path)
        env.set("DJANGO_DEBUG", "False")
        env.write()
        backup = self.path.with_suffix(self.path.suffix + ".backup")
        self.assertTrue(backup.exists())
        # Backup mirrors pre-write content.
        self.assertEqual(backup.read_text(), SAMPLE)

    def test_round_trip_preserves_key_order_for_unchanged_file(self):
        env = EnvFile(self.path)
        env.write()  # no edits
        original_keys = [
            line.split("=", 1)[0]
            for line in SAMPLE.splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        ]
        new_keys = [
            line.split("=", 1)[0]
            for line in self.path.read_text().splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        ]
        self.assertEqual(new_keys, original_keys)

    def test_new_file_creates_from_scratch(self):
        """An EnvFile pointed at a missing path can be populated and written."""
        target = self.path.parent / "fresh.env"
        target.unlink(missing_ok=True)
        self.addCleanup(target.unlink, missing_ok=True)
        env = EnvFile(target)
        env.set("DJANGO_SECRET_KEY", "xyz")
        env.write()
        self.assertEqual(target.read_text(), "DJANGO_SECRET_KEY=xyz\n")
