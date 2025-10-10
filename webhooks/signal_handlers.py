from __future__ import annotations

from django.dispatch import receiver

from consents import signals as consent_signals
from memory import signals as memory_signals

from .services.dispatcher import dispatcher


@receiver(memory_signals.entry_created)
def handle_entry_created(sender, entry, **_kwargs):
    dispatcher.dispatch(
        event="memory.entry.created",
        data={
            "entry_id": entry.pk,
            "title": entry.title,
            "sensitivity": entry.sensitivity,
            "entry_type": entry.entry_type,
        },
    )


@receiver(memory_signals.entry_updated)
def handle_entry_updated(sender, entry, **_kwargs):
    dispatcher.dispatch(
        event="memory.entry.updated",
        data={
            "entry_id": entry.pk,
            "title": entry.title,
            "sensitivity": entry.sensitivity,
            "entry_type": entry.entry_type,
        },
    )


@receiver(memory_signals.entry_deleted)
def handle_entry_deleted(sender, entry_id, **_kwargs):
    dispatcher.dispatch(
        event="memory.entry.deleted",
        data={
            "entry_id": entry_id,
        },
    )


@receiver(consent_signals.consent_created)
def handle_consent_created(sender, consent, **_kwargs):
    dispatcher.dispatch(
        event="consent.created",
        data={
            "consent_id": consent.pk,
            "user_id": consent.user_id,
            "agent_identifier": consent.agent_identifier,
            "status": consent.status,
        },
    )


@receiver(consent_signals.consent_revoked)
def handle_consent_revoked(sender, consent, **_kwargs):
    dispatcher.dispatch(
        event="consent.revoked",
        data={
            "consent_id": consent.pk,
            "user_id": consent.user_id,
            "agent_identifier": consent.agent_identifier,
            "status": consent.status,
            "revoked_at": consent.revoked_at.isoformat() if consent.revoked_at else None,
        },
    )
