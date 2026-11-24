from django.apps import AppConfig


class SharesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shares"
    verbose_name = "Шеринг файлов и кода"

    def ready(self) -> None:
        import shares.signals  # noqa: F401
