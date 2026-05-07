"""
Tests for the theming module — discovery, active-theme cache, and the
ActiveThemeLoader's directory resolution. Covers the contract that lets
themes override CSS variables and templates without code changes.
"""

import json
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from apps.core import theming


def _write_theme(root: Path, slug: str, meta: dict) -> Path:
    theme_path = root / slug
    theme_path.mkdir(parents=True)
    (theme_path / "theme.json").write_text(json.dumps(meta))
    return theme_path


class DiscoverThemesTest(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.themes_dir = Path(self.tmp.name)
        self.patcher = mock.patch.object(
            theming, "themes_dir", return_value=self.themes_dir,
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_returns_empty_when_themes_dir_missing(self):
        missing = self.themes_dir / "does-not-exist"
        with mock.patch.object(theming, "themes_dir", return_value=missing):
            self.assertEqual(theming.discover_themes(), {})

    def test_picks_up_themes_with_valid_metadata(self):
        _write_theme(self.themes_dir, "default", {"name": "Default", "version": "1.0"})
        _write_theme(self.themes_dir, "midnight", {"name": "Midnight", "version": "1.0"})
        themes = theming.discover_themes()
        self.assertEqual(set(themes.keys()), {"default", "midnight"})
        self.assertEqual(themes["midnight"]["name"], "Midnight")

    def test_skips_directories_without_theme_json(self):
        (self.themes_dir / "looks-like-theme-but-isnt").mkdir()
        self.assertEqual(theming.discover_themes(), {})

    def test_skips_themes_with_invalid_json(self):
        bad = self.themes_dir / "broken"
        bad.mkdir()
        (bad / "theme.json").write_text("{ not valid json")
        self.assertEqual(theming.discover_themes(), {})

    def test_skips_files_in_themes_dir(self):
        # A README.md or .gitkeep at themes/ root must not become a theme.
        (self.themes_dir / "README.md").write_text("docs")
        self.assertEqual(theming.discover_themes(), {})


class ThemeChoicesTest(SimpleTestCase):
    def test_falls_back_to_default_when_themes_missing(self):
        with mock.patch.object(theming, "discover_themes", return_value={}):
            self.assertEqual(theming.theme_choices(), [("default", "Default")])

    def test_uses_metadata_name_for_label(self):
        with mock.patch.object(theming, "discover_themes", return_value={
            "midnight": {"name": "Midnight"},
            "default": {"name": "Default"},
        }):
            choices = theming.theme_choices()
        self.assertIn(("midnight", "Midnight"), choices)
        self.assertIn(("default", "Default"), choices)

    def test_falls_back_to_slug_when_name_missing(self):
        with mock.patch.object(theming, "discover_themes", return_value={
            "weird": {"version": "1.0"},  # no "name" key
        }):
            self.assertEqual(theming.theme_choices(), [("weird", "weird")])


class ActiveThemeCacheTest(TestCase):
    """SiteBranding-backed: needs a real DB."""

    def setUp(self):
        theming._active_theme_cache.clear()

    def test_default_when_branding_missing_falls_back_safely(self):
        # If the model lookup raises (DB issues, model not yet registered),
        # we must still return *something* sensible.
        with mock.patch(
            "django.apps.apps.get_model",
            side_effect=Exception("simulated DB outage"),
        ):
            self.assertEqual(theming.get_active_theme(), "default")

    def test_returns_value_from_branding_and_caches_it(self):
        from apps.pages.models import SiteBranding
        b = SiteBranding.load()
        b.active_theme = "midnight"
        b.save()
        # Cache miss → DB hit → cached.
        theming._active_theme_cache.clear()
        self.assertEqual(theming.get_active_theme(), "midnight")
        # Subsequent calls should not re-query: simulate by stubbing
        # SiteBranding.load to blow up — if get_active_theme calls it,
        # the test fails.
        with mock.patch.object(SiteBranding, "load",
                               side_effect=AssertionError("must not re-query")):
            self.assertEqual(theming.get_active_theme(), "midnight")

    def test_post_save_signal_invalidates_cache(self):
        """Saving SiteBranding must clear the cache so the next call re-reads."""
        from apps.pages.models import SiteBranding
        theming._active_theme_cache["name"] = "stale"
        b = SiteBranding.load()
        b.active_theme = "default"
        b.save()  # post_save fires invalidate_active_theme_cache
        self.assertNotIn("name", theming._active_theme_cache)


class ActiveThemeLoaderTest(SimpleTestCase):
    def test_get_dirs_points_at_active_theme_templates(self):
        with mock.patch.object(theming, "get_active_theme", return_value="midnight"):
            loader = theming.ActiveThemeLoader(engine=mock.Mock())
            dirs = loader.get_dirs()
        self.assertEqual(len(dirs), 1)
        self.assertTrue(dirs[0].endswith("themes/midnight/templates"))


class TemplateOverrideIntegrationTest(SimpleTestCase):
    """
    End-to-end check: a theme that ships a templates/base.html should win
    over the project's templates/base.html via the ActiveThemeLoader.
    """

    def test_theme_template_overrides_project_template(self):
        from django.template import engines

        with tempfile.TemporaryDirectory() as tmp:
            themes_root = Path(tmp)
            theme = _write_theme(themes_root, "demo", {"name": "Demo"})
            (theme / "templates").mkdir()
            (theme / "templates" / "demo_target.html").write_text(
                "FROM-THEME"
            )
            with mock.patch.object(theming, "themes_dir", return_value=themes_root), \
                 mock.patch.object(theming, "get_active_theme", return_value="demo"):
                # Force a fresh engine so our patched loader takes effect.
                engine = engines["django"]
                template = engine.from_string(
                    '{% include "demo_target.html" %}'
                )
                # The loader chain still runs: ActiveThemeLoader resolves
                # demo_target.html from themes/demo/templates/.
                rendered = template.render({})
        self.assertIn("FROM-THEME", rendered)
