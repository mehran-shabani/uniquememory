from __future__ import annotations

from typing import Any

from django.db.models import Max
from rest_framework import serializers

from consents.models import Consent, SCOPE_CHOICES
from memory.models import MemoryEntry


class ConsentSerializer(serializers.ModelSerializer):
    sensitivity_levels = serializers.ListField(child=serializers.ChoiceField(choices=MemoryEntry.SENSITIVITY_CHOICES))
    scopes = serializers.ListField(child=serializers.ChoiceField(choices=SCOPE_CHOICES))

    class Meta:
        model = Consent
        fields = [
            "id",
            "user",
            "agent_identifier",
            "scopes",
            "sensitivity_levels",
            "version",
            "status",
            "issued_at",
            "updated_at",
            "revoked_at",
        ]
        read_only_fields = ["id", "user", "version", "status", "issued_at", "updated_at", "revoked_at"]

    def create(self, validated_data: dict[str, Any]) -> Consent:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required to create consents.")

        agent_identifier = validated_data["agent_identifier"]
        latest_version = (
            Consent.objects.filter(user=user, agent_identifier=agent_identifier).aggregate(max_version=Max("version"))
        )
        validated_data["version"] = (latest_version["max_version"] or 0) + 1
        validated_data["user"] = user
        consent = super().create(validated_data)
        consent.activate()
        return consent

    def update(self, instance: Consent, validated_data: dict[str, Any]) -> Consent:
        if instance.status != Consent.STATUS_ACTIVE:
            raise serializers.ValidationError("Only active consents may be updated.")
        return super().update(instance, validated_data)
