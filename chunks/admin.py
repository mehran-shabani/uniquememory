from django.contrib import admin

from .models import EntryChunk


@admin.register(EntryChunk)
class EntryChunkAdmin(admin.ModelAdmin):
    list_display = ("memory_entry", "position", "updated_at")
    list_filter = ("memory_entry",)
    search_fields = ("memory_entry__title", "content")
    autocomplete_fields = ("memory_entry",)
