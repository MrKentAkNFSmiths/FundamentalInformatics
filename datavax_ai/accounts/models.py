"""Account models for DataVax user profiles and storage quotas."""

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Sum


class Profile(models.Model):
    """Extended user profile with avatar, bio, and personal drive quota."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    bio = models.TextField(max_length=300, blank=True, default="")
    storage_quota = models.BigIntegerField(default=settings.DATAVAX_DEFAULT_QUOTA_BYTES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Профиль"
        verbose_name_plural = "Профили"

    def __str__(self) -> str:
        return f"Profile({self.user.username})"

    @property
    def used_storage_bytes(self) -> int:
        """Total bytes consumed by the user's files in Drive."""
        result = self.user.drive_files.aggregate(total=Sum("asset__size"))
        return int(result.get("total") or 0)

    @property
    def storage_usage_percent(self) -> int:
        """Percentage of storage quota used (0..100)."""
        if self.storage_quota <= 0:
            return 100
        pct = int((self.used_storage_bytes / self.storage_quota) * 100)
        return min(100, max(0, pct))

    @classmethod
    def for_user(cls, user: User) -> "Profile":
        """Get or create a Profile for the given user."""
        profile, _ = cls.objects.get_or_create(user=user)
        return profile
