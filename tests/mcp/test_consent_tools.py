from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from consents.models import Consent
from mcp.tools.consent import CONSENT_MANAGE_SCOPE, consent_grant, consent_revoke


class ConsentToolTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("granter@example.com", "password")
        self.agent_identifier = "consent-manager"
        self.token = self._build_token()

    def _build_token(self) -> str:
        token = AccessToken.for_user(self.user)
        token["sub"] = str(self.user.pk)
        token["agent_id"] = self.agent_identifier
        token["scopes"] = [CONSENT_MANAGE_SCOPE]
        return str(token)

    def test_consent_grant_validates_required_fields(self) -> None:
        with self.assertRaises(PermissionDenied):
            consent_grant(bearer_token=self.token, payload={})
        with self.assertRaises(PermissionDenied):
            consent_grant(
                bearer_token=self.token,
                payload={
                    "user_id": str(self.user.pk),
                    "agent_identifier": 123,
                    "scopes": ["memory.read"],
                    "sensitivity_levels": ["public"],
                },
            )
        with self.assertRaises(PermissionDenied):
            consent_grant(
                bearer_token=self.token,
                payload={
                    "user_id": str(self.user.pk),
                    "agent_identifier": self.agent_identifier,
                    "scopes": [],
                    "sensitivity_levels": ["public"],
                },
            )
        with self.assertRaises(PermissionDenied):
            consent_grant(
                bearer_token=self.token,
                payload={
                    "user_id": str(self.user.pk),
                    "agent_identifier": self.agent_identifier,
                    "scopes": ["memory.read"],
                    "sensitivity_levels": "public",
                },
            )

    def test_consent_grant_rejects_mismatched_subject(self) -> None:
        with self.assertRaises(PermissionDenied):
            consent_grant(
                bearer_token=self.token,
                payload={
                    "user_id": "00000000-0000-0000-0000-000000000000",
                    "agent_identifier": self.agent_identifier,
                    "scopes": ["memory.read"],
                    "sensitivity_levels": ["public"],
                },
            )

    def test_consent_grant_creates_next_version(self) -> None:
        existing = Consent.objects.create(
            user=self.user,
            agent_identifier=self.agent_identifier,
            scopes=["memory.read"],
            sensitivity_levels=["public"],
            version=3,
            status=Consent.STATUS_ACTIVE,
        )
        payload = {
            "user_id": str(self.user.pk),
            "agent_identifier": self.agent_identifier,
            "scopes": ["memory.read"],
            "sensitivity_levels": ["public"],
        }

        result = consent_grant(bearer_token=self.token, payload=payload)

        self.assertIn("consent_id", result)
        self.assertEqual(result["version"], existing.version + 1)
        new_consent = Consent.objects.get(pk=result["consent_id"])
        self.assertEqual(new_consent.status, Consent.STATUS_ACTIVE)

    def test_consent_revoke_validates_arguments(self) -> None:
        with self.assertRaises(PermissionDenied):
            consent_revoke(bearer_token=self.token, payload={})
        with self.assertRaises(PermissionDenied):
            consent_revoke(bearer_token=self.token, payload={"consent_id": "abc"})

    def test_consent_revoke_requires_matching_consent(self) -> None:
        with self.assertRaises(PermissionDenied):
            consent_revoke(bearer_token=self.token, payload={"consent_id": 9999})

    def test_consent_revoke_sets_status(self) -> None:
        consent = Consent.objects.create(
            user=self.user,
            agent_identifier=self.agent_identifier,
            scopes=["memory.read"],
            sensitivity_levels=["public"],
            status=Consent.STATUS_ACTIVE,
        )

        result = consent_revoke(bearer_token=self.token, payload={"consent_id": consent.pk})

        consent.refresh_from_db()
        self.assertTrue(result["ok"])
        self.assertEqual(consent.status, Consent.STATUS_REVOKED)
