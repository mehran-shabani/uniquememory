from __future__ import annotations

import json
from typing import Any, Dict

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import (HttpRequest, HttpResponse, HttpResponseBadRequest,
                         JsonResponse)
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView, ListView

from accounts.models import User
from policies.engine import PolicyEngine

from .models import MemoryEntry


def _is_valid_choice(value: str, choices: tuple[tuple[str, str], ...] | list[tuple[str, str]]) -> bool:
    return value in {choice for choice, _ in choices}


def _parse_if_match(request: HttpRequest) -> int | None:
    header_value = request.headers.get("If-Match")
    if not header_value:
        return None
    header_value = header_value.strip().strip('"')
    try:
        return int(header_value)
    except (TypeError, ValueError):
        return None


policy_engine = PolicyEngine()


def _extract_subject(request: HttpRequest) -> User:
    subject_id = request.headers.get("X-Subject-ID")
    if not subject_id:
        raise PermissionDenied("Missing X-Subject-ID header.")
    return get_object_or_404(User, pk=subject_id)


def _extract_agent_identifier(request: HttpRequest) -> str:
    agent_identifier = request.headers.get("X-Agent-ID")
    if not agent_identifier:
        raise PermissionDenied("Missing X-Agent-ID header.")
    return agent_identifier


def _enforce_query_permissions(request: HttpRequest, queryset) -> None:
    subject = _extract_subject(request)
    agent_identifier = _extract_agent_identifier(request)
    sensitivities = queryset.values_list("sensitivity", flat=True).distinct()
    policy_engine.enforce_multiple(
        subject=subject,
        agent_identifier=agent_identifier,
        action="memory:list",
        sensitivities=sensitivities,
    )


def _permission_denied_response(exception: PermissionDenied) -> HttpResponse:
    return HttpResponse(str(exception), status=403)


class MemoryEntryListView(ListView):
    model = MemoryEntry
    template_name = "memory/entry_list.html"
    context_object_name = "entries"
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset()
        sensitivity = self.request.GET.get("sensitivity")
        entry_type = self.request.GET.get("entry_type")
        if sensitivity:
            queryset = queryset.filter(sensitivity=sensitivity)
        if entry_type:
            queryset = queryset.filter(entry_type=entry_type)
        return queryset

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["selected_sensitivity"] = self.request.GET.get("sensitivity", "")
        context["selected_entry_type"] = self.request.GET.get("entry_type", "")
        context["sensitivity_choices"] = MemoryEntry.SENSITIVITY_CHOICES
        context["type_choices"] = MemoryEntry.TYPE_CHOICES
        return context


class MemoryEntryDetailView(DetailView):
    model = MemoryEntry
    template_name = "memory/entry_detail.html"
    context_object_name = "entry"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        entry: MemoryEntry = self.object
        context["policies"] = entry.access_policies.order_by("name")
        context["chunks"] = entry.chunks.order_by("position")
        return context


class MemoryEntryCollectionApiView(View):
    """Provides read/write access to the collection of entries."""

    http_method_names = ["get", "post"]

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse | HttpResponse:
        sensitivity = request.GET.get("sensitivity")
        entry_type = request.GET.get("entry_type")
        queryset = MemoryEntry.objects.all().order_by("-updated_at", "title")
        if sensitivity:
            queryset = queryset.filter(sensitivity=sensitivity)
        if entry_type:
            queryset = queryset.filter(entry_type=entry_type)
        try:
            _enforce_query_permissions(request, queryset)
        except PermissionDenied as exc:
            return _permission_denied_response(exc)
        payload = [
            {
                "id": entry.pk,
                "title": entry.title,
                "sensitivity": entry.sensitivity,
                "entry_type": entry.entry_type,
                "version": entry.version,
                "updated_at": entry.updated_at,
            }
            for entry in queryset
        ]
        return JsonResponse({"count": len(payload), "results": payload})

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse | HttpResponse:
        try:
            data = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON payload.")

        required_fields = {"title", "content"}
        if not required_fields.issubset(data):
            return HttpResponseBadRequest("Missing required fields: title, content.")

        sensitivity = data.get("sensitivity", MemoryEntry.SENSITIVITY_PUBLIC)
        entry_type = data.get("entry_type", MemoryEntry.TYPE_NOTE)

        if sensitivity and not _is_valid_choice(sensitivity, MemoryEntry.SENSITIVITY_CHOICES):
            return HttpResponseBadRequest("Invalid sensitivity value.")
        if entry_type and not _is_valid_choice(entry_type, MemoryEntry.TYPE_CHOICES):
            return HttpResponseBadRequest("Invalid entry_type value.")

        try:
            subject = _extract_subject(request)
            agent_identifier = _extract_agent_identifier(request)
            policy_engine.enforce(
                subject=subject,
                agent_identifier=agent_identifier,
                action="memory:create",
                sensitivity=sensitivity,
            )
        except PermissionDenied as exc:
            return _permission_denied_response(exc)

        entry = MemoryEntry.objects.create(
            title=data["title"],
            content=data.get("content", ""),
            sensitivity=sensitivity,
            entry_type=entry_type,
        )
        response_data = {
            "id": entry.pk,
            "version": entry.version,
        }
        response = JsonResponse(response_data, status=201)
        response["ETag"] = f'"{entry.version}"'
        return response


