from __future__ import annotations

from typing import Any, Callable, Dict

from django.core.exceptions import PermissionDenied

from .consent import consent_grant, consent_revoke
from .memory import memory_delete, memory_get, memory_search, memory_upsert

ToolHandler = Callable[..., Dict[str, Any]]

TOOL_HANDLERS: Dict[str, ToolHandler] = {
    "memory.search": memory_search,
    "memory.get": memory_get,
    "memory.upsert": memory_upsert,
    "memory.delete": memory_delete,
    "consent.grant": consent_grant,
    "consent.revoke": consent_revoke,
}


def execute_tool(name: str, *, bearer_token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        handler = TOOL_HANDLERS[name]
    except KeyError as exc:
        raise PermissionDenied(f"Unknown tool: {name}") from exc
    if not isinstance(payload, dict):
        raise PermissionDenied("Tool payload must be a JSON object.")
    return handler(bearer_token=bearer_token, payload=payload)


__all__ = ["TOOL_HANDLERS", "execute_tool"]
