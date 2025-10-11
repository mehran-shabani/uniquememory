from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction

from consents.models import SCOPE_MEMORY_READ, SCOPE_MEMORY_SEARCH, SCOPE_MEMORY_WRITE
from memory.models import MemoryEntry
from memory.services.query import HybridQueryService, HybridSearchResult

from ..auth import BearerTokenValidator

validator = BearerTokenValidator()
query_service = HybridQueryService()

SENSITIVITY_TYPE_ERROR = "sensitivity must be a string."
SENSITIVITY_CHOICE_ERROR = "sensitivity must be one of the supported values."
ENTRY_TYPE_TYPE_ERROR = "entry_type must be a string."
ENTRY_TYPE_CHOICE_ERROR = "entry_type must be one of the supported values."
ENTRY_PAYLOAD_TYPE_ERROR = "entry payload must be provided as an object."
TITLE_CONTENT_REQUIRED_ERROR = "title and content must be provided for new entries."
TITLE_STRING_ERROR = "title must be a string."
CONTENT_STRING_ERROR = "content must be a string."
SENSITIVITY_VALID_STRING_ERROR = "sensitivity must be a valid string."
ENTRY_TYPE_VALID_STRING_ERROR = "entry_type must be a valid string."
ENTRY_ID_INT_ERROR = "entry.id must be an integer."
VERSION_REQUIRED_ERROR = "Current version must be provided for updates."
VERSION_CONFLICT_ERROR = "Version conflict detected."
ENTRY_NOT_FOUND_ERROR = "Memory entry not found."
ENTRY_ID_REQUIRED_ERROR = "entry_id must be provided as an integer."
ENTRY_VERSION_INT_ERROR = "version must be an integer when provided."
SEARCH_QUERY_REQUIRED_ERROR = "Search query is required."
LIMIT_POSITIVE_INT_ERROR = "Limit must be a positive integer."
UNAUTHORIZED_SEARCH_ERROR = "Searching on behalf of another user is not permitted."


def _serialize_entry(entry: MemoryEntry) -> dict[str, object]:
    return {
        "id": entry.pk,
        "title": entry.title,
        "content": entry.content,
        "sensitivity": entry.sensitivity,
        "entry_type": entry.entry_type,
        "version": entry.version,
        "updated_at": entry.updated_at.isoformat(),
    }


def memory_search(*, bearer_token: str, payload: dict[str, object]) -> dict[str, object]:
    query = payload.get("query") or payload.get("q")
    if not isinstance(query, str) or not query.strip():
        raise PermissionDenied(SEARCH_QUERY_REQUIRED_ERROR)

    limit_value = payload.get("limit")
    if limit_value is None:
        limit_value = payload.get("k")
    limit = limit_value if limit_value is not None else 10
    if not isinstance(limit, int) or limit <= 0:
        raise PermissionDenied(LIMIT_POSITIVE_INT_ERROR)

    context = validator.parse(
        bearer_token,
        required_scopes=[SCOPE_MEMORY_SEARCH],
    )

    user_id_from_payload = payload.get("user_id")
    if user_id_from_payload and str(user_id_from_payload) != str(context.subject.pk):
        raise PermissionDenied(UNAUTHORIZED_SEARCH_ERROR)

    raw_results = query_service.search(
        user_id=str(context.subject.pk),
        query=query,
        limit=limit,
    )

    consent = context.consent
    allowed: list[HybridSearchResult]
    if consent:
        allowed = []
        for result in raw_results:
            allows_check = consent.allows_sensitivity
            try:
                permitted = allows_check(result.sensitivity)
            except TypeError as exc:
                try:
                    # Some callers (tests) patch the descriptor without binding self.
                    permitted = allows_check(consent, result.sensitivity)
                except TypeError:
                    raise exc
            if permitted:
                allowed.append(result)
    else:
        allowed = list(raw_results)
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


def memory_get(*, bearer_token: str, payload: dict[str, object]) -> dict[str, object]:
    entry_id = payload.get("entry_id") or payload.get("id")
    if not isinstance(entry_id, int):
        raise PermissionDenied(ENTRY_ID_REQUIRED_ERROR)

    try:
        entry = MemoryEntry.objects.get(pk=entry_id)
    except MemoryEntry.DoesNotExist as exc:
        raise PermissionDenied(ENTRY_NOT_FOUND_ERROR) from exc

    validator.validate(
        bearer_token,
        action="memory:retrieve",
        required_scopes=[SCOPE_MEMORY_READ],
        sensitivity=entry.sensitivity,
    )

    return {"entry": _serialize_entry(entry)}

