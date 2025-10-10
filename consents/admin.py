from django.contrib import admin

from .models import Consent


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):
    list_display = ("user", "agent_identifier", "status", "version", "issued_at", "revoked_at")
    list_filter = ("status", "agent_identifier")
    search_fields = ("user__email", "agent_identifier")
    ordering = ("-updated_at",)
