from __future__ import annotations

from typing import Dict

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max

from consents.models import Consent

from ..auth import BearerTokenValidator

CONSENT_MANAGE_SCOPE = "consent.manage"

validator = BearerTokenValidator()


def consent_grant(*, bearer_token: str, payload: Dict[str, object]) -> Dict[str, object]:
    user_id = payload.get("user_id")
    agent_identifier = payload.get("agent_identifier") or payload.get("agent_id")
    scopes = payload.get("scopes")
    sensitivity_levels = payload.get("sensitivity_levels") or payload.get("sensitivities")

    if not isinstance(user_id, str):
        raise PermissionDenied("user_id must be provided as a string.")
    if not isinstance(agent_identifier, str):
        raise PermissionDenied("agent_identifier must be provided as a string.")
    if not isinstance(scopes, list) or not scopes:
        raise PermissionDenied("At least one scope must be granted.")
    if not isinstance(sensitivity_levels, list) or not sensitivity_levels:
        raise PermissionDenied("At least one sensitivity level must be provided.")

    context = validator.parse(
        bearer_token,
        required_scopes=[CONSENT_MANAGE_SCOPE],
        require_consent=False,
    )

    if str(context.subject.pk) != user_id:
        raise PermissionDenied("Tokens may only grant consent for the authenticated user.")

    with transaction.atomic():
        latest_version = (
            Consent.objects.filter(user=context.subject, agent_identifier=agent_identifier).aggregate(max_version=Max("version"))
        )
        consent = Consent.objects.create(
            user=context.subject,
            agent_identifier=agent_identifier,
            scopes=list(scopes),
            sensitivity_levels=list(sensitivity_levels),
            version=(latest_version["max_version"] or 0) + 1,
            status=Consent.STATUS_PENDING,
        )
        consent.activate()

    return {"consent_id": consent.pk, "version": consent.version}


def consent_revoke(*, bearer_token: str, payload: Dict[str, object]) -> Dict[str, object]:
    consent_id = payload.get("consent_id")
    if not isinstance(consent_id, int):
        raise PermissionDenied("consent_id must be provided as an integer.")

    context = validator.parse(
        bearer_token,
        required_scopes=[CONSENT_MANAGE_SCOPE],
        require_consent=False,
    )

    try:
        consent = Consent.objects.get(pk=consent_id, user=context.subject)
    except Consent.DoesNotExist as exc:
        raise PermissionDenied("Consent not found for this user.") from exc

    consent.revoke()

    return {"ok": True, "status": consent.status}


__all__ = ["consent_grant", "consent_revoke", "CONSENT_MANAGE_SCOPE"]
