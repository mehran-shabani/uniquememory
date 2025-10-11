from __future__ import annotations

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


def _extract_entry_payload(payload: Dict[str, object]) -> Dict[str, object]:
    entry_payload = payload.get("entry") or payload
    if not isinstance(entry_payload, dict):
        raise PermissionDenied("Entry payload must be an object.")
    return entry_payload


def _validate_text_field(payload: Dict[str, object], field: str) -> None:
    if field in payload and not isinstance(payload[field], str):
        raise PermissionDenied(f"{field} must be a string.")


def _validate_choice(value: str | None, *, choices: set[str], field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PermissionDenied(f"{field} must be a string.")
    if value not in choices:
        raise PermissionDenied(f"Invalid {field} provided.")
    return value


def memory_upsert(*, bearer_token: str, payload: Dict[str, object]) -> Dict[str, object]:
    entry_payload = _extract_entry_payload(payload)
    entry_id = entry_payload.get("id") or payload.get("entry_id")

    sensitivity_choices = {choice for choice, _ in MemoryEntry.SENSITIVITY_CHOICES}
    requested_sensitivity = _validate_choice(
        entry_payload.get("sensitivity"),
        choices=sensitivity_choices,
        field="sensitivity",
    )

    type_choices = {choice for choice, _ in MemoryEntry.TYPE_CHOICES}
    entry_type_value = entry_payload.get("entry_type")
    validated_entry_type = _validate_choice(
        entry_type_value,
        choices=type_choices,
        field="entry_type",
    )

    _validate_text_field(entry_payload, "title")
    _validate_text_field(entry_payload, "content")

    if entry_id is None:
        sensitivity = requested_sensitivity or MemoryEntry.SENSITIVITY_PUBLIC
        validator.validate(
            bearer_token,
            action="memory:create",
            required_scopes=[SCOPE_MEMORY_WRITE],
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

        context = validator.validate(
            bearer_token,
            action="memory:update",
            required_scopes=[SCOPE_MEMORY_WRITE],
            sensitivity=entry.sensitivity,
        )

        if requested_sensitivity and requested_sensitivity != entry.sensitivity:
            validator.ensure_permissions(
                context,
                action="memory:update",
                sensitivity=requested_sensitivity,
            )

        if entry.version != expected_version:
            raise PermissionDenied("Version conflict detected.")

        updates = {
            key: entry_payload[key]
            for key in {"title", "content", "sensitivity", "entry_type"}
            if key in entry_payload
        }
        for field, value in updates.items():
            setattr(entry, field, value)
        if requested_sensitivity is not None:
            entry.sensitivity = requested_sensitivity
        if validated_entry_type is not None:
            entry.entry_type = validated_entry_type

        entry.version = expected_version + 1
        update_fields = {"version", "updated_at", *updates.keys()}
        entry.save(update_fields=sorted(update_fields))

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
