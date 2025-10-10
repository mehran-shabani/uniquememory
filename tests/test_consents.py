from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from companies.models import ApiKey, Company
from consents.models import Consent
from memory.models import MemoryEntry


class ConsentPolicyTests(TestCase):
    def setUp(self) -> None:
        self.subject = User.objects.create_user("subject@example.com", "password")
        self.agent_identifier = "agent-alpha"
        self.entry = MemoryEntry.objects.create(
            title="Sample Entry",
            content="Sensitive content",
            sensitivity=MemoryEntry.SENSITIVITY_CONFIDENTIAL,
            entry_type=MemoryEntry.TYPE_NOTE,
        )
        self.collection_url = reverse("memory:entry-collection-api")
        self.api_client = APIClient()
        self.access_token = str(RefreshToken.for_user(self.subject).access_token)
        self.company = Company.objects.create(name="Acme", slug="acme")
        self.api_key = ApiKey.objects.create(company=self.company, name="Test key")

    def test_memory_access_requires_active_consent(self):
        response = self.client.get(
            self.collection_url,
            HTTP_X_SUBJECT_ID=str(self.subject.pk),
            HTTP_X_AGENT_ID=self.agent_identifier,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Consent.objects.count(), 0)

    def test_grant_consent_allows_access(self):
        self.api_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self.access_token}",
            HTTP_X_API_KEY=self.api_key.key,
        )
        payload = {
            "agent_identifier": self.agent_identifier,
            "scopes": ["memory.read", "memory.write"],
            "sensitivity_levels": [MemoryEntry.SENSITIVITY_PUBLIC, MemoryEntry.SENSITIVITY_CONFIDENTIAL],
        }
        response = self.api_client.post(reverse("consent-list"), data=payload, format="json")
        self.assertEqual(response.status_code, 201)
        consent_id = response.json()["id"]

        allowed = self.client.get(
            self.collection_url,
            HTTP_X_SUBJECT_ID=str(self.subject.pk),
            HTTP_X_AGENT_ID=self.agent_identifier,
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()["count"], 1)

        revoke = self.api_client.post(reverse("consent-revoke", args=[consent_id]))
        self.assertEqual(revoke.status_code, 200)

        denied = self.client.get(
            self.collection_url,
            HTTP_X_SUBJECT_ID=str(self.subject.pk),
            HTTP_X_AGENT_ID=self.agent_identifier,
        )
        self.assertEqual(denied.status_code, 403)
