from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Optional

import requests
from django.utils import timezone

from webhooks.models import WebhookSubscription

EVENT_REQUIRED_FIELDS: dict[str, set[str]] = {
    "memory.entry.created": {"entry_id"},
    "memory.entry.updated": {"entry_id"},
    "memory.entry.deleted": {"entry_id"},
    "consent.created": {"consent_id", "agent_identifier"},
    "consent.revoked": {"consent_id", "agent_identifier"},
}

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """Pushes webhook payloads to subscribed companies."""

    def __init__(self, *, session: Optional[requests.Session] = None) -> None:
        self._session = session

    def dispatch(self, *, event: str, data: dict[str, Any]) -> None:
        subscriptions = WebhookSubscription.objects.active().for_event(event)
        for subscription in subscriptions:
            if not self._event_has_required_fields(event, data):
                logger.debug(
                    "Skipping webhook dispatch due to incomplete payload",
                    extra={
                        "event": event,
                        "subscription_id": subscription.pk,
                    },
                )
                continue
            payload = self._build_payload(event=event, data=data)
            try:
                self._deliver(subscription, payload)
            except Exception as exc:  # pragma: no cover - network errors vary
                logger.warning("Webhook delivery failed", exc_info=exc)
                subscription.mark_failure(str(exc))
            else:
                subscription.mark_success()

    def _build_payload(self, *, event: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "event": event,
            "ts": timezone.now().isoformat(),
            **data,
        }
        return payload

    def _deliver(self, subscription: WebhookSubscription, payload: dict[str, Any]) -> None:
        body = self._sign_payload(subscription.secret, payload)
        session = self._session or requests.Session()
        try:
            response = session.post(subscription.target_url, json=body, timeout=5)
            response.raise_for_status()
        finally:
            if self._session is None:
                session.close()

    def _sign_payload(self, secret: str, payload: dict[str, Any]) -> dict[str, Any]:
        serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        signature = hmac.new(secret.encode(), serialized, hashlib.sha256).hexdigest()
        signed_payload = dict(payload)
        signed_payload["signature"] = signature
        return signed_payload

    def _event_has_required_fields(self, event: str, data: dict[str, Any]) -> bool:
        required = EVENT_REQUIRED_FIELDS.get(event)
        if not required:
            return True
        present = {key for key in data if data.get(key) is not None}
        return required.issubset(present)


dispatcher = WebhookDispatcher()
