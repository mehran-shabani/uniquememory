from django.contrib import admin

from .models import MemoryEntry


@admin.register(MemoryEntry)
class MemoryEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "sensitivity", "entry_type", "version", "updated_at")
    list_filter = ("sensitivity", "entry_type")
    search_fields = ("title", "content")
    readonly_fields = ("created_at", "updated_at", "version")
