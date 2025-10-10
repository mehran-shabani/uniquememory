from __future__ import annotations

from django.db import models


class GraphNode(models.Model):
    """Represents an entity inside the knowledge graph."""

    node_type = models.CharField(max_length=64)
    reference_id = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("node_type", "reference_id")
    def __str__(self) -> str:
        return f"{self.node_type}:{self.reference_id}"


class GraphEdge(models.Model):
    """Connects two nodes and stores additional metadata about the relation."""

    source = models.ForeignKey(
        GraphNode,
        related_name="outgoing_edges",
        on_delete=models.CASCADE,
    )
    target = models.ForeignKey(
        GraphNode,
        related_name="incoming_edges",
        on_delete=models.CASCADE,
    )
    relation_type = models.CharField(max_length=64)
    weight = models.FloatField(default=1.0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("source", "target", "relation_type")
        indexes = [
            models.Index(fields=["source", "relation_type"]),
            models.Index(fields=["target", "relation_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.source} -[{self.relation_type}]-> {self.target}"
