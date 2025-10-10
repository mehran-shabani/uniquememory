from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import Signal, receiver

from memory.models import MemoryEntry

entry_created = Signal()  # provides: entry
entry_updated = Signal()  # provides: entry
entry_deleted = Signal()  # provides: entry_id


@receiver(post_save, sender=MemoryEntry)
def _handle_entry_saved(sender, instance: MemoryEntry, created: bool, **_kwargs):
    if created:
        entry_created.send(sender=sender, entry=instance)
    else:
        entry_updated.send(sender=sender, entry=instance)


@receiver(post_delete, sender=MemoryEntry)
def _handle_entry_deleted(sender, instance: MemoryEntry, **_kwargs):
    entry_deleted.send(sender=sender, entry_id=instance.pk)
