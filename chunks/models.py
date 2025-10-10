from __future__ import annotations

from django.db import models


class EntryChunk(models.Model):
    """Represents a chunk of information derived from a memory entry."""

    memory_entry = models.ForeignKey(
        "memory.MemoryEntry",
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    position = models.PositiveIntegerField(help_text="Ordering of the chunk inside the entry.")
    content = models.TextField()
    embedding = models.JSONField(blank=True, null=True, help_text="Vector representation of the chunk.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["memory_entry", "position"]
        unique_together = ("memory_entry", "position")

    def __str__(self) -> str:
        return f"Chunk {self.position} of {self.memory_entry_id}"
