from __future__ import annotations

from collections.abc import Iterable
from typing import Dict, List

from django.core.exceptions import PermissionDenied
from django.db import transaction

from consents.models import SCOPE_MEMORY_READ, SCOPE_MEMORY_SEARCH, SCOPE_MEMORY_WRITE
from memory.models import MemoryEntry
from memory.services.query import HybridQueryService, HybridSearchResult

from ..auth import BearerTokenValidator

validator = BearerTokenValidator()
query_service = HybridQueryService()


def _serialize_entry(entry: MemoryEntry) -> Dict[str, object]:
    return {
        "id": entry.pk,
        "title": entry.title,
        "content": entry.content,
        "sensitivity": entry.sensitivity,
        "entry_type": entry.entry_type,
        "version": entry.version,
        "updated_at": entry.updated_at.isoformat(),
    }


def memory_search(*, bearer_token: str, payload: Dict[str, object]) -> Dict[str, object]:
    query = payload.get("query") or payload.get("q")
    if not isinstance(query, str) or not query.strip():
        raise PermissionDenied("Search query is required.")

    limit = payload.get("limit") or payload.get("k") or 10
    if not isinstance(limit, int) or limit <= 0:
        raise PermissionDenied("Limit must be a positive integer.")

    context = validator.parse(
        bearer_token,
        required_scopes=[SCOPE_MEMORY_SEARCH],
    )

    user_id_from_payload = payload.get("user_id")
    if user_id_from_payload and str(user_id_from_payload) != str(context.subject.pk):
        raise PermissionDenied("Searching on behalf of another user is not permitted.")

    raw_results = query_service.search(
        user_id=str(context.subject.pk),
        query=query,
        limit=limit,
    )

    allowed: List[HybridSearchResult] = [
        result
        for result in raw_results
        if context.consent and context.consent.allows_sensitivity(result.sensitivity)
    ]
    allowed = allowed[:limit]

    if allowed:
        validator.ensure_permissions(
            context,
            action="memory:query",
            sensitivities=[result.sensitivity for result in allowed],
        )

    return {
        "user_id": str(context.subject.pk),
        "count": len(allowed),
        "results": [result.to_dict() for result in allowed],
    }


def memory_get(*, bearer_token: str, payload: Dict[str, object]) -> Dict[str, object]:
    entry_id = payload.get("entry_id") or payload.get("id")
    if not isinstance(entry_id, int):
        raise PermissionDenied("entry_id must be provided as an integer.")

    try:
        entry = MemoryEntry.objects.get(pk=entry_id)
    except MemoryEntry.DoesNotExist as exc:
        raise PermissionDenied("Memory entry not found.") from exc

    validator.validate(
        bearer_token,
        action="memory:retrieve",
        required_scopes=[SCOPE_MEMORY_READ],
        sensitivity=entry.sensitivity,
    )

    return {"entry": _serialize_entry(entry)}

