from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from consents.models import Consent, SCOPE_MEMORY_READ, SCOPE_MEMORY_WRITE
from memory.models import MemoryEntry


@pytest.mark.django_db
class TestConsentModel:
    def setup_method(self) -> None:
        self.user = get_user_model().objects.create_user("owner@example.com", "password")
        self.agent_identifier = "agent-z"

    def _create_valid_consent(self, **overrides: Any) -> Consent:
        data: dict[str, Any] = {
            "user": self.user,
            "agent_identifier": self.agent_identifier,
            "scopes": [SCOPE_MEMORY_READ],
            "sensitivity_levels": [MemoryEntry.SENSITIVITY_PUBLIC],
            "status": Consent.STATUS_PENDING,
            "version": 1,
        }
        data.update(overrides)
        return Consent.objects.create(**data)

    def test_clean_enforces_validations(self):
        consent = Consent(
            user=self.user,
            agent_identifier=self.agent_identifier,
            scopes=[],
            sensitivity_levels=["invalid"],
        )
        with pytest.raises(ValidationError):
            consent.full_clean()

    def test_activate_and_revoke_transitions(self):
        consent = self._create_valid_consent()
        consent.activate()
        assert consent.status == Consent.STATUS_ACTIVE
        assert consent.revoked_at is None

        consent.revoke()
        consent.refresh_from_db()
        assert consent.status == Consent.STATUS_REVOKED
        assert consent.revoked_at is not None

    def test_unique_version_per_agent(self):
        self._create_valid_consent(version=1)
        with pytest.raises(ValidationError):
            self._create_valid_consent(version=1)

    def test_allows_scope_and_sensitivity_helpers(self):
        consent = self._create_valid_consent(
            scopes=[SCOPE_MEMORY_READ, SCOPE_MEMORY_WRITE],
            sensitivity_levels=[
                MemoryEntry.SENSITIVITY_PUBLIC,
                MemoryEntry.SENSITIVITY_CONFIDENTIAL,
            ],
        )
        assert consent.allows_scope(SCOPE_MEMORY_WRITE)
        assert consent.allows_sensitivity(MemoryEntry.SENSITIVITY_CONFIDENTIAL)
        assert consent.allows_all_scopes([SCOPE_MEMORY_READ])
        assert not consent.allows_all_scopes(["unknown"])
