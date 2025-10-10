from __future__ import annotations

import json
from unittest import mock

from django.test import TestCase

from companies.models import Company
from memory.models import MemoryEntry
from webhooks.models import WebhookSubscription
from webhooks.services.dispatcher import dispatcher


class WebhookDispatchTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.company = Company.objects.create(name="Acme", slug="acme")
        self.subscription = WebhookSubscription.objects.create(
            company=self.company,
            target_url="https://example.com/webhook",
            events=["memory.entry.created", "consent.revoked"],
            secret="topsecret",
        )

    @mock.patch("webhooks.services.dispatcher.requests.Session.post")
    def test_signal_dispatches_signed_payload_for_active_subscription(self, mock_post: mock.Mock) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None

        entry = MemoryEntry.objects.create(title="Hello", content="world")

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, WebhookSubscription.STATUS_ACTIVE)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        body = kwargs["json"]
        self.assertIn("signature", body)
        signatureless = dict(body)
        signatureless.pop("signature")
        expected = {
            "event": "memory.entry.created",
            "ts": mock.ANY,
            "entry_id": entry.pk,
            "title": entry.title,
            "sensitivity": entry.sensitivity,
            "entry_type": entry.entry_type,
        }
        self.assertDictEqual(signatureless, expected)

        serialized = json.dumps(signatureless, separators=(",", ":"), sort_keys=True).encode()
        # Ensure signature is deterministic by recomputing
        from hashlib import sha256
        import hmac

        recomputed = hmac.new(self.subscription.secret.encode(), serialized, sha256).hexdigest()
        self.assertEqual(body["signature"], recomputed)

    @mock.patch("webhooks.services.dispatcher.requests.Session.post")
    def test_failure_marks_subscription(self, mock_post: mock.Mock) -> None:
        mock_post.side_effect = Exception("boom")

        dispatcher.dispatch(event="memory.entry.created", data={"entry_id": 1})

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.failure_count, 1)
        self.assertEqual(self.subscription.status, WebhookSubscription.STATUS_ACTIVE)

        dispatcher.dispatch(event="memory.entry.created", data={"entry_id": 1})
        dispatcher.dispatch(event="memory.entry.created", data={"entry_id": 1})

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.failure_count, 3)
        self.assertEqual(self.subscription.status, WebhookSubscription.STATUS_ERROR)

    @mock.patch("webhooks.services.dispatcher.requests.Session.post")
    def test_ignores_subscriptions_not_subscribed_to_event(self, mock_post: mock.Mock) -> None:
        dispatcher.dispatch(event="consent.created", data={"consent_id": 1})

        mock_post.assert_not_called()
