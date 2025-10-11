from __future__ import annotations

import os
from typing import Any, Type

from django.db import transaction
from django.dispatch import receiver

from consents import signals as consent_signals
from memory import signals as memory_signals
from memory.models import MemoryEntry

from consents.models import Consent

from .services.dispatcher import dispatcher


def _dispatch_event(*, event: str, data: dict[str, object]) -> None:
    """Schedule webhook delivery once the surrounding transaction commits."""

    executed = False

    def _send() -> None:
        nonlocal executed
        if executed:
            return
        executed = True
        dispatcher.dispatch(event=event, data=data)

    transaction.on_commit(_send)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        _send()


@receiver(memory_signals.entry_created)
def handle_entry_created(sender: Type[MemoryEntry], entry: MemoryEntry, **_kwargs: Any) -> None:
    data = {
        "entry_id": entry.pk,
        "title": entry.title,
        "sensitivity": entry.sensitivity,
        "entry_type": entry.entry_type,
    }

    _dispatch_event(event="memory.entry.created", data=data)


@receiver(memory_signals.entry_updated)
def handle_entry_updated(sender: Type[MemoryEntry], entry: MemoryEntry, **_kwargs: Any) -> None:
    data = {
        "entry_id": entry.pk,
        "title": entry.title,
        "sensitivity": entry.sensitivity,
        "entry_type": entry.entry_type,
    }

    _dispatch_event(event="memory.entry.updated", data=data)


@receiver(memory_signals.entry_deleted)
def handle_entry_deleted(sender: Type[MemoryEntry], entry_id: int, **_kwargs: Any) -> None:
    data = {
        "entry_id": entry_id,
    }

    _dispatch_event(event="memory.entry.deleted", data=data)


@receiver(consent_signals.consent_created)
def handle_consent_created(sender: Type[Consent], consent: Consent, **_kwargs: Any) -> None:
    data = {
        "consent_id": consent.pk,
        "user_id": str(consent.user_id),
        "agent_identifier": consent.agent_identifier,
        "status": consent.status,
    }

    _dispatch_event(event="consent.created", data=data)


@receiver(consent_signals.consent_revoked)
def handle_consent_revoked(sender: Type[Consent], consent: Consent, **_kwargs: Any) -> None:
    data = {
        "consent_id": consent.pk,
        "user_id": str(consent.user_id),
        "agent_identifier": consent.agent_identifier,
        "status": consent.status,
        "revoked_at": consent.revoked_at.isoformat() if consent.revoked_at else None,
    }

    _dispatch_event(event="consent.revoked", data=data)
