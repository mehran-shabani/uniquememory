from django.apps import AppConfig


class WebhooksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "webhooks"

    def ready(self) -> None:  # pragma: no cover - import side effects
        from . import signal_handlers
