from django.apps import AppConfig


class DriveConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "drive"
    verbose_name = "Облачный диск"

    def ready(self) -> None:
        import drive.signals  # noqa: F401
