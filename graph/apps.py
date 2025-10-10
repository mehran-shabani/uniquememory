from __future__ import annotations

from django.apps import AppConfig


class GraphConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "graph"

    def ready(self) -> None:  # pragma: no cover - side-effect wiring
        from .services.sync import graph_sync_service

        graph_sync_service.connect()
