from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from consents.models import Consent
from security.dlp import sanitize_output, sanitize_text

from .forms import ConsentGrantForm, ConsentRevokeForm


class ConsentManagementView(LoginRequiredMixin, TemplateView):
    template_name = "portal/consent_management.html"
    login_url = reverse_lazy("admin:login")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        consents = Consent.objects.filter(user=self.request.user).order_by("-updated_at")
        context.update(
            {
                "consents": consents,
                "grant_form": kwargs.get("grant_form") or ConsentGrantForm(),
            }
        )
        return sanitize_output(context)

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if "consent_id" in request.POST:
            form = ConsentRevokeForm(request.POST, user=request.user)
            if form.is_valid():
                consent = form.save(user=request.user)
                messages.success(
                    request,
                    sanitize_text(f"Consent for {consent.agent_identifier} revoked."),
                )
            else:
                messages.error(
                    request,
                    sanitize_text("Unable to revoke consent. Please try again."),
                )
            return redirect("portal:consents")

        form = ConsentGrantForm(request.POST)
        if form.is_valid():
            consent = form.save(user=request.user)
            messages.success(
                request,
                sanitize_text(f"Consent for {consent.agent_identifier} granted."),
            )
            return redirect("portal:consents")

        messages.error(request, sanitize_text("Please correct the errors below."))
        context = self.get_context_data(grant_form=form)
        return self.render_to_response(context)
