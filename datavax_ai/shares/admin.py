from django.contrib import admin
from unfold.admin import ModelAdmin

from shares.models import Like, Report, Share


@admin.register(Share)
class ShareAdmin(ModelAdmin):
    list_display = (
        "hash_id",
        "title",
        "user",
        "is_anonymous",
        "views_count",
        "downloads_count",
        "expire_date",
        "created_at",
    )
    list_filter = ("is_anonymous",)
    search_fields = ("hash_id", "title", "user__username")
    readonly_fields = ("hash_id", "views_count", "downloads_count", "created_at")


@admin.register(Like)
class LikeAdmin(ModelAdmin):
    list_display = ("share", "user", "created_at")
    search_fields = ("share__hash_id", "user__username")


@admin.register(Report)
class ReportAdmin(ModelAdmin):
    list_display = ("share", "reason", "reporter", "is_resolved", "created_at")
    list_filter = ("reason", "is_resolved")
    list_editable = ("is_resolved",)
    search_fields = ("share__hash_id", "comment")
