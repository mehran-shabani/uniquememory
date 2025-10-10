from __future__ import annotations

from typing import Any, Dict, Iterable

from django.db.models import ManyToManyField, Model
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.forms.models import model_to_dict

from .middleware import get_current_user
from .models import AuditLog

_TRACKED_APP_LABELS = {"memory", "chunks", "policies"}


def _serialize_instance(instance: Model) -> Dict[str, Any]:
    opts = instance._meta
    field_names = [field.name for field in opts.fields]
    data = model_to_dict(instance, fields=field_names)
    data["id"] = instance.pk

    # Include many-to-many relations as lists of primary keys for additional context.
    for field in opts.many_to_many:
        if isinstance(field, ManyToManyField):
            data[field.name] = list(getattr(instance, field.name).values_list("pk", flat=True))
    return data


def _build_changes(instance: Model, update_fields: Iterable[str] | None) -> Dict[str, Any] | None:
    if not update_fields:
        return None
    return {field: getattr(instance, field) for field in update_fields}


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
