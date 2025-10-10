from django.contrib import admin

from .models import ApiKey, Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "is_active", "rate_limit", "rate_limit_window", "last_used_at")
    list_filter = ("is_active", "company")
    search_fields = ("name", "key", "company__name")
    readonly_fields = ("key", "created_at", "last_used_at")
    ordering = ("company", "name")
