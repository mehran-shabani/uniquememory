from django.apps import AppConfig


class MemoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "memory"

    def ready(self) -> None:  # pragma: no cover - import side effects
        from . import signals
