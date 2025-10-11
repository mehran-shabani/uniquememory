from __future__ import annotations

import secrets
from collections.abc import Iterable

from django.db import connection, models
from django.utils import timezone


class WebhookSubscriptionQuerySet(models.QuerySet):
    def active(self) -> "WebhookSubscriptionQuerySet":
        return self.filter(status=WebhookSubscription.STATUS_ACTIVE)

    def for_event(self, event_name: str) -> "WebhookSubscriptionQuerySet":
        if connection.vendor == "sqlite":
            matching_ids = [
                pk
                for pk, events in self.values_list("pk", "events")
                if event_name in (events or [])
            ]
            return self.filter(pk__in=matching_ids)
        return self.filter(events__contains=[event_name])


class WebhookSubscription(models.Model):
    """Represents a company's HTTP webhook subscription."""

    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_ERROR = "error"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_ERROR, "Error"),
    ]

    FAILURE_THRESHOLD = 3

    company = models.ForeignKey(
        "companies.Company",
        related_name="webhook_subscriptions",
        on_delete=models.CASCADE,
    )
    target_url = models.URLField(max_length=500)
    secret = models.CharField(max_length=128, default=secrets.token_hex)
    events = models.JSONField(default=list, help_text="List of event names that trigger the webhook.")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    failure_count = models.PositiveIntegerField(default=0)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = WebhookSubscriptionQuerySet.as_manager()

    class Meta:
        ordering = ("company", "created_at")
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["company", "status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - human friendly output
        return f"Webhook<{self.company_id}:{self.target_url}>"

    def activate(self) -> None:
        self.status = self.STATUS_ACTIVE
        self.failure_count = 0
        self.last_error = ""
        self.save(update_fields=["status", "failure_count", "last_error", "updated_at"])

    def pause(self) -> None:
        self.status = self.STATUS_PAUSED
        self.save(update_fields=["status", "updated_at"])

    def mark_success(self) -> None:
        self.failure_count = 0
        self.status = self.STATUS_ACTIVE
        self.last_success_at = timezone.now()
        self.last_error = ""
        self.save(update_fields=["failure_count", "status", "last_success_at", "last_error", "updated_at"])

    def mark_failure(self, message: str) -> None:
        self.failure_count += 1
        self.last_failure_at = timezone.now()
        self.last_error = message
        if self.failure_count >= self.FAILURE_THRESHOLD:
            self.status = self.STATUS_ERROR
        self.save(
            update_fields=[
                "failure_count",
                "last_failure_at",
                "last_error",
                "status",
                "updated_at",
            ]
        )

    def allows_event(self, event_name: str) -> bool:
        return event_name in set(self.events or [])

    def set_events(self, event_names: Iterable[str]) -> None:
        self.events = sorted(set(event_names))
        self.save(update_fields=["events", "updated_at"])
