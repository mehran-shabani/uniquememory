from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from companies.models import ApiKey


class ApiGatewayMiddleware(MiddlewareMixin):
    """Simple middleware to enforce API key presence and rate limiting."""

    header_name = "HTTP_X_API_KEY"
    exempt_paths: Iterable[str] = (
        "/api/token/",
        "/api/token/refresh/",
    )

    def process_request(self, request: HttpRequest) -> HttpResponse | None:
        if not request.path.startswith("/api/"):
            return None

        if request.path in self.exempt_paths:
            return None

        api_key_value = request.META.get(self.header_name)
        if not api_key_value:
            return JsonResponse({"detail": "API key required."}, status=401)

        try:
            api_key = ApiKey.objects.select_related("company").get(key=api_key_value, is_active=True)
        except ApiKey.DoesNotExist:
            return JsonResponse({"detail": "Invalid API key."}, status=401)

        limit = api_key.rate_limit
        window = api_key.rate_limit_window

        if limit:
            cache_key = f"api-key:{api_key.pk}:window"
            state = cache.get(cache_key)
            now = timezone.now()

            if not state or state["reset_at"] <= now:
                state = {"count": 0, "reset_at": now + timedelta(seconds=window)}

            if state["count"] >= limit:
                retry_after = max(1, int((state["reset_at"] - now).total_seconds()))
                response = JsonResponse({"detail": "Rate limit exceeded."}, status=429)
                response["Retry-After"] = str(retry_after)
                return response

            state["count"] += 1
            cache_timeout = max(1, int((state["reset_at"] - now).total_seconds()))
            cache.set(cache_key, state, cache_timeout)

        request.api_key = api_key
        api_key.touch(commit=True)
        return None
