from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.core.exceptions import PermissionDenied

from consents.models import Consent, SCOPE_MEMORY_READ, SCOPE_MEMORY_SEARCH, SCOPE_MEMORY_WRITE
from memory.models import MemoryEntry


@dataclass
class PolicyContext:
    consent: Consent
    action: str
    sensitivity: Optional[str]


class PolicyEngine:
    """Evaluates ABAC rules using user consents before CRUD operations."""

    action_scope_map = {
        "memory:list": SCOPE_MEMORY_READ,
        "memory:retrieve": SCOPE_MEMORY_READ,
        "memory:create": SCOPE_MEMORY_WRITE,
        "memory:update": SCOPE_MEMORY_WRITE,
        "memory:delete": SCOPE_MEMORY_WRITE,
        "memory:query": SCOPE_MEMORY_SEARCH,
    }

    def _get_required_scope(self, action: str) -> Optional[str]:
        return self.action_scope_map.get(action)

    def enforce(
        self,
        *,
        subject,
        agent_identifier: str,
        action: str,
        sensitivity: Optional[str] = None,
    ) -> PolicyContext:
        consent = (
            Consent.objects.active()
            .filter(user=subject, agent_identifier=agent_identifier)
            .order_by("-version")
            .first()
        )
        if consent is None:
            raise PermissionDenied("Active consent is required for this operation.")

        scope = self._get_required_scope(action)
        if scope and not consent.allows_scope(scope):
            raise PermissionDenied("The provided consent does not cover the requested scope.")

        if sensitivity is not None:
            if sensitivity not in {choice for choice, _ in MemoryEntry.SENSITIVITY_CHOICES}:
                raise PermissionDenied("Unknown sensitivity level requested.")
            if not consent.allows_sensitivity(sensitivity):
                raise PermissionDenied("The requested sensitivity level is not permitted by this consent.")

        return PolicyContext(consent=consent, action=action, sensitivity=sensitivity)

    def enforce_multiple(
        self,
        *,
        subject,
        agent_identifier: str,
        action: str,
        sensitivities: Iterable[str],
    ) -> PolicyContext:
        highest_sensitivity = self._max_sensitivity(sensitivities)
        return self.enforce(subject=subject, agent_identifier=agent_identifier, action=action, sensitivity=highest_sensitivity)

    @staticmethod
    def _max_sensitivity(sensitivities: Iterable[str]) -> Optional[str]:
        order = {value: index for index, (value, _) in enumerate(MemoryEntry.SENSITIVITY_CHOICES)}
        ranked = [order.get(sensitivity) for sensitivity in sensitivities if sensitivity in order]
        if not ranked:
            return None
        max_rank = max(ranked)
        inverse = {index: value for value, index in order.items()}
        return inverse[max_rank]
