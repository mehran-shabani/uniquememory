from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Set

from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from consents.models import Consent
from policies.engine import PolicyEngine


@dataclass
class AuthContext:
    """Resolved information about the caller extracted from the bearer token."""

    subject: User
    agent_identifier: str
    consent: Optional[Consent]
    scopes: Set[str]


class BearerTokenValidator:
    """Validates OAuth2 bearer tokens against consent and policy rules."""

    def __init__(self, *, policy_engine: Optional[PolicyEngine] = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()

    def parse(
        self,
        token: str,
        *,
        required_scopes: Sequence[str] | None = None,
        require_consent: bool = True,
    ) -> AuthContext:
        if not token:
            raise PermissionDenied(_("Authorization token is required."))

        raw = token.strip()
        if raw.lower().startswith("bearer "):
            raw = raw[7:].strip()
        if not raw:
            raise PermissionDenied(_("Authorization token is required."))

        try:
            access_token = AccessToken(raw)
        except TokenError as exc:  # pragma: no cover - defensive guard
            raise PermissionDenied(_("Invalid access token.")) from exc

        subject_id = access_token.get("sub") or access_token.get("user_id")
        if not subject_id:
            raise PermissionDenied(_("Token is missing subject information."))

        agent_identifier = access_token.get("agent_id") or access_token.get("agent")
        if not agent_identifier:
            raise PermissionDenied(_("Token must include the agent identifier."))

        scopes_claim = access_token.get("scopes") or access_token.get("scope") or []
        scopes = self._normalize_scopes(scopes_claim)

        try:
            subject = User.objects.get(pk=subject_id)
        except User.DoesNotExist as exc:
            raise PermissionDenied(_("Subject specified in token does not exist.")) from exc

        consent: Optional[Consent]
        if require_consent:
            consent_id = access_token.get("consent_id")
            if consent_id is None:
                raise PermissionDenied(_("Token must reference an active consent."))
            try:
                consent = (
                    Consent.objects.active()
                    .filter(user=subject, agent_identifier=agent_identifier)
                    .get(pk=consent_id)
                )
            except Consent.DoesNotExist as exc:
                raise PermissionDenied(_("Referenced consent is not active.")) from exc
        else:
            consent = None

        required = set(required_scopes or [])
        if required and not required.issubset(scopes):
            raise PermissionDenied(_("Token does not grant the required scopes."))

        if require_consent and consent and not consent.allows_all_scopes(required):
            raise PermissionDenied(_("Consent does not include the required scopes."))

        return AuthContext(
            subject=subject,
            agent_identifier=str(agent_identifier),
            consent=consent,
            scopes=scopes,
        )

    def ensure_permissions(
        self,
        context: AuthContext,
        *,
        action: Optional[str],
        sensitivity: Optional[str] = None,
        sensitivities: Iterable[str] | None = None,
    ) -> None:
        if action is None:
            return

        consent = context.consent
        if consent is None:
            raise PermissionDenied(_("Consent is required for this action."))

        if sensitivities is not None:
            policy_context = self.policy_engine.enforce_multiple(
                subject=context.subject,
                agent_identifier=context.agent_identifier,
                action=action,
                sensitivities=sensitivities,
            )
        else:
            policy_context = self.policy_engine.enforce(
                subject=context.subject,
                agent_identifier=context.agent_identifier,
                action=action,
                sensitivity=sensitivity,
            )

        if policy_context.consent.pk != consent.pk:
            raise PermissionDenied(_("Token consent no longer matches the active policy."))

    def validate(
        self,
        token: str,
        *,
        action: Optional[str],
        required_scopes: Sequence[str] | None = None,
        sensitivity: Optional[str] = None,
        sensitivities: Iterable[str] | None = None,
        require_consent: bool = True,
    ) -> AuthContext:
        context = self.parse(
            token,
            required_scopes=required_scopes,
            require_consent=require_consent,
        )
        self.ensure_permissions(
            context,
            action=action,
            sensitivity=sensitivity,
            sensitivities=sensitivities,
        )
        return context

    @staticmethod
    def _normalize_scopes(value: object) -> Set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            return {scope for scope in value.split() if scope}
        if isinstance(value, Iterable):
            return {str(scope) for scope in value if str(scope)}
        return {str(value)}


__all__ = ["AuthContext", "BearerTokenValidator"]
