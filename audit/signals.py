from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db.models import ManyToManyField, Model
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.forms.models import model_to_dict

from .middleware import get_current_user
from .models import AuditLog

_TRACKED_APP_LABELS = {"memory", "chunks", "policies"}


def _make_json_serializable(value: Any) -> Any:
    """Recursively convert Django model data to JSON-friendly primitives."""

    if isinstance(value, dict):
        return {key: _make_json_serializable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_make_json_serializable(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        try:
            return value.decode()
        except UnicodeDecodeError:  # pragma: no cover - defensive fallback
            return value.hex()
    return value


def _serialize_instance(instance: Model) -> dict[str, Any]:
    """Serialize a model instance to a JSON-serializable dict."""

    opts = instance._meta
    field_names = [field.name for field in opts.fields]
    data = model_to_dict(instance, fields=field_names)
    data["id"] = instance.pk

    # Include many-to-many relations as lists of primary keys for additional context.
    for field in opts.many_to_many:
        if isinstance(field, ManyToManyField):
            data[field.name] = list(
                getattr(instance, field.name).values_list("pk", flat=True)
            )

    return _make_json_serializable(data)


def _build_changes(instance: Model, update_fields: Iterable[str] | None) -> dict[str, Any] | None:
    """Return the updated fields in a JSON-friendly format."""

    if not update_fields:
        return None
    changes = {field: getattr(instance, field) for field in update_fields}
    return _make_json_serializable(changes)


@receiver(post_save)
def audit_post_save(sender, instance: Model, created: bool, update_fields=None, **kwargs):
    if sender._meta.app_label not in _TRACKED_APP_LABELS:
        return

    action = AuditLog.ACTION_CREATE if created else AuditLog.ACTION_UPDATE
    user = get_current_user()
    AuditLog.objects.create(
        user=user,
        action=action,
        app_label=sender._meta.app_label,
        model_name=sender._meta.model_name,
        object_id=str(instance.pk),
        snapshot=_serialize_instance(instance),
        changes=_build_changes(instance, update_fields),
    )


@receiver(post_delete)
def audit_post_delete(sender, instance: Model, **kwargs):
    if sender._meta.app_label not in _TRACKED_APP_LABELS:
        return

    user = get_current_user()
    AuditLog.objects.create(
        user=user,
        action=AuditLog.ACTION_DELETE,
        app_label=sender._meta.app_label,
        model_name=sender._meta.model_name,
        object_id=str(instance.pk),
        snapshot=_serialize_instance(instance),
    )
