"""Core models for unified reference-counted file asset storage."""

from __future__ import annotations

import hashlib
import uuid

from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone

from core.services import detect_mime_type, sanitize_filename


def asset_upload_path(instance: "FileAsset", filename: str) -> str:
    """Store physical assets organized by year/month and unique UUID prefix."""
    safe = sanitize_filename(filename)
    now = timezone.now()
    return f"assets/{now:%Y/%m}/{instance.uuid}_{safe}"


class FileAsset(models.Model):
    """Physical file stored on disk, safely referenced by DriveFile and/or Share records."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    file = models.FileField(upload_to=asset_upload_path, max_length=500)
    original_name = models.CharField(max_length=255)
    size = models.BigIntegerField(default=0)
    mime_type = models.CharField(max_length=120, default="application/octet-stream")
    sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Файловый ресурс"
        verbose_name_plural = "Файловые ресурсы"

    def __str__(self) -> str:
        return f"{self.original_name} ({self.size} B)"

    def delete_if_unreferenced(self) -> bool:
        """Delete physical file and record if no DriveFile or Share references this asset."""
        has_drive_refs = self.drive_files.exists()
        has_share_refs = self.shares.exists()
        if not has_drive_refs and not has_share_refs:
            if self.file:
                self.file.delete(save=False)
            self.delete()
            return True
        return False

    @classmethod
    def create_from_uploaded(
        cls,
        uploaded_file,
        filename: str | None = None,
        declared_mime: str | None = None,
    ) -> "FileAsset":
        """Create a FileAsset from a Django UploadedFile or ContentFile."""
        resolved_name = sanitize_filename(filename or getattr(uploaded_file, "name", "file"))
        mime = detect_mime_type(
            resolved_name,
            declared_mime or getattr(uploaded_file, "content_type", None),
        )
        hasher = hashlib.sha256()
        total_size = 0
        if hasattr(uploaded_file, "chunks"):
            for chunk in uploaded_file.chunks():
                hasher.update(chunk)
                total_size += len(chunk)
            if hasattr(uploaded_file, "seek"):
                uploaded_file.seek(0)
        else:
            raw = uploaded_file.read()
            hasher.update(raw)
            total_size = len(raw)
            if hasattr(uploaded_file, "seek"):
                uploaded_file.seek(0)

        asset = cls(
            original_name=resolved_name,
            size=total_size,
            mime_type=mime,
            sha256=hasher.hexdigest(),
        )
        asset.file.save(resolved_name, uploaded_file, save=False)
        asset.save()
        return asset

    @classmethod
    def create_from_bytes(
        cls,
        data: bytes,
        filename: str,
        declared_mime: str | None = None,
    ) -> "FileAsset":
        """Create a FileAsset from raw bytes."""
        resolved_name = sanitize_filename(filename)
        content_file = ContentFile(data, name=resolved_name)
        return cls.create_from_uploaded(content_file, filename=resolved_name, declared_mime=declared_mime)
