from django.apps import AppConfig


class WagtailVegaAppConfig(AppConfig):
    name = "wagtail_vega"
    label = "wagtail_vega"
    verbose_name = "Wagtail Vega"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        from . import checks  # noqa: F401  (registers the system checks)
