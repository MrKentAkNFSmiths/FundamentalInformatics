from django.contrib import admin
from unfold.admin import ModelAdmin

from core.models import FileAsset


@admin.register(FileAsset)
class FileAssetAdmin(ModelAdmin):
    list_display = ("original_name", "mime_type", "size", "created_at")
    search_fields = ("original_name", "sha256", "mime_type")
    readonly_fields = ("uuid", "sha256", "size", "created_at")
