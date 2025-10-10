from __future__ import annotations

from typing import Iterable

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from memory.models import MemoryEntry
SCOPE_MEMORY_READ = "memory.read"
SCOPE_MEMORY_WRITE = "memory.write"
SCOPE_MEMORY_SEARCH = "memory.search"

SCOPE_CHOICES = [
    (SCOPE_MEMORY_READ, "Memory read"),
    (SCOPE_MEMORY_WRITE, "Memory write"),
    (SCOPE_MEMORY_SEARCH, "Memory search"),
]


class ConsentQuerySet(models.QuerySet):
    def active(self) -> "ConsentQuerySet":
        return self.filter(status=Consent.STATUS_ACTIVE)

    def for_subject(self, user: settings.AUTH_USER_MODEL) -> "ConsentQuerySet":
        return self.filter(user=user)

    def for_agent(self, agent_identifier: str) -> "ConsentQuerySet":
        return self.filter(agent_identifier=agent_identifier)


class Consent(models.Model):
    """Represents a grant of access from a user to an external agent."""

    STATUS_PENDING = "pending"
    STATUS_ACTIVE = "active"
    STATUS_REVOKED = "revoked"
    STATUS_EXPIRED = "expired"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_REVOKED, "Revoked"),
        (STATUS_EXPIRED, "Expired"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consents",
    )
    agent_identifier = models.CharField(
        max_length=255,
        help_text="Stable identifier of the agent or client receiving access.",
    )
    scopes = models.JSONField(
        default=list,
        blank=True,
        help_text="Granted scopes such as memory.read or memory.write.",
    )
    sensitivity_levels = models.JSONField(
        default=list,
        help_text="List of sensitivity levels that the agent is allowed to access.",
    )
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    issued_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = ConsentQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at", "-issued_at"]
        unique_together = ["user", "agent_identifier", "version"]
        indexes = [
            models.Index(fields=["user", "agent_identifier", "status"]),
        ]

    def __str__(self) -> str:
        return f"Consent v{self.version} for {self.agent_identifier}"

    def clean(self) -> None:
        super().clean()
        allowed_sensitivities = {choice for choice, _ in MemoryEntry.SENSITIVITY_CHOICES}
        if not self.sensitivity_levels:
            raise ValidationError({"sensitivity_levels": "At least one sensitivity level must be selected."})
        invalid = set(self.sensitivity_levels) - allowed_sensitivities
        if invalid:
            raise ValidationError({"sensitivity_levels": f"Invalid sensitivities: {', '.join(sorted(invalid))}."})
        if not self.scopes:
            raise ValidationError({"scopes": "At least one scope must be granted."})
        allowed_scopes = {choice for choice, _ in SCOPE_CHOICES}
        invalid_scopes = set(self.scopes) - allowed_scopes
        if invalid_scopes:
            raise ValidationError({"scopes": f"Invalid scopes: {', '.join(sorted(invalid_scopes))}."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def activate(self) -> None:
        self.status = self.STATUS_ACTIVE
        self.revoked_at = None
        self.save(update_fields=["status", "revoked_at", "updated_at"])

    def revoke(self) -> None:
        if self.status == self.STATUS_REVOKED:
            return
        self.status = self.STATUS_REVOKED
        self.revoked_at = timezone.now()
        self.save(update_fields=["status", "revoked_at", "updated_at"])
        from . import signals

        signals.consent_revoked.send(sender=self.__class__, consent=self)

    def allows_scope(self, scope: str) -> bool:
        return scope in set(self.scopes)

    def allows_all_scopes(self, scopes: Iterable[str]) -> bool:
        granted = set(self.scopes)
        return all(scope in granted for scope in scopes)

    def allows_sensitivity(self, sensitivity: str) -> bool:
        return sensitivity in set(self.sensitivity_levels)

    @property
    def is_active(self) -> bool:
        return self.status == self.STATUS_ACTIVE
