from django.db import migrations


def seed_site_branding(apps, schema_editor):
    SiteBranding = apps.get_model("pages", "SiteBranding")
    SiteBranding.objects.update_or_create(
        pk=1,
        defaults={
            "site_name": "Oil Region Creative Hub",
            "tagline": "An open-source hub for independent musicians, visual artists, makers, venues, and fans.",
            "origin_story": (
                "A community platform for independent musicians, visual artists, "
                "makers, venues, and fans. Born from the Oil Region Indie Music Festival."
            ),
            "contact_email": "feedback@oilregionindie.com",
            "source_repo_url": "https://github.com/jwincek/oilregionindie.com",
        },
    )


def unseed_site_branding(apps, schema_editor):
    SiteBranding = apps.get_model("pages", "SiteBranding")
    SiteBranding.objects.filter(pk=1).delete()


class Migration(migrations.Migration):
    dependencies = [("pages", "0002_sitebranding")]
    operations = [migrations.RunPython(seed_site_branding, unseed_site_branding)]
