from __future__ import annotations

from django.db import models


class MemoryEntry(models.Model):
    """Represents an item stored in the long-term memory vault."""

    SENSITIVITY_PUBLIC = "public"
    SENSITIVITY_CONFIDENTIAL = "confidential"
    SENSITIVITY_SECRET = "secret"
    SENSITIVITY_CHOICES = [
        (SENSITIVITY_PUBLIC, "Public"),
        (SENSITIVITY_CONFIDENTIAL, "Confidential"),
        (SENSITIVITY_SECRET, "Secret"),
    ]

    TYPE_FACT = "fact"
    TYPE_EVENT = "event"
    TYPE_NOTE = "note"
    TYPE_CHOICES = [
        (TYPE_FACT, "Fact"),
        (TYPE_EVENT, "Event"),
        (TYPE_NOTE, "Note"),
    ]

    title = models.CharField(max_length=255)
    content = models.TextField()
    sensitivity = models.CharField(
        max_length=32,
        choices=SENSITIVITY_CHOICES,
        default=SENSITIVITY_PUBLIC,
    )
    entry_type = models.CharField(
        max_length=32,
        choices=TYPE_CHOICES,
        default=TYPE_NOTE,
    )
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "title"]
        indexes = [
            models.Index(fields=["sensitivity"]),
            models.Index(fields=["entry_type"]),
        ]

    def __str__(self) -> str:
        return self.title

    def increment_version(self) -> None:
        """Advance the optimistic locking version counter."""

        self.version = models.F("version") + 1
        self.save(update_fields=["version"])
        # Refresh from database to resolve F expression for in-memory instance
        self.refresh_from_db(fields=["version"])
