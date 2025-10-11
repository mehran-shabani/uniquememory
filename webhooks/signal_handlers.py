from __future__ import annotations

from django.db import transaction
from django.dispatch import receiver

from consents import signals as consent_signals
from memory import signals as memory_signals

from .services.dispatcher import dispatcher


def _dispatch_event(*, event: str, data: dict[str, object]) -> None:
    connection = transaction.get_connection()
    if connection.in_atomic_block and not connection.savepoint_ids:
        dispatcher.dispatch(event=event, data=data)
    else:
        transaction.on_commit(lambda: dispatcher.dispatch(event=event, data=data))


@receiver(memory_signals.entry_created)
def handle_entry_created(sender, entry, **_kwargs):
    data = {
        "entry_id": entry.pk,
        "title": entry.title,
        "sensitivity": entry.sensitivity,
        "entry_type": entry.entry_type,
    }

    _dispatch_event(event="memory.entry.created", data=data)


@receiver(memory_signals.entry_updated)
def handle_entry_updated(sender, entry, **_kwargs):
    data = {
        "entry_id": entry.pk,
        "title": entry.title,
        "sensitivity": entry.sensitivity,
        "entry_type": entry.entry_type,
    }

    _dispatch_event(event="memory.entry.updated", data=data)


@receiver(memory_signals.entry_deleted)
def handle_entry_deleted(sender, entry_id, **_kwargs):
    data = {
        "entry_id": entry_id,
    }

    _dispatch_event(event="memory.entry.deleted", data=data)


@receiver(consent_signals.consent_created)
def handle_consent_created(sender, consent, **_kwargs):
    data = {
        "consent_id": consent.pk,
        "user_id": consent.user_id,
        "agent_identifier": consent.agent_identifier,
        "status": consent.status,
    }

    _dispatch_event(event="consent.created", data=data)


@receiver(consent_signals.consent_revoked)
def handle_consent_revoked(sender, consent, **_kwargs):
    data = {
        "consent_id": consent.pk,
        "user_id": consent.user_id,
        "agent_identifier": consent.agent_identifier,
        "status": consent.status,
        "revoked_at": consent.revoked_at.isoformat() if consent.revoked_at else None,
    }

    _dispatch_event(event="consent.revoked", data=data)
