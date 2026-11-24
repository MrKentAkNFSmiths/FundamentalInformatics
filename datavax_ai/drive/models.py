"""Drive models representing user folder hierarchy and stored files."""

from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import FileAsset
from core.services import sanitize_folder_name


class Folder(models.Model):
    """Hierarchical folder belonging to a user's personal cloud Drive."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="folders")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subfolders",
    )
    name = models.CharField(max_length=120)
    is_root = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Папка"
        verbose_name_plural = "Папки"
        constraints = [
            models.UniqueConstraint(
                fields=["owner"],
                condition=Q(is_root=True),
                name="unique_root_folder_per_user",
            ),
            models.UniqueConstraint(
                fields=["owner", "parent", "name"],
                condition=Q(parent__isnull=False),
                name="unique_subfolder_name_per_parent",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.owner.username}:{self.get_virtual_path()}"

    @classmethod
    def ensure_root_for_user(cls, user: User) -> "Folder":
        """Return existing root folder for user or create it atomically."""
        root = cls.objects.filter(owner=user, is_root=True).first()
        if root is None:
            root, _ = cls.objects.get_or_create(
                owner=user,
                is_root=True,
                defaults={"name": "Мой диск", "parent": None},
            )
        return root

    def get_breadcrumbs(self) -> list["Folder"]:
        """Return list of folders from root down to self."""
        chain: list[Folder] = []
        current: Folder | None = self
        seen: set[int] = set()
        while current is not None and current.pk not in seen:
            seen.add(current.pk)
            chain.append(current)
            current = current.parent
        chain.reverse()
        return chain

    def get_virtual_path(self) -> str:
        """Return slash-delimited virtual path such as '/Drive/Photos'."""
        return "/" + "/".join(folder.name for folder in self.get_breadcrumbs())

    def is_descendant_of(self, candidate_ancestor: "Folder") -> bool:
        """Check whether self is the same as or inside candidate_ancestor."""
        current: Folder | None = self
        seen: set[int] = set()
        while current is not None and current.pk not in seen:
            if current.pk == candidate_ancestor.pk:
                return True
            seen.add(current.pk)
            current = current.parent
        return False

    def clean(self) -> None:
        if not self.is_root:
            self.name = sanitize_folder_name(self.name)
            if self.parent is None:
                raise ValidationError("Обычная папка должна иметь родительскую папку.")
            if self.parent.owner_id != self.owner_id:
                raise ValidationError("Нельзя создать папку в чужом хранилище.")
            if self.pk and self.parent.is_descendant_of(self):
                raise ValidationError("Нельзя переместить папку внутрь самой себя или дочерней папки.")
        else:
            if self.parent is not None:
                raise ValidationError("Корневая папка не может иметь родителя.")


class DriveFile(models.Model):
    """A file stored in a user's Drive folder."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="drive_files")
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name="files")
    asset = models.ForeignKey(FileAsset, on_delete=models.PROTECT, related_name="drive_files")
    name = models.CharField(max_length=255)
    is_starred = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Файл на диске"
        verbose_name_plural = "Файлы на диске"
        constraints = [
            models.UniqueConstraint(
                fields=["folder", "name"],
                name="unique_file_name_per_folder",
            )
        ]

    def __str__(self) -> str:
        return f"{self.owner.username}/{self.name}"

    @property
    def size(self) -> int:
        return self.asset.size

    @property
    def mime_type(self) -> str:
        return self.asset.mime_type
