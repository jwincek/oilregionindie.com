from django.apps import AppConfig


class PagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pages"
    verbose_name = "Pages"

    def ready(self):
        # Invalidate the active-theme cache whenever SiteBranding is saved
        # so a theme switch from /cms/ takes effect on the next request.
        from django.db.models.signals import post_save
        from apps.core.theming import invalidate_active_theme_cache
        from apps.pages.models import SiteBranding

        post_save.connect(
            invalidate_active_theme_cache,
            sender=SiteBranding,
            dispatch_uid="apps.pages.invalidate_active_theme_cache",
        )
