from __future__ import annotations

from django.db import models


class Embedding(models.Model):
    """Stores vector representations for :class:`memory.MemoryEntry`."""

    memory_entry = models.OneToOneField(
        "memory.MemoryEntry",
        on_delete=models.CASCADE,
        related_name="embedding",
    )
    vector = models.JSONField(help_text="Dense vector representing the entry content.")
    model_name = models.CharField(max_length=255)
    dimension = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["model_name"]),
        ]
        verbose_name = "Embedding"
        verbose_name_plural = "Embeddings"

    def __str__(self) -> str:  # pragma: no cover - representation only
        return f"Embedding<{self.memory_entry_id}>"

    def as_vector(self) -> list[float]:
        """Return the stored vector as a list of floats."""

        data = self.vector or []
        return [float(value) for value in data]
