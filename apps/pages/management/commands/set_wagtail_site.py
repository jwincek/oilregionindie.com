"""
Configure the default Wagtail Site row's hostname and port.

Wagtail's initial migration creates a Site with hostname="localhost",
which is fine for development but causes problems on a fresh
production deploy — page absolute URLs (RSS feeds, email links) point
at localhost until someone updates the row by hand.

This command is intended to be called by the Ansible add-playbook
right after `migrate` so first-time deployments land with the correct
hostname.

Usage:
    python manage.py set_wagtail_site --hostname oilregionindie.com --port 443
    python manage.py set_wagtail_site --hostname localhost --port 8000

If --hostname is omitted, the command tries WAGTAILADMIN_BASE_URL from
settings to derive a hostname and port.
"""

from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Set the default Wagtail Site row's hostname and port."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hostname",
            type=str,
            default=None,
            help="Hostname to set (e.g., oilregionindie.com). "
                 "Defaults to the host parsed from WAGTAILADMIN_BASE_URL.",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=None,
            help="Port to set (default: 443 if https, 80 if http, "
                 "or 8000 if WAGTAILADMIN_BASE_URL is localhost).",
        )

    def handle(self, *args, **opts):
        from wagtail.models import Site

        hostname = opts["hostname"]
        port = opts["port"]

        if not hostname:
            base_url = getattr(settings, "WAGTAILADMIN_BASE_URL", "")
            if not base_url:
                raise CommandError(
                    "No --hostname given and WAGTAILADMIN_BASE_URL is "
                    "unset. Pass --hostname explicitly."
                )
            parsed = urlparse(base_url)
            hostname = parsed.hostname or "localhost"
            if port is None:
                if parsed.port:
                    port = parsed.port
                elif parsed.scheme == "https":
                    port = 443
                else:
                    port = 80

        if port is None:
            port = 443

        site = Site.objects.filter(is_default_site=True).first()
        if not site:
            raise CommandError(
                "No default Wagtail Site row found. Run `migrate` first."
            )

        old = (site.hostname, site.port)
        if old == (hostname, port):
            self.stdout.write(self.style.NOTICE(
                f"Wagtail Site already set to {hostname}:{port} — no change."
            ))
            return

        site.hostname = hostname
        site.port = port
        site.save(update_fields=["hostname", "port"])
        self.stdout.write(self.style.SUCCESS(
            f"Wagtail Site updated: {old[0]}:{old[1]} → {hostname}:{port}"
        ))
