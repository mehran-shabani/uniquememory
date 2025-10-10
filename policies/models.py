from __future__ import annotations

from django.conf import settings
from django.db import models


class AccessPolicy(models.Model):
    """Defines which actors can interact with a memory entry."""

    ACCESS_READ = "read"
    ACCESS_WRITE = "write"
    ACCESS_ADMIN = "admin"
    ACCESS_LEVEL_CHOICES = [
        (ACCESS_READ, "Read"),
        (ACCESS_WRITE, "Write"),
        (ACCESS_ADMIN, "Admin"),
    ]

    memory_entry = models.ForeignKey(
        "memory.MemoryEntry",
        on_delete=models.CASCADE,
        related_name="access_policies",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    access_level = models.CharField(max_length=16, choices=ACCESS_LEVEL_CHOICES, default=ACCESS_READ)
    allowed_roles = models.JSONField(
        default=list,
        blank=True,
        help_text="List of roles allowed to use this entry.",
    )
    allowed_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="memory_access_policies",
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Access policies"

    def __str__(self) -> str:
        return f"{self.name} ({self.access_level})"
