from __future__ import annotations

from django import forms

from consents.models import Consent, SCOPE_CHOICES
from memory.models import MemoryEntry


class ConsentGrantForm(forms.Form):
    agent_identifier = forms.CharField(label="Agent identifier", max_length=255)
    scopes = forms.MultipleChoiceField(
        label="Scopes",
        required=True,
        choices=SCOPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    sensitivity_levels = forms.MultipleChoiceField(
        label="Sensitivity levels",
        required=True,
        choices=MemoryEntry.SENSITIVITY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )

    def save(self, *, user) -> Consent:
        consent = Consent(
            user=user,
            agent_identifier=self.cleaned_data["agent_identifier"],
            scopes=self.cleaned_data["scopes"],
            sensitivity_levels=self.cleaned_data["sensitivity_levels"],
        )
        consent.version = (
            Consent.objects.filter(user=user, agent_identifier=consent.agent_identifier)
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
            or 0
        ) + 1
        consent.status = Consent.STATUS_ACTIVE
        consent.save()
        return consent


class ConsentRevokeForm(forms.Form):
    consent_id = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        consent_id = cleaned_data.get("consent_id")
        if consent_id and self.user:
            exists = Consent.objects.filter(pk=consent_id, user=self.user).exists()
            if not exists:
                raise forms.ValidationError("Consent not found.")
        return cleaned_data

    def save(self, *, user) -> Consent:
        consent = Consent.objects.get(pk=self.cleaned_data["consent_id"], user=user)
        consent.revoke()
        return consent
