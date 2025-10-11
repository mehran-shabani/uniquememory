from __future__ import annotations

from unittest import mock

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from consents.models import Consent, SCOPE_MEMORY_WRITE
from memory.models import MemoryEntry
from mcp.tools import memory as memory_tools
from mcp.tools.memory import memory_upsert


class MemoryUpsertTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("upserter@example.com", "password")
        self.agent_identifier = "memory-upserter"
        self.consent = Consent.objects.create(
            user=self.user,
            agent_identifier=self.agent_identifier,
            scopes=[SCOPE_MEMORY_WRITE],
            sensitivity_levels=[
                MemoryEntry.SENSITIVITY_PUBLIC,
                MemoryEntry.SENSITIVITY_CONFIDENTIAL,
                MemoryEntry.SENSITIVITY_SECRET,
            ],
            status=Consent.STATUS_ACTIVE,
        )
        self.access_token = self._build_token()

    def _build_token(self) -> str:
        token = AccessToken.for_user(self.user)
        token["sub"] = str(self.user.pk)
        token["agent_id"] = self.agent_identifier
        token["scopes"] = [SCOPE_MEMORY_WRITE]
        token["consent_id"] = self.consent.pk
        return str(token)

    def test_memory_upsert_requires_dict_payload(self) -> None:
        with self.assertRaises(PermissionDenied):
            memory_upsert(bearer_token=self.access_token, payload=["not", "a", "dict"])

    def test_memory_upsert_creates_entry(self) -> None:
        payload = {
            "entry": {
                "title": "Launch checklist",
                "content": "Review deployment steps before launch.",
                "sensitivity": MemoryEntry.SENSITIVITY_CONFIDENTIAL,
            }
        }

        result = memory_upsert(bearer_token=self.access_token, payload=payload)

        self.assertIn("entry_id", result)
        self.assertIn("version", result)
        entry = MemoryEntry.objects.get(pk=result["entry_id"])
        self.assertEqual(entry.title, "Launch checklist")
        self.assertEqual(entry.version, 1)
        self.assertEqual(entry.sensitivity, MemoryEntry.SENSITIVITY_CONFIDENTIAL)

    def test_memory_upsert_updates_entry_with_matching_version(self) -> None:
        entry = MemoryEntry.objects.create(
            title="Existing note",
            content="Original content",
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            entry_type=MemoryEntry.TYPE_NOTE,
        )

        payload = {
            "entry": {
                "entry_id": entry.pk,
                "version": entry.version,
                "title": "Existing note",
                "content": "Updated content",
            }
        }

        result = memory_upsert(bearer_token=self.access_token, payload=payload)

        entry.refresh_from_db()
        self.assertEqual(result["entry_id"], entry.pk)
        self.assertEqual(result["version"], entry.version)
        self.assertEqual(entry.content, "Updated content")

    def test_memory_upsert_rejects_version_conflict(self) -> None:
        entry = MemoryEntry.objects.create(
            title="Versioned entry",
            content="First version",
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            entry_type=MemoryEntry.TYPE_NOTE,
        )

        payload = {
            "entry": {
                "entry_id": entry.pk,
                "version": entry.version + 1,
                "content": "Attempting stale update",
            }
        }

        with self.assertRaises(PermissionDenied):
            memory_upsert(bearer_token=self.access_token, payload=payload)

    def test_memory_upsert_rejects_invalid_string_fields(self) -> None:
        payload = {
            "entry": {
                "title": 123,
                "content": "Body",
            }
        }

        with self.assertRaises(PermissionDenied):
            memory_upsert(bearer_token=self.access_token, payload=payload)

    def test_memory_upsert_rejects_non_string_updates(self) -> None:
        entry = MemoryEntry.objects.create(
            title="Structured note",
            content="Valid content",
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            entry_type=MemoryEntry.TYPE_NOTE,
        )

        payload = {
            "entry": {
                "entry_id": entry.pk,
                "version": entry.version,
                "content": 42,
            }
        }

        with self.assertRaises(PermissionDenied):
            memory_upsert(bearer_token=self.access_token, payload=payload)

    def test_memory_upsert_validates_sensitivity_fields(self) -> None:
        with self.assertRaises(PermissionDenied):
            memory_upsert(
                bearer_token=self.access_token,
                payload={"entry": {"title": "Bad", "content": "bad", "sensitivity": 123}},
            )

        with self.assertRaises(PermissionDenied):
            memory_upsert(
                bearer_token=self.access_token,
                payload={
                    "entry": {
                        "title": "Bad",
                        "content": "bad",
                        "sensitivity": "unknown",
                    }
                },
            )

    def test_memory_upsert_validates_entry_type_fields(self) -> None:
        with self.assertRaises(PermissionDenied):
            memory_upsert(
                bearer_token=self.access_token,
                payload={"entry": {"title": "Bad", "content": "bad", "entry_type": 42}},
            )

        with self.assertRaises(PermissionDenied):
            memory_upsert(
                bearer_token=self.access_token,
                payload={
                    "entry": {
                        "title": "Bad",
                        "content": "bad",
                        "entry_type": "invalid",
                    }
                },
            )

    def test_memory_upsert_requires_integer_entry_id(self) -> None:
        payload = {"entry": {"entry_id": "abc", "title": "Bad", "content": "bad"}}
        with self.assertRaises(PermissionDenied):
            memory_upsert(bearer_token=self.access_token, payload=payload)

    def test_memory_upsert_requires_version_on_update(self) -> None:
        entry = MemoryEntry.objects.create(title="Doc", content="body")
        payload = {"entry": {"entry_id": entry.pk}}
        with self.assertRaises(PermissionDenied):
            memory_upsert(bearer_token=self.access_token, payload=payload)

    def test_memory_upsert_handles_missing_entry(self) -> None:
        payload = {"entry": {"entry_id": 9999, "version": 1}}
        with self.assertRaises(PermissionDenied):
            memory_upsert(bearer_token=self.access_token, payload=payload)

    def test_memory_upsert_checks_permissions_when_sensitivity_changes(self) -> None:
        entry = MemoryEntry.objects.create(
            title="Existing note",
            content="Content",
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            entry_type=MemoryEntry.TYPE_NOTE,
        )

        payload = {
            "entry": {
                "entry_id": entry.pk,
                "version": entry.version,
                "content": "Updated",
                "sensitivity": MemoryEntry.SENSITIVITY_CONFIDENTIAL,
            }
        }

        with mock.patch.object(memory_tools.validator, "ensure_permissions", wraps=memory_tools.validator.ensure_permissions) as ensure:
            result = memory_upsert(bearer_token=self.access_token, payload=payload)

        entry.refresh_from_db()
        self.assertEqual(result["version"], entry.version)
        self.assertGreaterEqual(ensure.call_count, 2)

    def test_memory_upsert_rejects_invalid_sensitivity_updates(self) -> None:
        entry = MemoryEntry.objects.create(
            title="Existing note",
            content="Content",
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            entry_type=MemoryEntry.TYPE_NOTE,
        )

        payload = {
            "entry": {
                "entry_id": entry.pk,
                "version": entry.version,
                "sensitivity": None,
            }
        }

        with self.assertRaises(PermissionDenied):
            memory_upsert(bearer_token=self.access_token, payload=payload)

    def test_memory_upsert_rejects_invalid_entry_type_updates(self) -> None:
        entry = MemoryEntry.objects.create(
            title="Existing note",
            content="Content",
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            entry_type=MemoryEntry.TYPE_NOTE,
        )

        payload = {
            "entry": {
                "entry_id": entry.pk,
                "version": entry.version,
                "entry_type": None,
            }
        }

        with self.assertRaises(PermissionDenied):
            memory_upsert(bearer_token=self.access_token, payload=payload)
