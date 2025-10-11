from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from django.db import IntegrityError, transaction
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
            weak=False,
        )
        post_delete.connect(
            self._handle_memory_entry_deleted,
            sender=MemoryEntry,
            dispatch_uid="graph.sync.memory.delete",
            weak=False,
        )
        post_save.connect(
            self._handle_consent_saved,
            sender=Consent,
            dispatch_uid="graph.sync.consent.save",
            weak=False,
        )
        post_delete.connect(
            self._handle_consent_deleted,
            sender=Consent,
            dispatch_uid="graph.sync.consent.delete",
            weak=False,
        )
        self._connected = True
    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------
    def _handle_memory_entry_saved(self, sender, instance: MemoryEntry, **_kwargs: Any) -> None:
        def sync() -> None:
            metadata = {
                "sensitivity": instance.sensitivity,
                "entry_type": instance.entry_type,
            }
            node = self._upsert_node(
                node_type=self.memory_node_type,
                reference_id=str(instance.pk),
                metadata=metadata,
            )
            self._link_memory_entry(node=node, entry=instance)

        self._on_commit(sync)

    def _handle_memory_entry_deleted(self, sender, instance: MemoryEntry, **_kwargs: Any) -> None:
        def sync() -> None:
            GraphNode.objects.filter(
                node_type=self.memory_node_type,
                reference_id=str(instance.pk),
            ).delete()

        self._on_commit(sync)

    def _handle_consent_saved(self, sender, instance: Consent, **_kwargs: Any) -> None:
        def sync() -> None:
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

            if instance.is_active:
                self._ensure_edge(user_node, consent_node, "grants", weight=1.0)
                self._ensure_edge(consent_node, user_node, "granted_by", weight=1.0)
                self._ensure_edge(consent_node, agent_node, "granted_to", weight=0.8)
                self._ensure_edge(agent_node, consent_node, "receives", weight=0.8)
                self._link_consent_to_sensitivity(consent_node, instance.sensitivity_levels)
            else:
                self._clear_consent_edges(consent_node, user_node, agent_node)

        self._on_commit(sync)

    def _handle_consent_deleted(self, sender, instance: Consent, **_kwargs: Any) -> None:
        def sync() -> None:
            GraphNode.objects.filter(
                node_type=self.consent_node_type,
                reference_id=str(instance.pk),
            ).delete()

        self._on_commit(sync)

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
        try:
            edge, created = GraphEdge.objects.get_or_create(
                source=source,
                target=target,
                relation_type=relation_type,
                defaults={"weight": weight, "metadata": metadata},
            )
        except IntegrityError:
            edge = GraphEdge.objects.get(
                source=source, target=target, relation_type=relation_type
            )
            created = False
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
        existing_permits = GraphEdge.objects.filter(
            source=consent_node,
            relation_type="permits_sensitivity",
        ).select_related("target")
        existing_permits_by_level = {
            edge.target.reference_id: edge for edge in existing_permits
        }
        existing_permitted_by = GraphEdge.objects.filter(
            target=consent_node,
            relation_type="permitted_by",
        ).select_related("source")
        existing_permitted_by_by_level = {
            edge.source.reference_id: edge for edge in existing_permitted_by
        }
        for level in levels:
            sensitivity_node = self._upsert_node(
                node_type=self.sensitivity_node_type,
                reference_id=level,
                metadata={"label": level},
            )
            self._ensure_edge(consent_node, sensitivity_node, "permits_sensitivity", weight=0.6)
            self._ensure_edge(sensitivity_node, consent_node, "permitted_by", weight=0.6)
            existing_permits_by_level.pop(level, None)
            existing_permitted_by_by_level.pop(level, None)
        # Remove stale sensitivity edges that are no longer granted
        if existing_permits_by_level:
            stale_target_ids = {edge.target_id for edge in existing_permits_by_level.values()}
            GraphEdge.objects.filter(
                source=consent_node,
                relation_type="permits_sensitivity",
                target_id__in=stale_target_ids,
            ).delete()
        if existing_permitted_by_by_level:
            stale_source_ids = {edge.source_id for edge in existing_permitted_by_by_level.values()}
            GraphEdge.objects.filter(
                source_id__in=stale_source_ids,
                target=consent_node,
                relation_type="permitted_by",
            ).delete()

    def _clear_consent_edges(
        self,
        consent_node: GraphNode,
        user_node: GraphNode,
        agent_node: GraphNode,
    ) -> None:
        GraphEdge.objects.filter(
            source=user_node, target=consent_node, relation_type="grants"
        ).delete()
        GraphEdge.objects.filter(
            source=consent_node, target=user_node, relation_type="granted_by"
        ).delete()
        GraphEdge.objects.filter(
            source=consent_node, target=agent_node, relation_type="granted_to"
        ).delete()
        GraphEdge.objects.filter(
            source=agent_node, target=consent_node, relation_type="receives"
        ).delete()
        GraphEdge.objects.filter(
            source=consent_node, relation_type="permits_sensitivity"
        ).delete()
        GraphEdge.objects.filter(
            target=consent_node, relation_type="permitted_by"
        ).delete()

    def _on_commit(self, func: Callable[[], None]) -> None:
        connection = transaction.get_connection()
        if connection.in_atomic_block:
            func()
        else:
            transaction.on_commit(func)


graph_sync_service = GraphSyncService()
