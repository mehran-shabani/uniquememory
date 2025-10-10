from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Stores an immutable trail of write operations performed in the system."""

    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=12, choices=ACTION_CHOICES)
    app_label = models.CharField(max_length=128)
    model_name = models.CharField(max_length=128)
    object_id = models.CharField(max_length=255)
    snapshot = models.JSONField(blank=True, null=True, help_text="Serialized representation of the object state.")
    changes = models.JSONField(blank=True, null=True, help_text="Key/value changes captured during the operation.")
    metadata = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["app_label", "model_name"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} {self.model_name}#{self.object_id}"
