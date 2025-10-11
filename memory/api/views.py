from __future__ import annotations

import json
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404
from django.views import View

from accounts.models import User
from memory.services.query import HybridQueryService
from policies.engine import PolicyEngine
from security.dlp import sanitize_output, sanitize_text


class MemoryQueryView(View):
    """Handle hybrid retrieval queries for a given user."""

    http_method_names = ["post"]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.service = HybridQueryService()
        self.policy_engine = PolicyEngine()

    def post(self, request: HttpRequest, user_id: str, *args: Any, **kwargs: Any) -> JsonResponse:
        user = get_object_or_404(User, pk=user_id)
        try:
            payload = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return HttpResponseBadRequest(sanitize_text("Invalid JSON payload."))

        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            return HttpResponseBadRequest(sanitize_text("Query text is required."))

        limit = payload.get("limit", 10)
        if not isinstance(limit, int) or limit <= 0:
            return HttpResponseBadRequest(
                sanitize_text("Limit must be a positive integer.")
            )

        agent_identifier = request.headers.get("X-Agent-ID")
        if not agent_identifier:
            return HttpResponse(sanitize_text("Missing X-Agent-ID header."), status=403)
        try:
            self.policy_engine.enforce(
                subject=user,
                agent_identifier=agent_identifier,
                action="memory:query",
            )
        except PermissionDenied as exc:
            return HttpResponse(sanitize_text(str(exc)), status=403)

        results = self.service.search(user_id=str(user.pk), query=query, limit=limit)
        response_payload = sanitize_output(
            {
                "user_id": str(user.pk),
                "count": len(results),
                "results": [result.to_dict() for result in results],
            }
        )
        return JsonResponse(response_payload)
