from __future__ import annotations

import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from consents.models import Consent, SCOPE_MEMORY_READ, SCOPE_MEMORY_SEARCH
from embeddings.models import Embedding
from memory.models import MemoryEntry


class HybridQueryApiTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user("alice@example.com", "password")
        self.agent_identifier = "test-agent"
        self.entry_alpha = MemoryEntry.objects.create(
            title="Alpha release plan",
            content="Details about the alpha project milestones and release goals.",
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            entry_type=MemoryEntry.TYPE_NOTE,
        )
        self.entry_beta = MemoryEntry.objects.create(
            title="Beta customer feedback",
            content="Feedback from beta testers about usability and interface.",
            sensitivity=MemoryEntry.SENSITIVITY_CONFIDENTIAL,
            entry_type=MemoryEntry.TYPE_NOTE,
        )
        self.entry_gamma = MemoryEntry.objects.create(
            title="Gamma incident report",
            content="Summary of the outage and remediation steps taken.",
            sensitivity=MemoryEntry.SENSITIVITY_SECRET,
            entry_type=MemoryEntry.TYPE_EVENT,
        )

        Embedding.objects.create(
            memory_entry=self.entry_alpha,
            vector=[1.0, 0.0],
            dimension=2,
            model_name="test-model",
        )
        Embedding.objects.create(
            memory_entry=self.entry_beta,
            vector=[0.8, 0.2],
            dimension=2,
            model_name="test-model",
        )
        Embedding.objects.create(
            memory_entry=self.entry_gamma,
            vector=[0.0, 1.0],
            dimension=2,
            model_name="test-model",
        )

        Consent.objects.create(
            user=self.user,
            agent_identifier=self.agent_identifier,
            scopes=[SCOPE_MEMORY_SEARCH, SCOPE_MEMORY_READ],
            sensitivity_levels=[
                MemoryEntry.SENSITIVITY_PUBLIC,
                MemoryEntry.SENSITIVITY_CONFIDENTIAL,
                MemoryEntry.SENSITIVITY_SECRET,
            ],
            status=Consent.STATUS_ACTIVE,
        )

        self.url = reverse("memory-query", kwargs={"user_id": self.user.pk})

    def _post_query(self, query: str, limit: int = 10):
        payload = json.dumps({"query": query, "limit": limit})
        return self.client.post(
            self.url,
            data=payload,
            content_type="application/json",
            HTTP_X_AGENT_ID=self.agent_identifier,
        )

    def test_hybrid_query_orders_results(self):
        with patch("memory.services.query.HybridQueryService._encode_query", return_value=[1.0, 0.0]):
            response = self._post_query("alpha project release")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 2)
        top_result = payload["results"][0]
        self.assertEqual(top_result["id"], self.entry_alpha.id)
        self.assertGreaterEqual(top_result["scores"]["vector"], top_result["scores"]["text"])
        second_result = payload["results"][1]
        self.assertEqual(second_result["id"], self.entry_beta.id)

    def test_hybrid_query_uses_cache(self):
        with patch("memory.services.query.HybridQueryService._encode_query", return_value=[1.0, 0.0]) as mock_encode:
            first = self._post_query("alpha project release")
            second = self._post_query("alpha project release")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(mock_encode.call_count, 1)
        self.assertEqual(first.json(), second.json())
