"""Models for public/password-protected file and code shares, likes, and reports."""

from __future__ import annotations

from django.contrib.auth.hashers import check_password as django_check_password
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from core.models import FileAsset


class Share(models.Model):
    """A shareable link pointing to an uploaded file, code snippet, or Drive file."""

    hash_id = models.CharField(max_length=16, unique=True, db_index=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shares",
    )
    source_drive_file = models.ForeignKey(
        "drive.DriveFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shares",
    )
    asset = models.ForeignKey(FileAsset, on_delete=models.PROTECT, related_name="shares")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    password_hash = models.CharField(max_length=255, blank=True, default="")
    is_anonymous = models.BooleanField(default=False)
    expire_date = models.DateTimeField(null=True, blank=True)
    views_count = models.PositiveIntegerField(default=0)
    downloads_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Шейр"
        verbose_name_plural = "Шейры"

    def __str__(self) -> str:
        return f"{self.title} ({self.hash_id})"

    def set_password(self, raw_password: str | None) -> None:
        """Hash and store access password, or clear protection if empty."""
        cleaned = (raw_password or "").strip()
        self.password_hash = make_password(cleaned) if cleaned else ""

    def verify_password(self, raw_password: str | None) -> bool:
        """Verify candidate password against stored hash."""
        if not self.password_hash:
            return True
        return django_check_password(raw_password or "", self.password_hash)

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash)

    @property
    def is_expired(self) -> bool:
        return bool(self.expire_date and timezone.now() >= self.expire_date)

    @property
    def display_author(self) -> str:
        if self.is_anonymous or self.user is None:
            return "Аноним"
        return self.user.username


class Like(models.Model):
    """User like on a Share."""

    share = models.ForeignKey(Share, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="share_likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Лайк"
        verbose_name_plural = "Лайки"
        constraints = [
            models.UniqueConstraint(fields=["share", "user"], name="unique_share_like"),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} -> {self.share.hash_id}"


class Report(models.Model):
    """Abuse or copyright report submitted against a Share."""

    REASON_CHOICES = [
        ("spam", "Спам или реклама"),
        ("malware", "Вредоносный файл"),
        ("copyright", "Нарушение авторских прав"),
        ("abuse", "Запрещённый контент"),
        ("other", "Другое"),
    ]

    share = models.ForeignKey(Share, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_reports",
    )
    reason = models.CharField(max_length=32, choices=REASON_CHOICES, default="other")
    comment = models.TextField(max_length=500, blank=True, default="")
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Жалоба"
        verbose_name_plural = "Жалобы"

    def __str__(self) -> str:
        return f"Report({self.share.hash_id}, {self.reason})"