def memory_upsert(*, bearer_token: str, payload: Dict[str, object]) -> Dict[str, object]:
    entry_payload_obj = payload.get("entry") if isinstance(payload, dict) else None
    if entry_payload_obj is None:
        entry_payload_obj = payload
    if not isinstance(entry_payload_obj, dict):
        raise PermissionDenied("entry payload must be provided as an object.")

    entry_payload: Dict[str, object] = entry_payload_obj
    entry_id = entry_payload.get("entry_id") or entry_payload.get("id")

    requested_sensitivity = entry_payload.get("sensitivity")
    if requested_sensitivity is not None and not isinstance(requested_sensitivity, str):
        raise PermissionDenied("sensitivity must be a string.")

    validated_sensitivity: str | None = None
    if requested_sensitivity is not None:
        allowed_sensitivities = {choice for choice, _ in MemoryEntry.SENSITIVITY_CHOICES}
        if requested_sensitivity not in allowed_sensitivities:
            raise PermissionDenied("sensitivity is invalid.")
        validated_sensitivity = requested_sensitivity

    entry_type = entry_payload.get("entry_type")
    if entry_type is not None and not isinstance(entry_type, str):
        raise PermissionDenied("entry_type must be a string.")

    validated_entry_type: str | None = None
    if entry_type is not None:
        allowed_entry_types = {choice for choice, _ in MemoryEntry.TYPE_CHOICES}
        if entry_type not in allowed_entry_types:
            raise PermissionDenied("entry_type is invalid.")
        validated_entry_type = entry_type

    context = validator.parse(
        bearer_token,
        required_scopes=[SCOPE_MEMORY_WRITE],
    )

    if entry_id is None:
        sensitivity = validated_sensitivity or MemoryEntry.SENSITIVITY_PUBLIC
        validator.ensure_permissions(
            context,
            action="memory:create",
            sensitivity=sensitivity,
        )

        title = entry_payload.get("title")
        content = entry_payload.get("content")
        if not isinstance(title, str) or not isinstance(content, str):
            raise PermissionDenied("title and content must be provided for new entries.")

        entry = MemoryEntry.objects.create(
            title=title,
            content=content,
            sensitivity=sensitivity,
            entry_type=validated_entry_type or MemoryEntry.TYPE_NOTE,
        )
        return {"entry_id": entry.pk, "version": entry.version}

    if not isinstance(entry_id, int):
        raise PermissionDenied("entry.id must be an integer.")

    expected_version = entry_payload.get("version")
    if not isinstance(expected_version, int):
        raise PermissionDenied("Current version must be provided for updates.")

    with transaction.atomic():
        try:
            entry = MemoryEntry.objects.select_for_update().get(pk=entry_id)
        except MemoryEntry.DoesNotExist as exc:
            raise PermissionDenied("Memory entry not found.") from exc

        validator.ensure_permissions(
            context,
            action="memory:update",
            sensitivity=entry.sensitivity,
        )

        if validated_sensitivity and validated_sensitivity != entry.sensitivity:
            validator.ensure_permissions(
                context,
                action="memory:update",
                sensitivity=validated_sensitivity,
            )

        if entry.version != expected_version:
            raise PermissionDenied("Version conflict detected.")
        updates: Dict[str, object] = {}

        if "title" in entry_payload:
            title = entry_payload["title"]
            if not isinstance(title, str):
                raise PermissionDenied("title must be a string.")
            updates["title"] = title

        if "content" in entry_payload:
            content = entry_payload["content"]
            if not isinstance(content, str):
                raise PermissionDenied("content must be a string.")
            updates["content"] = content

        if validated_sensitivity is not None:
            updates["sensitivity"] = validated_sensitivity
        elif "sensitivity" in entry_payload:
            raise PermissionDenied("sensitivity must be a valid string.")

        if validated_entry_type is not None:
            updates["entry_type"] = validated_entry_type
        elif "entry_type" in entry_payload:
            raise PermissionDenied("entry_type must be a valid string.")

        for field, value in updates.items():
            setattr(entry, field, value)

        entry.version = expected_version + 1
        entry.save(update_fields=[*updates.keys(), "version", "updated_at"])

    return {"entry_id": entry.pk, "version": entry.version}


def memory_delete(*, bearer_token: str, payload: Dict[str, object]) -> Dict[str, object]:
    entry_id = payload.get("entry_id") or payload.get("id")
    if not isinstance(entry_id, int):
        raise PermissionDenied("entry_id must be provided as an integer.")

    version = payload.get("version")
    if version is not None and not isinstance(version, int):
        raise PermissionDenied("version must be an integer when provided.")

    with transaction.atomic():
        try:
            entry = MemoryEntry.objects.select_for_update().get(pk=entry_id)
        except MemoryEntry.DoesNotExist as exc:
            raise PermissionDenied("Memory entry not found.") from exc

        validator.validate(
            bearer_token,
            action="memory:delete",
            required_scopes=[SCOPE_MEMORY_WRITE],
            sensitivity=entry.sensitivity,
        )
        if version is not None and entry.version != version:
            raise PermissionDenied("Version conflict detected.")

        entry.delete()

    return {"ok": True}


__all__ = [
    "memory_delete",
    "memory_get",
    "memory_search",
    "memory_upsert",
]
