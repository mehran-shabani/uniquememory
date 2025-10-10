from __future__ import annotations

from typing import Any, Dict, List

SERVER_LABEL = "uniquememory-mcp"
PROTOCOL_VERSION = "2024-05-01"


def _tool(name: str, input_schema: Dict[str, Any], output_schema: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": name,
        "input_schema": input_schema,
        "output_schema": output_schema,
    }


def build_manifest() -> Dict[str, Any]:
    tools: List[Dict[str, Any]] = [
        _tool(
            "memory.search",
            {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "user_id": {"type": "string"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "default": 10},
                },
            },
            {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "count": {"type": "integer"},
                    "results": {"type": "array", "items": {"type": "object"}},
                },
            },
        ),
        _tool(
            "memory.get",
            {
                "type": "object",
                "required": ["entry_id"],
                "properties": {
                    "entry_id": {"type": "integer"},
                },
            },
            {
                "type": "object",
                "properties": {
                    "entry": {"type": "object"},
                },
            },
        ),
        _tool(
            "memory.upsert",
            {
                "type": "object",
                "required": ["entry"],
                "properties": {
                    "entry": {"type": "object"},
                },
            },
            {
                "type": "object",
                "properties": {
                    "entry_id": {"type": "integer"},
                    "version": {"type": "integer"},
                },
            },
        ),
        _tool(
            "memory.delete",
            {
                "type": "object",
                "required": ["entry_id"],
                "properties": {
                    "entry_id": {"type": "integer"},
                    "version": {"type": "integer"},
                    "soft": {"type": "boolean", "default": False},
                },
            },
            {
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                },
            },
        ),
        _tool(
            "consent.grant",
            {
                "type": "object",
                "required": ["user_id", "agent_identifier", "scopes", "sensitivity_levels"],
                "properties": {
                    "user_id": {"type": "string"},
                    "agent_identifier": {"type": "string"},
                    "scopes": {"type": "array", "items": {"type": "string"}},
                    "sensitivity_levels": {"type": "array", "items": {"type": "string"}},
                },
            },
            {
                "type": "object",
                "properties": {
                    "consent_id": {"type": "integer"},
                    "version": {"type": "integer"},
                },
            },
        ),
        _tool(
            "consent.revoke",
            {
                "type": "object",
                "required": ["consent_id"],
                "properties": {
                    "consent_id": {"type": "integer"},
                },
            },
            {
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "status": {"type": "string"},
                },
            },
        ),
    ]

    return {
        "server_label": SERVER_LABEL,
        "protocol_version": PROTOCOL_VERSION,
        "tools": tools,
        "auth": {"type": "oauth2-bearer"},
    }


MANIFEST: Dict[str, Any] = build_manifest()

__all__ = ["MANIFEST", "build_manifest"]
