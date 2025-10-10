from __future__ import annotations

from datetime import datetime

from django.db import models
from django.utils import timezone


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


class MemoryCondensationJobQuerySet(models.QuerySet):
    def pending(self) -> "MemoryCondensationJobQuerySet":
        return self.filter(status=MemoryCondensationJob.STATUS_PENDING)

    def due(self) -> "MemoryCondensationJobQuerySet":
        return self.pending().filter(scheduled_for__lte=timezone.now()).order_by("scheduled_for", "created_at")


class MemoryCondensationJob(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    memory_entry = models.ForeignKey(
        MemoryEntry,
        related_name="condensation_jobs",
        on_delete=models.CASCADE,
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    scheduled_for = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    summary = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MemoryCondensationJobQuerySet.as_manager()

    class Meta:
        ordering = ("scheduled_for", "created_at")
        indexes = [
            models.Index(fields=["status", "scheduled_for"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"CondensationJob<{self.pk}:{self.memory_entry_id}>"

    def start(self) -> None:
        if self.status not in {self.STATUS_PENDING, self.STATUS_FAILED}:
            raise ValueError("Only pending or failed jobs can be started")
        self.status = self.STATUS_PROCESSING
        self.started_at = timezone.now()
        self.attempts += 1
        self.save(update_fields=["status", "started_at", "attempts", "updated_at"])

    def complete(self, summary: str) -> None:
        if self.status != self.STATUS_PROCESSING:
            raise ValueError("Only processing jobs can be completed")
        self.status = self.STATUS_COMPLETED
        self.summary = summary
        self.completed_at = timezone.now()
        self.error_message = ""
        self.save(update_fields=["status", "summary", "completed_at", "error_message", "updated_at"])

    def fail(self, message: str) -> None:
        if self.status != self.STATUS_PROCESSING:
            raise ValueError("Only processing jobs can fail")
        self.status = self.STATUS_FAILED
        self.error_message = message
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "error_message", "completed_at", "updated_at"])

    def reschedule(self, *, when: datetime | None = None) -> None:
        if self.status not in {self.STATUS_FAILED, self.STATUS_PROCESSING}:
            raise ValueError("Only failed or processing jobs may be rescheduled")
        self.status = self.STATUS_PENDING
        self.scheduled_for = when or timezone.now()
        self.started_at = None
        self.completed_at = None
        self.save(update_fields=["status", "scheduled_for", "started_at", "completed_at", "updated_at"])
