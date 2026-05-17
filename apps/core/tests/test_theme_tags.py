"""
Tests for apps.core.templatetags.theme_tags.theme_static.

The tag exists so base.html's dynamic theme-CSS path participates in
the ManifestStaticFilesStorage manifest. Under DEBUG (where tests run)
the storage is the plain StaticFilesStorage, so we assert on the
*path-shape*: hash rewriting is verified separately by manual
collectstatic against prod-like settings.
"""

from unittest import mock

from django.test import SimpleTestCase

from apps.core.templatetags.theme_tags import theme_static


class ThemeStaticTagTest(SimpleTestCase):
    def test_returns_path_to_active_theme_css(self):
        url = theme_static("midnight")
        self.assertIn("themes/midnight/theme.css", url)
        # Path is prefixed with the configured STATIC_URL ("/static/").
        self.assertTrue(url.startswith("/static/"))

    def test_falls_back_to_default_when_active_theme_is_blank(self):
        self.assertIn("themes/default/theme.css", theme_static(""))

    def test_falls_back_to_default_when_active_theme_is_none(self):
        self.assertIn("themes/default/theme.css", theme_static(None))

    def test_unmanifested_path_falls_back_to_plain_url(self):
        """If ManifestStaticFilesStorage's manifest is missing the entry
        (e.g., a newly added theme without collectstatic having run),
        we want the page to still render rather than 500."""
        with mock.patch(
            "apps.core.templatetags.theme_tags.staticfiles_storage.url",
            side_effect=ValueError("Missing staticfiles manifest entry"),
        ):
            url = theme_static("brand-new")
            self.assertEqual(url, "/static/themes/brand-new/theme.css")
