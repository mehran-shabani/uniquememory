from __future__ import annotations

from django.contrib import admin

from .models import GraphEdge, GraphNode


@admin.register(GraphNode)
class GraphNodeAdmin(admin.ModelAdmin):
    list_display = ("node_type", "reference_id", "created_at", "updated_at")
    search_fields = ("node_type", "reference_id")
    list_filter = ("node_type",)


@admin.register(GraphEdge)
class GraphEdgeAdmin(admin.ModelAdmin):
    list_display = ("relation_type", "source", "target", "weight")
    list_filter = ("relation_type",)
    search_fields = ("relation_type", "source__reference_id", "target__reference_id")
