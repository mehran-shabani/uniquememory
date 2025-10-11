from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from rest_framework_simplejwt.tokens import AccessToken

from consents.models import Consent, SCOPE_MEMORY_READ, SCOPE_MEMORY_WRITE
from memory.models import MemoryEntry
from mcp.auth import BearerTokenValidator


@pytest.mark.django_db
class TestBearerTokenValidator:
    def setup_method(self) -> None:
        self.validator = BearerTokenValidator()
        self.user = get_user_model().objects.create_user("caller@example.com", "password")
        self.agent_identifier = "agent-123"
        self.consent = Consent.objects.create(
            user=self.user,
            agent_identifier=self.agent_identifier,
            scopes=[SCOPE_MEMORY_READ, SCOPE_MEMORY_WRITE],
            sensitivity_levels=[MemoryEntry.SENSITIVITY_PUBLIC],
            status=Consent.STATUS_ACTIVE,
        )

    def _build_token(self) -> AccessToken:
        token = AccessToken.for_user(self.user)
        token["agent_id"] = self.agent_identifier
        token["consent_id"] = self.consent.pk
        token["scopes"] = [SCOPE_MEMORY_READ, SCOPE_MEMORY_WRITE]
        return token

    def test_validate_returns_context(self):
        token = self._build_token()
        context = self.validator.validate(
            str(token),
            action="memory:retrieve",
            required_scopes=[SCOPE_MEMORY_READ],
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
        )
        assert context.subject == self.user
        assert context.consent.pk == self.consent.pk

    def test_parse_requires_consent_reference(self):
        token = AccessToken.for_user(self.user)
        token["agent_id"] = self.agent_identifier
        token["scopes"] = [SCOPE_MEMORY_READ]
        with pytest.raises(PermissionDenied):
            self.validator.parse(str(token))

    def test_validate_requires_scopes(self):
        token = self._build_token()
        token["scopes"] = []
        with pytest.raises(PermissionDenied):
            self.validator.validate(
                str(token),
                action="memory:retrieve",
                required_scopes=[SCOPE_MEMORY_READ],
                sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            )

    def test_policy_enforcement_checks_sensitivity(self):
        token = self._build_token()
        with pytest.raises(PermissionDenied):
            self.validator.validate(
                str(token),
                action="memory:update",
                required_scopes=[SCOPE_MEMORY_WRITE],
                sensitivity=MemoryEntry.SENSITIVITY_SECRET,
            )

    def test_ensure_permissions_requires_consent_when_action_set(self):
        token = self._build_token()
        context = self.validator.parse(
            str(token),
            required_scopes=[SCOPE_MEMORY_READ],
            require_consent=False,
        )
        with pytest.raises(PermissionDenied):
            self.validator.ensure_permissions(context, action="memory:retrieve")
