from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from django.http import HttpRequest, HttpResponse


_current_user: ContextVar[Optional[object]] = ContextVar("audit_current_user", default=None)


def set_current_user(user: Optional[object]):
    return _current_user.set(user)


def reset_current_user(token) -> None:
    if token is not None:
        _current_user.reset(token)


def get_current_user() -> Optional[object]:
    return _current_user.get()


class AuditMiddleware:
    """Stores the current user so that signal handlers can access it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = request.user if hasattr(request, "user") and request.user.is_authenticated else None
        token = set_current_user(user)
        try:
            response = self.get_response(request)
        finally:
            reset_current_user(token)
        return response
