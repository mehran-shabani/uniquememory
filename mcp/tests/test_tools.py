from __future__ import annotations

import json
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models.signals import post_delete, post_save
from django.test import TestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from consents.models import (
    Consent,
    SCOPE_MEMORY_READ,
    SCOPE_MEMORY_SEARCH,
    SCOPE_MEMORY_WRITE,
)
from embeddings.models import Embedding
from memory.models import MemoryEntry

from mcp.manifest import MANIFEST
from mcp.tools import execute_tool
from mcp.tools.consent import CONSENT_MANAGE_SCOPE

from audit import signals as audit_signals


class McpToolIntegrationTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.graph_connect_patch = patch("graph.services.sync.graph_sync_service.connect")
        self.graph_connect_patch.start()
        self.addCleanup(self.graph_connect_patch.stop)
        from graph.services.sync import graph_sync_service

        self.graph_connect_patch = patch("graph.services.sync.graph_sync_service.connect")
        self.graph_connect_patch.start()

        def _restore_signal_state() -> None:
            # Stop mocking connect and re-attach all of our sync handlers
            self.graph_connect_patch.stop()
            graph_sync_service.connect()
            post_save.connect(audit_signals.audit_post_save, weak=False)
            post_delete.connect(audit_signals.audit_post_delete, weak=False)

        self.addCleanup(_restore_signal_state)

        post_save.disconnect(dispatch_uid="graph.sync.memory.save", sender=MemoryEntry)
        post_delete.disconnect(dispatch_uid="graph.sync.memory.delete", sender=MemoryEntry)
        post_save.disconnect(dispatch_uid="graph.sync.consent.save", sender=Consent)
        post_delete.disconnect(dispatch_uid="graph.sync.consent.delete", sender=Consent)
        post_save.disconnect(audit_signals.audit_post_save)
        post_delete.disconnect(audit_signals.audit_post_delete)
        self.user = User.objects.create_user("agent-user@example.com", "password")
        self.agent_identifier = "python-agent"

        self.entry_public = MemoryEntry.objects.create(
            title="Alpha release plan",
            content="Alpha release plan and preparation notes.",
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            entry_type=MemoryEntry.TYPE_NOTE,
        )
        self.entry_confidential = MemoryEntry.objects.create(
            title="Beta launch feedback",
            content="Beta launch plan and key customer insights.",
            sensitivity=MemoryEntry.SENSITIVITY_CONFIDENTIAL,
            entry_type=MemoryEntry.TYPE_NOTE,
        )
        self.entry_secret = MemoryEntry.objects.create(
            title="Gamma incident post-mortem",
            content="Gamma incident plan for remediation.",
            sensitivity=MemoryEntry.SENSITIVITY_SECRET,
            entry_type=MemoryEntry.TYPE_EVENT,
        )

        Embedding.objects.create(
            memory_entry=self.entry_public,
            vector=[1.0, 0.0],
            model_name="unit-test",
            dimension=2,
        )
        Embedding.objects.create(
            memory_entry=self.entry_confidential,
            vector=[0.8, 0.1],
            model_name="unit-test",
            dimension=2,
        )
        Embedding.objects.create(
            memory_entry=self.entry_secret,
            vector=[0.0, 1.0],
            model_name="unit-test",
            dimension=2,
        )

        self.consent = Consent.objects.create(
            user=self.user,
            agent_identifier=self.agent_identifier,
            scopes=[
                SCOPE_MEMORY_SEARCH,
                SCOPE_MEMORY_READ,
                SCOPE_MEMORY_WRITE,
            ],
            sensitivity_levels=[
                MemoryEntry.SENSITIVITY_PUBLIC,
                MemoryEntry.SENSITIVITY_CONFIDENTIAL,
            ],
            status=Consent.STATUS_ACTIVE,
        )

    def _issue_token(self, *, scopes: list[str], consent: Consent | None = None, agent: str | None = None) -> str:
        token = AccessToken.for_user(self.user)
        token["sub"] = str(self.user.pk)
        token["agent_id"] = agent or self.agent_identifier
        token["scopes"] = scopes
        if consent is not None:
            token["consent_id"] = consent.pk
        return f"Bearer {str(token)}"

    def test_manifest_lists_expected_tools(self):
        tool_names = {tool["name"] for tool in MANIFEST["tools"]}
        expected = {
            "memory.search",
            "memory.get",
            "memory.upsert",
            "memory.delete",
            "consent.grant",
            "consent.revoke",
        }
        self.assertTrue(expected.issubset(tool_names))
        self.assertEqual(MANIFEST["auth"]["type"], "oauth2-bearer")

    def test_python_agent_memory_flow(self):
        bearer = self._issue_token(
            scopes=[SCOPE_MEMORY_SEARCH, SCOPE_MEMORY_READ, SCOPE_MEMORY_WRITE],
            consent=self.consent,
        )

        with patch("memory.services.query.HybridQueryService._encode_query", return_value=[1.0, 0.0]):
            search_response = execute_tool(
                "memory.search",
                bearer_token=bearer,
                payload={"query": "release plan", "limit": 5},
            )

        self.assertEqual(search_response["count"], 2)
        returned_ids = {result["id"] for result in search_response["results"]}
        self.assertIn(self.entry_public.id, returned_ids)
        self.assertIn(self.entry_confidential.id, returned_ids)
        self.assertNotIn(self.entry_secret.id, returned_ids)

        detail_response = execute_tool(
            "memory.get",
            bearer_token=bearer,
            payload={"entry_id": self.entry_public.id},
        )
        self.assertEqual(detail_response["entry"]["id"], self.entry_public.id)
        self.assertEqual(detail_response["entry"]["version"], self.entry_public.version)

        update_payload = {
            "entry": {
                "id": self.entry_confidential.id,
                "version": self.entry_confidential.version,
                "title": "Beta launch feedback (updated)",
            }
        }
        update_response = execute_tool(
            "memory.upsert",
            bearer_token=bearer,
            payload=update_payload,
        )
        self.assertEqual(update_response["entry_id"], self.entry_confidential.id)
        self.entry_confidential.refresh_from_db()
        self.assertEqual(self.entry_confidential.version, update_response["version"])
        self.assertEqual(self.entry_confidential.title, "Beta launch feedback (updated)")

        create_response = execute_tool(
            "memory.upsert",
            bearer_token=bearer,
            payload={
                "entry": {
                    "title": "Agent created note",
                    "content": "Created via MCP tool.",
                    "sensitivity": MemoryEntry.SENSITIVITY_PUBLIC,
                }
            },
        )
        created_id = create_response["entry_id"]
        self.assertTrue(MemoryEntry.objects.filter(pk=created_id).exists())

        delete_response = execute_tool(
            "memory.delete",
            bearer_token=bearer,
            payload={"entry_id": created_id, "version": create_response["version"]},
        )
        self.assertEqual(delete_response["ok"], True)
        self.assertFalse(MemoryEntry.objects.filter(pk=created_id).exists())

    def test_node_agent_consent_flow(self):
        bearer = self._issue_token(
            scopes=[CONSENT_MANAGE_SCOPE],
            consent=None,
        )
        node_payload = json.loads(
            json.dumps(
                {
                    "user_id": str(self.user.pk),
                    "agent_identifier": "node-agent",
                    "scopes": [SCOPE_MEMORY_READ, SCOPE_MEMORY_SEARCH],
                    "sensitivity_levels": [MemoryEntry.SENSITIVITY_PUBLIC],
                }
            )
        )
        grant_response = execute_tool(
            "consent.grant",
            bearer_token=bearer,
            payload=node_payload,
        )
        consent_id = grant_response["consent_id"]
        consent = Consent.objects.get(pk=consent_id)
        self.assertEqual(consent.status, Consent.STATUS_ACTIVE)
        self.assertEqual(consent.version, grant_response["version"])

        revoke_response = execute_tool(
            "consent.revoke",
            bearer_token=bearer,
            payload={"consent_id": consent_id},
        )
        consent.refresh_from_db()
        self.assertEqual(revoke_response["status"], Consent.STATUS_REVOKED)
        self.assertEqual(consent.status, Consent.STATUS_REVOKED)

    def test_missing_scope_denied(self):
        bearer = self._issue_token(scopes=[SCOPE_MEMORY_READ], consent=self.consent)
        with self.assertRaises(PermissionDenied):
            execute_tool(
                "memory.search",
                bearer_token=bearer,
                payload={"query": "release"},
            )
