from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete, post_save

from consents.models import Consent
from memory.models import MemoryEntry

from ..models import GraphEdge, GraphNode


class GraphSyncService:
    """Keep the graph representation in sync with domain models."""

    memory_node_type = "memory_entry"
    memory_type_node_type = "memory_entry_type"
    sensitivity_node_type = "sensitivity_level"
    consent_node_type = "consent"
    user_node_type = "user"
    agent_node_type = "agent"

    def __init__(self) -> None:
        self._connected = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def connect(self) -> None:
        if self._connected:
            return
        post_save.connect(
            self._handle_memory_entry_saved,
            sender=MemoryEntry,
            dispatch_uid="graph.sync.memory.save",
        )
        post_delete.connect(
            self._handle_memory_entry_deleted,
            sender=MemoryEntry,
            dispatch_uid="graph.sync.memory.delete",
        )
        post_save.connect(
            self._handle_consent_saved,
            sender=Consent,
            dispatch_uid="graph.sync.consent.save",
        )
        post_delete.connect(
            self._handle_consent_deleted,
            sender=Consent,
            dispatch_uid="graph.sync.consent.delete",
        )
        self._connected = True

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------
    def _handle_memory_entry_saved(self, sender, instance: MemoryEntry, **kwargs: Any) -> None:
        metadata = {
            "title": instance.title,
            "sensitivity": instance.sensitivity,
            "entry_type": instance.entry_type,
        }
        node = self._upsert_node(
            node_type=self.memory_node_type,
            reference_id=str(instance.pk),
            metadata=metadata,
        )
        self._link_memory_entry(node=node, entry=instance)

    def _handle_memory_entry_deleted(self, sender, instance: MemoryEntry, **kwargs: Any) -> None:
        GraphNode.objects.filter(
            node_type=self.memory_node_type,
            reference_id=str(instance.pk),
        ).delete()

    def _handle_consent_saved(self, sender, instance: Consent, **kwargs: Any) -> None:
        metadata = {
            "status": instance.status,
            "scopes": list(instance.scopes or []),
            "sensitivity_levels": list(instance.sensitivity_levels or []),
        }
        consent_node = self._upsert_node(
            node_type=self.consent_node_type,
            reference_id=str(instance.pk),
            metadata=metadata,
        )
        user_node = self._upsert_node(
            node_type=self.user_node_type,
            reference_id=str(instance.user_id),
            metadata={"email": instance.user.email},
        )
        agent_node = self._upsert_node(
            node_type=self.agent_node_type,
            reference_id=instance.agent_identifier,
            metadata={"identifier": instance.agent_identifier},
        )
        self._ensure_edge(user_node, consent_node, "grants", weight=1.0)
        self._ensure_edge(consent_node, user_node, "granted_by", weight=1.0)
        self._ensure_edge(consent_node, agent_node, "granted_to", weight=0.8)
        self._ensure_edge(agent_node, consent_node, "receives", weight=0.8)
        self._link_consent_to_sensitivity(consent_node, instance.sensitivity_levels)

    def _handle_consent_deleted(self, sender, instance: Consent, **kwargs: Any) -> None:
        GraphNode.objects.filter(
            node_type=self.consent_node_type,
            reference_id=str(instance.pk),
        ).delete()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _upsert_node(self, *, node_type: str, reference_id: str, metadata: dict[str, Any]) -> GraphNode:
        with transaction.atomic():
            node, _ = GraphNode.objects.select_for_update().get_or_create(
                node_type=node_type,
                reference_id=reference_id,
                defaults={"metadata": metadata},
            )
            if node.metadata != metadata:
                node.metadata = metadata
                node.save(update_fields=["metadata", "updated_at"])
        return node

    def _ensure_edge(
        self,
        source: GraphNode,
        target: GraphNode,
        relation_type: str,
        *,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> GraphEdge:
        metadata = metadata or {}
        edge, created = GraphEdge.objects.get_or_create(
            source=source,
            target=target,
            relation_type=relation_type,
            defaults={"weight": weight, "metadata": metadata},
        )
        if not created:
            updates = {}
            if edge.weight != weight:
                edge.weight = weight
                updates["weight"] = weight
            if edge.metadata != metadata:
                edge.metadata = metadata
                updates["metadata"] = metadata
            if updates:
                edge.save(update_fields=[*updates.keys(), "updated_at"])
        return edge

    def _link_memory_entry(self, *, node: GraphNode, entry: MemoryEntry) -> None:
        type_node = self._upsert_node(
            node_type=self.memory_type_node_type,
            reference_id=entry.entry_type,
            metadata={"label": entry.entry_type},
        )
        sensitivity_node = self._upsert_node(
            node_type=self.sensitivity_node_type,
            reference_id=entry.sensitivity,
            metadata={"label": entry.sensitivity},
        )
        self._ensure_edge(node, type_node, "has_type", weight=0.9)
        self._ensure_edge(type_node, node, "type_of", weight=0.9)
        self._ensure_edge(node, sensitivity_node, "has_sensitivity", weight=0.7)
        self._ensure_edge(sensitivity_node, node, "sensitivity_of", weight=0.7)

    def _link_consent_to_sensitivity(
        self,
        consent_node: GraphNode,
        sensitivity_levels: Iterable[str] | None,
    ) -> None:
        levels = list(sensitivity_levels or [])
        existing_edges = GraphEdge.objects.filter(
            source=consent_node,
            relation_type="permits_sensitivity",
        )
        existing_targets = {edge.target.reference_id: edge for edge in existing_edges.select_related("target")}
        for level in levels:
            sensitivity_node = self._upsert_node(
                node_type=self.sensitivity_node_type,
                reference_id=level,
                metadata={"label": level},
            )
            self._ensure_edge(consent_node, sensitivity_node, "permits_sensitivity", weight=0.6)
            self._ensure_edge(sensitivity_node, consent_node, "permitted_by", weight=0.6)
            existing_targets.pop(level, None)
        # Remove stale sensitivity edges that are no longer granted
        for stale in existing_targets.values():
            GraphEdge.objects.filter(pk=stale.pk).delete()


graph_sync_service = GraphSyncService()
