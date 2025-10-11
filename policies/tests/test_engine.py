from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model

from consents.models import Consent, SCOPE_MEMORY_READ, SCOPE_MEMORY_SEARCH, SCOPE_MEMORY_WRITE
from memory.models import MemoryEntry
from policies.engine import PolicyEngine


@pytest.mark.django_db
class TestPolicyEngine:
    def setup_method(self) -> None:
        self.engine = PolicyEngine()
        self.user = get_user_model().objects.create_user("user@example.com", "password")
        self.agent_identifier = "agent-1"
        self.consent = Consent.objects.create(
            user=self.user,
            agent_identifier=self.agent_identifier,
            scopes=[SCOPE_MEMORY_READ, SCOPE_MEMORY_WRITE, SCOPE_MEMORY_SEARCH],
            sensitivity_levels=[
                MemoryEntry.SENSITIVITY_PUBLIC,
                MemoryEntry.SENSITIVITY_CONFIDENTIAL,
            ],
            status=Consent.STATUS_ACTIVE,
        )

    def test_requires_active_consent(self):
        self.consent.status = Consent.STATUS_REVOKED
        self.consent.save(update_fields=["status"])
        with pytest.raises(PermissionDenied):
            self.engine.enforce(
                subject=self.user,
                agent_identifier=self.agent_identifier,
                action="memory:retrieve",
            )

    def test_enforce_blocks_unknown_sensitivity(self):
        with pytest.raises(PermissionDenied):
            self.engine.enforce(
                subject=self.user,
                agent_identifier=self.agent_identifier,
                action="memory:create",
                sensitivity="top-secret",
            )

    def test_enforce_checks_scope_and_sensitivity(self):
        with pytest.raises(PermissionDenied):
            self.engine.enforce(
                subject=self.user,
                agent_identifier=self.agent_identifier,
                action="memory:delete",
                sensitivity=MemoryEntry.SENSITIVITY_SECRET,
            )

        context = self.engine.enforce(
            subject=self.user,
            agent_identifier=self.agent_identifier,
            action="memory:retrieve",
            sensitivity=MemoryEntry.SENSITIVITY_CONFIDENTIAL,
        )
        assert context.consent.pk == self.consent.pk

    def test_enforce_multiple_uses_highest_sensitivity(self):
        context = self.engine.enforce_multiple(
            subject=self.user,
            agent_identifier=self.agent_identifier,
            action="memory:query",
            sensitivities=[
                MemoryEntry.SENSITIVITY_PUBLIC,
                MemoryEntry.SENSITIVITY_CONFIDENTIAL,
            ],
        )
        assert context.sensitivity == MemoryEntry.SENSITIVITY_CONFIDENTIAL

        with pytest.raises(PermissionDenied):
            self.engine.enforce_multiple(
                subject=self.user,
                agent_identifier=self.agent_identifier,
                action="memory:query",
                sensitivities=[MemoryEntry.SENSITIVITY_SECRET],
            )
