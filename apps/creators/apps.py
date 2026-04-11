from django.apps import AppConfig


class CreatorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.creators"
    verbose_name = "Creators"

    def ready(self):
        import apps.creators.signals  # noqa: F401