class MemoryEntryDetailApiView(View):
    """Handles optimistic concurrency operations on single entries."""

    http_method_names = ["get", "put", "patch", "delete"]

    def get(self, request: HttpRequest, pk: int, *args, **kwargs) -> JsonResponse | HttpResponse:
        entry = get_object_or_404(MemoryEntry, pk=pk)
        try:
            subject = _extract_subject(request)
            agent_identifier = _extract_agent_identifier(request)
            policy_engine.enforce(
                subject=subject,
                agent_identifier=agent_identifier,
                action="memory:retrieve",
                sensitivity=entry.sensitivity,
            )
        except PermissionDenied as exc:
            return _permission_denied_response(exc)
        data = {
            "id": entry.pk,
            "title": entry.title,
            "content": entry.content,
            "sensitivity": entry.sensitivity,
            "entry_type": entry.entry_type,
            "version": entry.version,
            "updated_at": entry.updated_at,
        }
        response = JsonResponse(data)
        response["ETag"] = f'"{entry.version}"'
        return response

    def put(self, request: HttpRequest, pk: int, *args, **kwargs) -> HttpResponse:
        return self._update_entry(request, pk, full_update=True)

    def patch(self, request: HttpRequest, pk: int, *args, **kwargs) -> HttpResponse:
        return self._update_entry(request, pk, full_update=False)

    def delete(self, request: HttpRequest, pk: int, *args, **kwargs) -> HttpResponse:
        match_version = _parse_if_match(request)
        if match_version is None:
            return HttpResponse(_("Missing or invalid If-Match header."), status=428)

        with transaction.atomic():
            entry = get_object_or_404(MemoryEntry.objects.select_for_update(), pk=pk)
            try:
                subject = _extract_subject(request)
                agent_identifier = _extract_agent_identifier(request)
                policy_engine.enforce(
                    subject=subject,
                    agent_identifier=agent_identifier,
                    action="memory:delete",
                    sensitivity=entry.sensitivity,
                )
            except PermissionDenied as exc:
                return _permission_denied_response(exc)
            if entry.version != match_version:
                return HttpResponse(_("Version conflict."), status=412)
            entry.delete()
        return HttpResponse(status=204)

    def _update_entry(self, request: HttpRequest, pk: int, *, full_update: bool) -> HttpResponse:
        match_version = _parse_if_match(request)
        if match_version is None:
            return HttpResponse(_("Missing or invalid If-Match header."), status=428)

        try:
            data = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON payload.")

        allowed_fields = {"title", "content", "sensitivity", "entry_type"}
        if full_update and not allowed_fields.issubset(data.keys()):
            return HttpResponseBadRequest("Full update requires title, content, sensitivity and entry_type fields.")

        updates = {key: value for key, value in data.items() if key in allowed_fields}
        sensitivity = updates.get("sensitivity")
        entry_type = updates.get("entry_type")
        if sensitivity and not _is_valid_choice(sensitivity, MemoryEntry.SENSITIVITY_CHOICES):
            return HttpResponseBadRequest("Invalid sensitivity value.")
        if entry_type and not _is_valid_choice(entry_type, MemoryEntry.TYPE_CHOICES):
            return HttpResponseBadRequest("Invalid entry_type value.")

        with transaction.atomic():
            entry = get_object_or_404(MemoryEntry.objects.select_for_update(), pk=pk)
            try:
                subject = _extract_subject(request)
                agent_identifier = _extract_agent_identifier(request)
                policy_engine.enforce(
                    subject=subject,
                    agent_identifier=agent_identifier,
                    action="memory:update",
                    sensitivity=updates.get("sensitivity", entry.sensitivity),
                )
            except PermissionDenied as exc:
                return _permission_denied_response(exc)
            if entry.version != match_version:
                return HttpResponse(_("Version conflict."), status=412)

            for field, value in updates.items():
                setattr(entry, field, value)
            entry.version = match_version + 1
            update_fields = list(updates.keys()) + ["version", "updated_at"]
            entry.save(update_fields=update_fields)

        response = JsonResponse({"id": entry.pk, "version": entry.version})
        response["ETag"] = f'"{entry.version}"'
        return response