def memory_upsert(*, bearer_token: str, payload: dict[str, object]) -> dict[str, object]:
    entry_payload_obj = payload.get("entry") if isinstance(payload, dict) else None
    if entry_payload_obj is None:
        entry_payload_obj = payload
    if not isinstance(entry_payload_obj, dict):
        raise PermissionDenied(ENTRY_PAYLOAD_TYPE_ERROR)

    entry_payload: dict[str, object] = entry_payload_obj
    entry_id = entry_payload.get("entry_id") or entry_payload.get("id")

    requested_sensitivity = entry_payload.get("sensitivity")
    validated_sensitivity: str | None = None
    if requested_sensitivity is not None:
        if not isinstance(requested_sensitivity, str):
            raise PermissionDenied(SENSITIVITY_TYPE_ERROR)
        valid_sensitivities = {choice for choice, _label in MemoryEntry.SENSITIVITY_CHOICES}
        if requested_sensitivity not in valid_sensitivities:
            raise PermissionDenied(SENSITIVITY_CHOICE_ERROR)
        validated_sensitivity = requested_sensitivity

    entry_type = entry_payload.get("entry_type")
    if entry_type is not None and not isinstance(entry_type, str):
        raise PermissionDenied(ENTRY_TYPE_TYPE_ERROR)

    validated_entry_type: str | None = None
    if entry_type is not None:
        valid_entry_types = {choice for choice, _label in MemoryEntry.TYPE_CHOICES}
        if entry_type not in valid_entry_types:
            raise PermissionDenied(ENTRY_TYPE_CHOICE_ERROR)
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
            raise PermissionDenied(TITLE_CONTENT_REQUIRED_ERROR)

        entry = MemoryEntry.objects.create(
            title=title,
            content=content,
            sensitivity=sensitivity,
            entry_type=validated_entry_type or MemoryEntry.TYPE_NOTE,
        )
        return {"entry_id": entry.pk, "version": entry.version}

    if not isinstance(entry_id, int):
        raise PermissionDenied(ENTRY_ID_INT_ERROR)

    expected_version = entry_payload.get("version")
    if not isinstance(expected_version, int):
        raise PermissionDenied(VERSION_REQUIRED_ERROR)

    with transaction.atomic():
        try:
            entry = MemoryEntry.objects.select_for_update().get(pk=entry_id)
        except MemoryEntry.DoesNotExist as exc:
            raise PermissionDenied(ENTRY_NOT_FOUND_ERROR) from exc

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
            raise PermissionDenied(VERSION_CONFLICT_ERROR)
        updates: dict[str, object] = {}

        if "title" in entry_payload:
            title = entry_payload["title"]
            if not isinstance(title, str):
                raise PermissionDenied(TITLE_STRING_ERROR)
            updates["title"] = title

        if "content" in entry_payload:
            content = entry_payload["content"]
            if not isinstance(content, str):
                raise PermissionDenied(CONTENT_STRING_ERROR)
            updates["content"] = content

        if validated_sensitivity is not None:
            updates["sensitivity"] = validated_sensitivity
        elif "sensitivity" in entry_payload:
            raise PermissionDenied(SENSITIVITY_VALID_STRING_ERROR)

        if validated_entry_type is not None:
            updates["entry_type"] = validated_entry_type
        elif "entry_type" in entry_payload:
            raise PermissionDenied(ENTRY_TYPE_VALID_STRING_ERROR)

        for field, value in updates.items():
            setattr(entry, field, value)

        entry.version = expected_version + 1
        entry.save(update_fields=[*updates.keys(), "version", "updated_at"])

    return {"entry_id": entry.pk, "version": entry.version}


def memory_delete(*, bearer_token: str, payload: dict[str, object]) -> dict[str, object]:
    entry_id = payload.get("entry_id") or payload.get("id")
    if not isinstance(entry_id, int):
        raise PermissionDenied(ENTRY_ID_REQUIRED_ERROR)

    version = payload.get("version")
    if version is not None and not isinstance(version, int):
        raise PermissionDenied(ENTRY_VERSION_INT_ERROR)

    with transaction.atomic():
        try:
            entry = MemoryEntry.objects.select_for_update().get(pk=entry_id)
        except MemoryEntry.DoesNotExist as exc:
            raise PermissionDenied(ENTRY_NOT_FOUND_ERROR) from exc

        validator.validate(
            bearer_token,
            action="memory:delete",
            required_scopes=[SCOPE_MEMORY_WRITE],
            sensitivity=entry.sensitivity,
        )
        if version is not None and entry.version != version:
            raise PermissionDenied(VERSION_CONFLICT_ERROR)

        entry.delete()

    return {"ok": True}


__all__ = [
    "memory_delete",
    "memory_get",
    "memory_search",
    "memory_upsert",
]
