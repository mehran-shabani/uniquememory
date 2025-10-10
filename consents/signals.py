from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

from consents.models import Consent

consent_created = Signal()  # provides: consent
consent_revoked = Signal()  # provides: consent


@receiver(post_save, sender=Consent)
def _handle_consent_created(sender, instance: Consent, created: bool, **_kwargs):
    if created:
        consent_created.send(sender=sender, consent=instance)
