from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from consents.models import Consent, SCOPE_MEMORY_READ
from memory.models import MemoryEntry


class GraphRelatedBenchmarkTests(TestCase):
    """A simple benchmark to validate graph-based re-ranking quality."""

    def setUp(self) -> None:
        self.user = User.objects.create_user("bob@example.com", "password")
        self.entry_public = MemoryEntry.objects.create(
            title="Public roadmap",
            content="Key milestones for the next quarter.",
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            entry_type=MemoryEntry.TYPE_NOTE,
        )
        self.entry_secret = MemoryEntry.objects.create(
            title="Secret incident postmortem",
            content="Contains sensitive operational details.",
            sensitivity=MemoryEntry.SENSITIVITY_SECRET,
            entry_type=MemoryEntry.TYPE_EVENT,
        )
        Consent.objects.create(
            user=self.user,
            agent_identifier="benchmark-agent",
            scopes=[SCOPE_MEMORY_READ],
            sensitivity_levels=[MemoryEntry.SENSITIVITY_PUBLIC],
            status=Consent.STATUS_ACTIVE,
        )
        self.url = reverse("graph-related")

    def test_related_results_prefer_granted_sensitivity(self) -> None:
        response = self.client.get(
            self.url,
            data={
                "node_type": "user",
                "reference_id": str(self.user.pk),
                "candidate": [
                    str(self.entry_public.pk),
                    str(self.entry_secret.pk),
                ],
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 2
        scores = {result["reference_id"]: result["score"] for result in payload["results"]}
        public_score = scores.get(str(self.entry_public.pk), 0.0)
        secret_score = scores.get(str(self.entry_secret.pk), 0.0)
        assert public_score > secret_score
        # Simple benchmark: ensure the preferred entry has a meaningful score.
        assert public_score >= 0.05
