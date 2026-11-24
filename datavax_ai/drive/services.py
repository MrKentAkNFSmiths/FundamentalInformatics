"""Business logic helpers for Drive quota enforcement, naming, trees, and ZIP export."""

from __future__ import annotations

import os
import tempfile
import zipfile
from typing import IO

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from accounts.models import Profile
from core.services import sanitize_filename
from drive.models import DriveFile, Folder


def validate_upload_against_quota(user: User, incoming_bytes: int) -> None:
    """Ensure file fits both per-file limit and user's Drive quota."""
    if incoming_bytes > settings.DATAVAX_MAX_FILE_SIZE_BYTES:
        max_mb = settings.DATAVAX_MAX_FILE_SIZE_MB
        raise ValidationError(f"Файл превышает максимальный размер ({max_mb} МБ).")
    profile = Profile.for_user(user)
    if profile.used_storage_bytes + incoming_bytes > profile.storage_quota:
        raise ValidationError("Недостаточно места на вашем диске. Удалите лишние файлы.")


def unique_drive_filename(folder: Folder, desired_name: str, exclude_pk: int | None = None) -> str:
    """Resolve duplicate filenames in a folder by appending (1), (2), etc."""
    clean = sanitize_filename(desired_name)
    stem, ext = os.path.splitext(clean)
    candidate = clean
    counter = 1
    qs = DriveFile.objects.filter(folder=folder)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(name=candidate).exists():
        candidate = f"{stem} ({counter}){ext}"
        counter += 1
    return candidate


def build_folder_tree(user: User, active_folder_id: int | None = None) -> list[dict]:
    """Build nested sidebar tree of all folders owned by user in one query."""
    folders = list(Folder.objects.filter(owner=user).order_by("-is_root", "name"))
    children_map: dict[int | None, list[Folder]] = {}
    for folder in folders:
        children_map.setdefault(folder.parent_id, []).append(folder)

    def build_node(folder: Folder, depth: int) -> dict:
        kids = [build_node(child, depth + 1) for child in children_map.get(folder.pk, [])]
        is_active = folder.pk == active_folder_id
        has_active_child = any(k["is_active"] or k["is_expanded"] for k in kids)
        return {
            "folder": folder,
            "depth": depth,
            "is_active": is_active,
            "is_expanded": folder.is_root or is_active or has_active_child,
            "children": kids,
        }

    roots = children_map.get(None, [])
    return [build_node(root, 0) for root in roots]


def collect_move_targets(user: User, exclude_folder: Folder | None = None) -> list[dict]:
    """Return flat indented list of valid target folders for moving items."""
    folders = list(Folder.objects.filter(owner=user).order_by("-is_root", "name"))
    children_map: dict[int | None, list[Folder]] = {}
    for folder in folders:
        children_map.setdefault(folder.parent_id, []).append(folder)

    result: list[dict] = []

    def walk(folder: Folder, depth: int) -> None:
        if exclude_folder is not None and folder.is_descendant_of(exclude_folder):
            return
        prefix = "— " * depth
        result.append({"uuid": str(folder.uuid), "label": f"{prefix}{folder.name}", "folder": folder})
        for child in children_map.get(folder.pk, []):
            walk(child, depth + 1)

    for root in children_map.get(None, []):
        walk(root, 0)
    return result


def build_folder_zip(folder: Folder) -> IO[bytes]:
    """Create a spooled ZIP archive containing folder hierarchy and all contained files."""
    tmp = tempfile.SpooledTemporaryFile(max_size=20 * 1024 * 1024)
    all_folders = list(Folder.objects.filter(owner=folder.owner))
    children_map: dict[int | None, list[Folder]] = {}
    for item in all_folders:
        children_map.setdefault(item.parent_id, []).append(item)

    files_by_folder: dict[int, list[DriveFile]] = {}
    for df in DriveFile.objects.filter(owner=folder.owner).select_related("asset"):
        files_by_folder.setdefault(df.folder_id, []).append(df)

    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        def write_dir(current: Folder, rel_prefix: str) -> None:
            dir_path = f"{rel_prefix}{current.name}/"
            files = files_by_folder.get(current.pk, [])
            subfolders = children_map.get(current.pk, [])
            if not files and not subfolders:
                zf.writestr(dir_path, b"")
            for df in files:
                arcname = f"{dir_path}{df.name}"
                try:
                    with df.asset.file.open("rb") as fh:
                        zf.writestr(arcname, fh.read())
                except OSError:
                    continue
            for sub in subfolders:
                write_dir(sub, dir_path)

        write_dir(folder, "")

    tmp.seek(0)
    return tmp
