"""
Tests for apps.creators.management.commands.refresh_embeds.

Mocks the apps.creators.embeds.refresh_embed helper so we don't make
real HTTP calls to oEmbed providers.
"""

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.creators.models import MediaItem
from apps.creators.tests.helpers import make_creator, make_user


def _make_media(creator, **kwargs):
    defaults = {
        "creator": creator,
        "title": "An embed",
        "media_type": "video",
        "embed_url": "https://example.com/video",
        "embed_html": "",
    }
    defaults.update(kwargs)
    return MediaItem.objects.create(**defaults)


class RefreshEmbedsCommandTest(TestCase):
    def setUp(self):
        self.creator = make_creator(user=make_user())

    def test_no_items_returns_clean_message(self):
        out = StringIO()
        call_command("refresh_embeds", stdout=out)
        self.assertIn("No media items to process", out.getvalue())

    @mock.patch("apps.creators.management.commands.refresh_embeds.refresh_embed")
    def test_default_only_processes_items_missing_embed_html(self, mock_refresh):
        """Without --all, only the items with empty embed_html are
        passed to refresh_embed. Already-cached items are skipped."""
        mock_refresh.return_value = True
        uncached = _make_media(self.creator, title="Uncached")
        cached = _make_media(self.creator, title="Cached",
                             embed_html="<iframe>...</iframe>")
        # Item with no embed_url at all → excluded from the queryset.
        _make_media(self.creator, title="No URL", embed_url="")

        out = StringIO()
        call_command("refresh_embeds", stdout=out)

        # refresh_embed called once, for the uncached item only.
        self.assertEqual(mock_refresh.call_count, 1)
        called_with = mock_refresh.call_args.args[0]
        self.assertEqual(called_with, uncached)
        self.assertIn("Processing 1 media items", out.getvalue())
        self.assertIn("1 fetched, 0 failed", out.getvalue())

    @mock.patch("apps.creators.management.commands.refresh_embeds.refresh_embed")
    def test_all_flag_processes_every_item_with_embed_url(self, mock_refresh):
        """With --all, items that already have embed_html are also
        re-fetched."""
        mock_refresh.return_value = True
        a = _make_media(self.creator, title="A")
        b = _make_media(self.creator, title="B",
                        embed_html="<iframe>existing</iframe>")
        _make_media(self.creator, title="No URL", embed_url="")

        out = StringIO()
        call_command("refresh_embeds", "--all", stdout=out)

        self.assertEqual(mock_refresh.call_count, 2)
        self.assertIn("2 fetched, 0 failed", out.getvalue())

    @mock.patch("apps.creators.management.commands.refresh_embeds.refresh_embed")
    def test_reports_fetch_failures_separately(self, mock_refresh):
        """refresh_embed returns True/False per item; we tally both."""
        # First call succeeds, second fails.
        mock_refresh.side_effect = [True, False]
        _make_media(self.creator, title="OK")
        _make_media(self.creator, title="Bad")
        out = StringIO()
        call_command("refresh_embeds", stdout=out)
        self.assertIn("1 fetched, 1 failed", out.getvalue())
        self.assertIn("Fetched", out.getvalue())
        self.assertIn("Failed", out.getvalue())
