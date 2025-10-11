from __future__ import annotations

from unittest import mock

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from consents.models import Consent, SCOPE_MEMORY_READ, SCOPE_MEMORY_SEARCH, SCOPE_MEMORY_WRITE
from memory.models import MemoryEntry
from memory.services.query import HybridSearchResult
from mcp.tools import memory as memory_tools
from mcp.tools.memory import memory_delete, memory_get, memory_search


class MemoryToolTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("searcher@example.com", "password")
        self.consent = Consent.objects.create(
            user=self.user,
            agent_identifier="memory-client",
            scopes=[SCOPE_MEMORY_READ, SCOPE_MEMORY_SEARCH, SCOPE_MEMORY_WRITE],
            sensitivity_levels=[
                MemoryEntry.SENSITIVITY_PUBLIC,
                MemoryEntry.SENSITIVITY_CONFIDENTIAL,
            ],
            status=Consent.STATUS_ACTIVE,
        )
        self.token = self._build_token()

    def _build_token(self) -> str:
        token = AccessToken.for_user(self.user)
        token["sub"] = str(self.user.pk)
        token["agent_id"] = self.consent.agent_identifier
        token["scopes"] = [SCOPE_MEMORY_READ, SCOPE_MEMORY_SEARCH, SCOPE_MEMORY_WRITE]
        token["consent_id"] = self.consent.pk
        return str(token)

    def test_memory_search_requires_query(self) -> None:
        with self.assertRaises(PermissionDenied):
            memory_search(bearer_token=self.token, payload={})

    def test_memory_search_validates_limit(self) -> None:
        with self.assertRaises(PermissionDenied):
            memory_search(bearer_token=self.token, payload={"query": "hi", "limit": 0})

    def test_memory_search_rejects_impersonation(self) -> None:
        with self.assertRaises(PermissionDenied):
            memory_search(
                bearer_token=self.token,
                payload={
                    "query": "roadmap",
                    "user_id": "00000000-0000-0000-0000-000000000000",
                },
            )

    @mock.patch("mcp.tools.memory.query_service.search")
    def test_memory_search_filters_results_and_checks_permissions(self, mock_search: mock.Mock) -> None:
        mock_search.return_value = [
            HybridSearchResult(
                entry_id=1,
                title="Public plan",
                snippet="",
                combined_score=0.8,
                text_score=0.6,
                vector_score=0.2,
                sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
                entry_type=MemoryEntry.TYPE_NOTE,
            ),
            HybridSearchResult(
                entry_id=2,
                title="Confidential note",
                snippet="",
                combined_score=0.5,
                text_score=0.5,
                vector_score=0.0,
                sensitivity=MemoryEntry.SENSITIVITY_CONFIDENTIAL,
                entry_type=MemoryEntry.TYPE_NOTE,
            ),
            HybridSearchResult(
                entry_id=3,
                title="Secret incident",
                snippet="",
                combined_score=0.9,
                text_score=0.9,
                vector_score=0.0,
                sensitivity=MemoryEntry.SENSITIVITY_SECRET,
                entry_type=MemoryEntry.TYPE_NOTE,
            ),
        ]

        with mock.patch.object(
            Consent,
            "allows_sensitivity",
            side_effect=lambda _self, level: level != MemoryEntry.SENSITIVITY_SECRET,
        ) as allows_mock, mock.patch.object(memory_tools.validator, "ensure_permissions") as ensure_permissions:
            result = memory_search(bearer_token=self.token, payload={"query": "plan"})

        self.assertEqual(result["count"], 2)
        self.assertEqual({item["title"] for item in result["results"]}, {"Public plan", "Confidential note"})
        allows_mock.assert_any_call(MemoryEntry.SENSITIVITY_PUBLIC)
        ensure_permissions.assert_called_once()

    def test_memory_get_validates_identifier(self) -> None:
        with self.assertRaises(PermissionDenied):
            memory_get(bearer_token=self.token, payload={})

    def test_memory_get_requires_existing_entry(self) -> None:
        with self.assertRaises(PermissionDenied):
            memory_get(bearer_token=self.token, payload={"entry_id": 9999})

    def test_memory_get_serializes_entry(self) -> None:
        entry = MemoryEntry.objects.create(title="Doc", content="body")

        result = memory_get(bearer_token=self.token, payload={"entry_id": entry.pk})

        self.assertEqual(result["entry"]["id"], entry.pk)
        self.assertEqual(result["entry"]["title"], "Doc")

    def test_memory_delete_validates_identifier(self) -> None:
        with self.assertRaises(PermissionDenied):
            memory_delete(bearer_token=self.token, payload={})

    def test_memory_delete_validates_version_type(self) -> None:
        with self.assertRaises(PermissionDenied):
            memory_delete(bearer_token=self.token, payload={"entry_id": 1, "version": "one"})

    def test_memory_delete_checks_version(self) -> None:
        entry = MemoryEntry.objects.create(title="To remove", content="body")

        with self.assertRaises(PermissionDenied):
            memory_delete(
                bearer_token=self.token,
                payload={"entry_id": entry.pk, "version": entry.version + 1},
            )

    def test_memory_delete_removes_entry(self) -> None:
        entry = MemoryEntry.objects.create(title="Disposable", content="body")

        result = memory_delete(bearer_token=self.token, payload={"entry_id": entry.pk, "version": entry.version})

        self.assertTrue(result["ok"])
        self.assertFalse(MemoryEntry.objects.filter(pk=entry.pk).exists())
