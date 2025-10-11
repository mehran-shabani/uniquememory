from __future__ import annotations

import json
from unittest import mock
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from consents.models import Consent, SCOPE_MEMORY_READ, SCOPE_MEMORY_SEARCH
from embeddings.models import Embedding
from memory.models import MemoryEntry
from memory.services.query import HybridQueryService


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


def fake_backend_factory():
    class _Backend:
        def encode(self, texts, batch_size=1, convert_to_numpy=False):
            return [[0.1, 0.2] for _ in texts]

    return _Backend()


class HybridQueryServiceUnitTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.service = HybridQueryService()

    def test_ensure_fts_index_no_entries_skips_setup(self) -> None:
        with mock.patch("memory.services.query.connections") as connections_mock:
            self.service._ensure_fts_index()

        connections_mock.__getitem__.assert_not_called()

    def test_ensure_fts_index_populates_rows_when_marker_changes(self) -> None:
        entry = MemoryEntry.objects.create(title="Doc", content="body")
        mock_cursor = mock.MagicMock()
        mock_cursor.__enter__.return_value = mock_cursor
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with mock.patch("memory.services.query.connections", {"default": mock_connection}), mock.patch(
            "memory.services.query.cache.get",
            return_value=None,
        ) as cache_get, mock.patch("memory.services.query.cache.set") as cache_set:
            self.service._ensure_fts_index()

        cache_get.assert_called()
        mock_cursor.execute.assert_any_call(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {self.service.fts_table} USING fts5(title, content)"
        )
        mock_cursor.execute.assert_any_call(f"DELETE FROM {self.service.fts_table}")
        mock_cursor.executemany.assert_called_once()
        cache_set.assert_called()
        entry.refresh_from_db()

    def test_prepare_fts_query_appends_wildcards(self) -> None:
        result = self.service._prepare_fts_query("alpha beta")
        self.assertEqual(result, "alpha* beta*")
        self.assertEqual(self.service._prepare_fts_query("   "), "   ")

    def test_text_search_normalizes_scores(self) -> None:
        mock_cursor = mock.MagicMock()
        mock_cursor.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(1, -1.0), (2, 3.0)]
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with mock.patch("memory.services.query.connections", {"default": mock_connection}):
            scores = self.service._text_search("alpha", limit=5)

        self.assertAlmostEqual(scores[1], 1.0)
        self.assertLess(scores[2], 1.0)

    def test_vector_search_handles_edge_cases(self) -> None:
        self.assertEqual(self.service._vector_search([], limit=5), {})
        self.assertEqual(self.service._vector_search([0.0, 0.0], limit=5), {})

    def test_vector_search_returns_scored_results(self) -> None:
        entry = MemoryEntry.objects.create(title="Vec", content="")
        Embedding.objects.create(memory_entry=entry, vector=[1.0, 0.0], model_name="m", dimension=2)

        scores = self.service._vector_search([1.0, 0.0], limit=5)

        self.assertIn(entry.pk, scores)
        self.assertGreater(scores[entry.pk], 0)

    def test_combine_scores_filters_missing_entries(self) -> None:
        result = self.service._combine_scores({1: 0.5}, {}, limit=5)
        self.assertEqual(result, [])

        entry = MemoryEntry.objects.create(title="Score", content="")
        combined = self.service._combine_scores({entry.pk: 0.5}, {entry.pk: 0.2}, limit=1)
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined[0].entry_id, entry.pk)

    def test_encode_query_handles_list_and_numpy_outputs(self) -> None:
        backend = mock.MagicMock()
        backend.encode.return_value = [[0.1, 0.2]]
        service = HybridQueryService()
        service.__dict__["_embedding_backend"] = backend
        self.assertEqual(service._encode_query("hello"), [0.1, 0.2])

        class _Array:
            def __init__(self, values):
                self._values = values

            def tolist(self):
                return list(self._values)

        backend2 = mock.MagicMock()
        backend2.encode.return_value = [_Array([0.3, 0.4])]
        service2 = HybridQueryService()
        service2.__dict__["_embedding_backend"] = backend2
        self.assertEqual(service2._encode_query("world"), [0.3, 0.4])

    @override_settings(EMBEDDINGS_BACKEND="tests.test_query.fake_backend_factory")
    def test_embedding_backend_uses_configured_factory(self) -> None:
        service = HybridQueryService()
        backend = service._embedding_backend
        self.assertEqual(backend.encode(["hi"]), [[0.1, 0.2]])

    @override_settings(EMBEDDINGS_BACKEND=None, EMBEDDINGS_MODEL_NAME="model-name")
    def test_embedding_backend_defaults_to_sentence_transformer(self) -> None:
        with mock.patch("memory.services.query.SentenceTransformer") as sentence:
            service = HybridQueryService()
            backend = service._embedding_backend

        sentence.assert_called_once_with("model-name")
        self.assertIsNotNone(backend)

    def test_vector_norm_and_cosine_similarity(self) -> None:
        self.assertAlmostEqual(self.service._vector_norm([3, 4]), 5.0)
        similarity = self.service._cosine_similarity([1, 0], [1, 0], 1.0)
        self.assertAlmostEqual(similarity, 1.0)

        zero_similarity = self.service._cosine_similarity([1, 0], [0, 0], 1.0)
        self.assertEqual(zero_similarity, 0.0)
