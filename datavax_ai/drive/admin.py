from django.contrib import admin
from unfold.admin import ModelAdmin

from drive.models import DriveFile, Folder


@admin.register(Folder)
class FolderAdmin(ModelAdmin):
    list_display = ("name", "owner", "parent", "is_root", "created_at")
    list_filter = ("is_root",)
    search_fields = ("name", "owner__username")


@admin.register(DriveFile)
class DriveFileAdmin(ModelAdmin):
    list_display = ("name", "owner", "folder", "is_starred", "created_at")
    list_filter = ("is_starred",)
    search_fields = ("name", "owner__username")
