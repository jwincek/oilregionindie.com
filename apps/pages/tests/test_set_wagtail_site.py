"""
Tests for apps.pages.management.commands.set_wagtail_site.

The command is invoked by the Ansible add-playbook right after migrate
so first-time deploys land with the correct Wagtail Site hostname
(otherwise the default Wagtail migration leaves it as "localhost":80,
which breaks absolute URLs in feeds, emails, and OG tags).
"""

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from wagtail.models import Site


class SetWagtailSiteCommandTest(TestCase):
    def _default_site(self):
        return Site.objects.filter(is_default_site=True).first()

    def test_explicit_hostname_and_port(self):
        out = StringIO()
        call_command(
            "set_wagtail_site",
            "--hostname", "oilregionindie.com",
            "--port", "443",
            stdout=out,
        )
        site = self._default_site()
        self.assertEqual(site.hostname, "oilregionindie.com")
        self.assertEqual(site.port, 443)
        self.assertIn("→ oilregionindie.com:443", out.getvalue())

    @override_settings(WAGTAILADMIN_BASE_URL="https://oilregionindie.com")
    def test_derives_hostname_and_port_443_from_https_base_url(self):
        call_command("set_wagtail_site", stdout=StringIO())
        site = self._default_site()
        self.assertEqual(site.hostname, "oilregionindie.com")
        self.assertEqual(site.port, 443)

    @override_settings(WAGTAILADMIN_BASE_URL="http://example.com")
    def test_derives_port_80_from_http_base_url(self):
        call_command("set_wagtail_site", stdout=StringIO())
        site = self._default_site()
        self.assertEqual(site.port, 80)

    @override_settings(WAGTAILADMIN_BASE_URL="http://localhost:8000")
    def test_explicit_port_in_base_url_is_used(self):
        call_command("set_wagtail_site", stdout=StringIO())
        site = self._default_site()
        self.assertEqual(site.hostname, "localhost")
        self.assertEqual(site.port, 8000)

    @override_settings(WAGTAILADMIN_BASE_URL="")
    def test_raises_when_no_hostname_and_no_base_url(self):
        with self.assertRaises(CommandError):
            call_command("set_wagtail_site", stdout=StringIO())

    def test_idempotent_when_already_set(self):
        """Re-running the command with the same values prints a 'no
        change' notice rather than a 'changed' message."""
        call_command(
            "set_wagtail_site",
            "--hostname", "stable.example.com", "--port", "443",
            stdout=StringIO(),
        )
        out = StringIO()
        call_command(
            "set_wagtail_site",
            "--hostname", "stable.example.com", "--port", "443",
            stdout=out,
        )
        self.assertIn("no change", out.getvalue())

    def test_raises_when_no_default_site_exists(self):
        Site.objects.filter(is_default_site=True).delete()
        with self.assertRaises(CommandError):
            call_command(
                "set_wagtail_site",
                "--hostname", "x.example.com",
                stdout=StringIO(),
            )
