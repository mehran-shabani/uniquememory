from django.contrib import admin

from .models import AccessPolicy


@admin.register(AccessPolicy)
class AccessPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "memory_entry", "access_level", "is_active")
    list_filter = ("access_level", "is_active")
    search_fields = ("name", "memory_entry__title")
    autocomplete_fields = ("memory_entry", "allowed_users")
