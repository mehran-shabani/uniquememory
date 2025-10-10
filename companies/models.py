from __future__ import annotations

import secrets
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def generate_api_key() -> str:
    return secrets.token_hex(32)


class Company(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:  # pragma: no cover - human readable output
        return self.name


class ApiKey(models.Model):
    company = models.ForeignKey(Company, related_name="api_keys", on_delete=models.CASCADE)
    key = models.CharField(max_length=128, unique=True, default=generate_api_key, editable=False)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    rate_limit = models.PositiveIntegerField(default=1000, help_text="Requests allowed per window")
    rate_limit_window = models.PositiveIntegerField(
        default=60,
        help_text="Window size in seconds for rate limiting",
    )
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("company", "name")
        verbose_name = "API key"
        verbose_name_plural = "API keys"

    def __str__(self) -> str:  # pragma: no cover - human readable output
        return f"{self.company.name} ({self.name})"

    def touch(self, *, commit: bool = True) -> None:
        self.last_used_at = timezone.now()
        if commit:
            self.save(update_fields=["last_used_at"])

    def reset_credentials(self) -> None:
        self.key = generate_api_key()
        self.save(update_fields=["key"])

    def clean(self) -> None:
        if self.rate_limit == 0:
            raise ValidationError("Rate limit must be greater than zero")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)
