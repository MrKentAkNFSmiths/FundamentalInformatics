from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from unfold.admin import ModelAdmin

from accounts.models import Profile

admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    list_display = ("username", "email", "is_active", "is_staff", "date_joined")
    list_editable = ("is_active",)
    search_fields = ("username", "email")


@admin.register(Profile)
class ProfileAdmin(ModelAdmin):
    list_display = ("user", "storage_quota", "created_at")
    search_fields = ("user__username", "user__email")
