"""Views for the personal cloud Drive with folders, uploads, notes, ZIP export, and sharing."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import Profile
from core.models import FileAsset
from core.services import (
    build_file_response,
    get_code_language,
    get_preview_category,
    read_text_preview,
    sanitize_filename,
    sanitize_folder_name,
)
from drive.models import DriveFile, Folder
from drive.services import (
    build_folder_tree,
    build_folder_zip,
    collect_move_targets,
    unique_drive_filename,
    validate_upload_against_quota,
)
from shares.services import create_share_record, parse_bool_flag, parse_expiration


def _json_or_redirect(request: HttpRequest, data: dict, redirect_url: str, status: int = 200) -> HttpResponse:
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )
    if is_ajax:
        return JsonResponse(data, status=status)
    if data.get("success"):
        if data.get("message"):
            messages.success(request, data["message"])
    elif data.get("error"):
        messages.error(request, data["error"])
    return redirect(redirect_url)


@login_required
def drive_explorer(request: HttpRequest, folder_id=None) -> HttpResponse:
    """Display the user's cloud Drive folder explorer."""
    root_folder = Folder.ensure_root_for_user(request.user)
    if folder_id is not None:
        current_folder = get_object_or_404(Folder, uuid=folder_id, owner=request.user)
    else:
        current_folder = root_folder

    filter_mode = request.GET.get("filter", "").strip()
    search_query = request.GET.get("q", "").strip()
    sort_by = request.GET.get("sort", "date").strip()

    sort_map = {
        "name": "name",
        "size": "-asset__size",
        "date": "-updated_at",
    }
    file_order = sort_map.get(sort_by, "-updated_at")
    folder_order = "name" if sort_by == "name" else "-updated_at"

    is_filtered_view = bool(search_query or filter_mode in ("starred", "recent"))

    if search_query:
        subfolders = Folder.objects.filter(
            owner=request.user,
            is_root=False,
            name__icontains=search_query,
        ).order_by(folder_order)
        files = (
            DriveFile.objects.filter(owner=request.user, name__icontains=search_query)
            .select_related("asset", "folder")
            .order_by(file_order)
        )
    elif filter_mode == "starred":
        subfolders = Folder.objects.none()
        files = (
            DriveFile.objects.filter(owner=request.user, is_starred=True)
            .select_related("asset", "folder")
            .order_by(file_order)
        )
    elif filter_mode == "recent":
        subfolders = Folder.objects.none()
        files = (
            DriveFile.objects.filter(owner=request.user)
            .select_related("asset", "folder")
            .order_by("-updated_at")[:30]
        )
    else:
        subfolders = current_folder.subfolders.all().order_by(folder_order)
        files = current_folder.files.select_related("asset", "folder").order_by(file_order)

    profile = Profile.for_user(request.user)
    context = {
        "root_folder": root_folder,
        "current_folder": current_folder,
        "breadcrumbs": current_folder.get_breadcrumbs(),
        "subfolders": subfolders,
        "files": files,
        "folder_tree": build_folder_tree(request.user, None if is_filtered_view else current_folder.pk),
        "move_targets": collect_move_targets(request.user),
        "profile": profile,
        "filter_mode": filter_mode,
        "search_query": search_query,
        "sort_by": sort_by,
        "is_filtered_view": is_filtered_view,
    }
    return render(request, "drive/explorer.html", context)


@login_required
@require_POST
def create_folder_handler(request: HttpRequest) -> HttpResponse:
    """Create a subfolder inside a target parent folder."""
    parent_uuid = request.POST.get("parent_uuid")
    if parent_uuid:
        parent = get_object_or_404(Folder, uuid=parent_uuid, owner=request.user)
    else:
        parent = Folder.ensure_root_for_user(request.user)

    redirect_url = reverse("drive:folder", kwargs={"folder_id": parent.uuid})
    try:
        name = sanitize_folder_name(request.POST.get("name", ""))
    except ValidationError as exc:
        return _json_or_redirect(request, {"success": False, "error": exc.message}, redirect_url, status=400)

    if Folder.objects.filter(owner=request.user, parent=parent, name=name).exists():
        return _json_or_redirect(
            request,
            {"success": False, "error": "Папка с таким именем уже существует."},
            redirect_url,
            status=400,
        )

    folder = Folder.objects.create(owner=request.user, parent=parent, name=name, is_root=False)
    return _json_or_redirect(
        request,
        {
            "success": True,
            "message": f"Папка «{folder.name}» создана.",
            "folder": {
                "uuid": str(folder.uuid),
                "name": folder.name,
                "url": reverse("drive:folder", kwargs={"folder_id": folder.uuid}),
            },
        },
        redirect_url,
        status=201,
    )


@login_required
@require_POST
def rename_folder_handler(request: HttpRequest, folder_id) -> HttpResponse:
    """Rename a non-root folder."""
    folder = get_object_or_404(Folder, uuid=folder_id, owner=request.user)
    redirect_url = reverse("drive:folder", kwargs={"folder_id": (folder.parent or folder).uuid})
    if folder.is_root:
        return _json_or_redirect(
            request, {"success": False, "error": "Корневую папку нельзя переименовать."}, redirect_url, status=400
        )

    try:
        new_name = sanitize_folder_name(request.POST.get("name", ""))
    except ValidationError as exc:
        return _json_or_redirect(request, {"success": False, "error": exc.message}, redirect_url, status=400)

    if (
        Folder.objects.filter(owner=request.user, parent=folder.parent, name=new_name)
        .exclude(pk=folder.pk)
        .exists()
    ):
        return _json_or_redirect(
            request, {"success": False, "error": "Папка с таким именем уже существует."}, redirect_url, status=400
        )

    folder.name = new_name
    folder.save(update_fields=["name", "updated_at"])
    return _json_or_redirect(
        request,
        {"success": True, "message": "Папка переименована.", "name": folder.name},
        redirect_url,
    )


@login_required
@require_POST
def move_folder_handler(request: HttpRequest, folder_id) -> HttpResponse:
    """Move a folder to another parent folder with cycle protection."""
    folder = get_object_or_404(Folder, uuid=folder_id, owner=request.user)
    redirect_url = reverse("drive:folder", kwargs={"folder_id": (folder.parent or folder).uuid})
    if folder.is_root:
        return _json_or_redirect(
            request, {"success": False, "error": "Корневую папку нельзя переместить."}, redirect_url, status=400
        )

    target_uuid = request.POST.get("target_uuid")
    target = get_object_or_404(Folder, uuid=target_uuid, owner=request.user)

    if target.is_descendant_of(folder):
        return _json_or_redirect(
            request,
            {"success": False, "error": "Нельзя переместить папку внутрь самой себя или вложенной папки."},
            redirect_url,
            status=400,
        )

    if (
        Folder.objects.filter(owner=request.user, parent=target, name=folder.name)
        .exclude(pk=folder.pk)
        .exists()
    ):
        return _json_or_redirect(
            request,
            {"success": False, "error": "В целевой папке уже есть папка с таким именем."},
            redirect_url,
            status=400,
        )

    folder.parent = target
    folder.save(update_fields=["parent", "updated_at"])
    return _json_or_redirect(
        request,
        {"success": True, "message": f"Папка перемещена в «{target.name}»."},
        reverse("drive:folder", kwargs={"folder_id": target.uuid}),
    )


@login_required
@require_POST
def delete_folder_handler(request: HttpRequest, folder_id) -> HttpResponse:
    """Delete a non-root folder and all nested subfolders/files."""
    folder = get_object_or_404(Folder, uuid=folder_id, owner=request.user)
    if folder.is_root:
        return _json_or_redirect(
            request,
            {"success": False, "error": "Корневую папку нельзя удалить."},
            reverse("drive:root"),
            status=400,
        )

    parent_folder = folder.parent or Folder.ensure_root_for_user(request.user)
    folder_name = folder.name
    folder.delete()
    redirect_url = reverse("drive:folder", kwargs={"folder_id": parent_folder.uuid})
    return _json_or_redirect(
        request,
        {"success": True, "message": f"Папка «{folder_name}» удалена.", "redirect_url": redirect_url},
        redirect_url,
    )


@login_required
def download_folder_zip_handler(request: HttpRequest, folder_id) -> FileResponse:
    """Download an entire Drive folder hierarchy as a ZIP archive."""
    folder = get_object_or_404(Folder, uuid=folder_id, owner=request.user)
    zip_stream = build_folder_zip(folder)
    zip_filename = f"{sanitize_filename(folder.name, default='drive')}.zip"
    response = FileResponse(zip_stream, content_type="application/zip", as_attachment=True)
    response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
    return response


@login_required
@require_POST
def upload_files_handler(request: HttpRequest) -> HttpResponse:
    """Upload one or more files into the specified Drive folder."""
    folder_uuid = request.POST.get("folder_uuid")
    if folder_uuid:
        folder = get_object_or_404(Folder, uuid=folder_uuid, owner=request.user)
    else:
        folder = Folder.ensure_root_for_user(request.user)

    redirect_url = reverse("drive:folder", kwargs={"folder_id": folder.uuid})
    uploaded_list = request.FILES.getlist("files") or request.FILES.getlist("file")
    if not uploaded_list:
        return _json_or_redirect(
            request, {"success": False, "error": "Выберите файлы для загрузки."}, redirect_url, 400
        )

    total_incoming = sum(f.size for f in uploaded_list)
    try:
        validate_upload_against_quota(request.user, total_incoming)
    except ValidationError as exc:
        return _json_or_redirect(request, {"success": False, "error": exc.message}, redirect_url, status=400)

    created_items = []
    for f in uploaded_list:
        unique_name = unique_drive_filename(folder, f.name)
        asset = FileAsset.create_from_uploaded(f, filename=unique_name)
        df = DriveFile.objects.create(
            owner=request.user,
            folder=folder,
            asset=asset,
            name=unique_name,
        )
        created_items.append({"uuid": str(df.uuid), "name": df.name, "size": df.size})

    return _json_or_redirect(
        request,
        {
            "success": True,
            "message": f"Загружено файлов: {len(created_items)}.",
            "files": created_items,
        },
        redirect_url,
        status=201,
    )


@login_required
@require_POST
def create_note_handler(request: HttpRequest) -> HttpResponse:
    """Create a text or source code file directly inside a Drive folder."""
    folder_uuid = request.POST.get("folder_uuid")
    if folder_uuid:
        folder = get_object_or_404(Folder, uuid=folder_uuid, owner=request.user)
    else:
        folder = Folder.ensure_root_for_user(request.user)

    redirect_url = reverse("drive:folder", kwargs={"folder_id": folder.uuid})
    raw_name = (request.POST.get("filename") or "note.txt").strip()
    if "." not in raw_name:
        raw_name = f"{raw_name}.txt"
    content = request.POST.get("content", "")
    data = content.encode("utf-8")

    try:
        validate_upload_against_quota(request.user, len(data))
    except ValidationError as exc:
        return _json_or_redirect(request, {"success": False, "error": exc.message}, redirect_url, status=400)

    unique_name = unique_drive_filename(folder, raw_name)
    asset = FileAsset.create_from_bytes(data, filename=unique_name)
    df = DriveFile.objects.create(owner=request.user, folder=folder, asset=asset, name=unique_name)

    return _json_or_redirect(
        request,
        {
            "success": True,
            "message": f"Файл «{df.name}» создан.",
            "file": {
                "uuid": str(df.uuid),
                "name": df.name,
                "preview_url": reverse("drive:preview_file", kwargs={"file_id": df.uuid}),
            },
        },
        redirect_url,
        status=201,
    )


@login_required
def preview_file_page(request: HttpRequest, file_id) -> HttpResponse:
    """Preview (and optionally edit if text/code) a Drive file."""
    drive_file = get_object_or_404(
        DriveFile.objects.select_related("asset", "folder"),
        uuid=file_id,
        owner=request.user,
    )
    category = get_preview_category(drive_file.name, drive_file.mime_type)
    code_language = get_code_language(drive_file.name)
    file_content = None
    is_truncated = False
    if category in ("code", "text"):
        file_content, is_truncated = read_text_preview(drive_file.asset.file)

    context = {
        "drive_file": drive_file,
        "breadcrumbs": drive_file.folder.get_breadcrumbs(),
        "category": category,
        "code_language": code_language,
        "file_content": file_content,
        "is_truncated": is_truncated,
        "move_targets": collect_move_targets(request.user),
    }
    return render(request, "drive/preview.html", context)


@login_required
@require_POST
def update_file_content_handler(request: HttpRequest, file_id) -> JsonResponse:
    """Save edited text/code content for a Drive file cleanly via a new FileAsset."""
    drive_file = get_object_or_404(DriveFile.objects.select_related("asset"), uuid=file_id, owner=request.user)
    content = request.POST.get("content", "")
    data = content.encode("utf-8")

    delta = max(0, len(data) - drive_file.size)
    try:
        validate_upload_against_quota(request.user, delta)
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.message}, status=400)

    old_asset = drive_file.asset
    new_asset = FileAsset.create_from_bytes(data, filename=drive_file.name)
    drive_file.asset = new_asset
    drive_file.save(update_fields=["asset", "updated_at"])
    old_asset.delete_if_unreferenced()

    return JsonResponse({"success": True, "message": "Изменения сохранены.", "size": new_asset.size})


@login_required
def download_file_handler(request: HttpRequest, file_id) -> FileResponse:
    """Download a Drive file owned by the current user."""
    drive_file = get_object_or_404(DriveFile.objects.select_related("asset"), uuid=file_id, owner=request.user)
    return build_file_response(drive_file.asset.file, drive_file.name, drive_file.mime_type, as_attachment=True)


@login_required
def raw_file_handler(request: HttpRequest, file_id) -> FileResponse:
    """Stream Drive file inline for authorized preview (image/video/audio/PDF)."""
    drive_file = get_object_or_404(DriveFile.objects.select_related("asset"), uuid=file_id, owner=request.user)
    return build_file_response(drive_file.asset.file, drive_file.name, drive_file.mime_type, as_attachment=False)


@login_required
@require_POST
def toggle_star_handler(request: HttpRequest, file_id) -> JsonResponse:
    """Toggle favorite/starred status on a Drive file."""
    drive_file = get_object_or_404(DriveFile, uuid=file_id, owner=request.user)
    drive_file.is_starred = not drive_file.is_starred
    drive_file.save(update_fields=["is_starred", "updated_at"])
    return JsonResponse({"success": True, "is_starred": drive_file.is_starred})


@login_required
@require_POST
def rename_file_handler(request: HttpRequest, file_id) -> HttpResponse:
    """Rename a Drive file inside its current folder."""
    drive_file = get_object_or_404(DriveFile, uuid=file_id, owner=request.user)
    redirect_url = reverse("drive:folder", kwargs={"folder_id": drive_file.folder.uuid})
    raw_name = (request.POST.get("name") or "").strip()
    if not raw_name:
        return _json_or_redirect(request, {"success": False, "error": "Введите новое имя файла."}, redirect_url, 400)

    new_name = sanitize_filename(raw_name)
    if (
        DriveFile.objects.filter(folder=drive_file.folder, name=new_name)
        .exclude(pk=drive_file.pk)
        .exists()
    ):
        return _json_or_redirect(
            request, {"success": False, "error": "Файл с таким именем уже есть в папке."}, redirect_url, 400
        )

    drive_file.name = new_name
    drive_file.save(update_fields=["name", "updated_at"])
    return _json_or_redirect(
        request, {"success": True, "message": "Файл переименован.", "name": new_name}, redirect_url
    )


@login_required
@require_POST
def move_file_handler(request: HttpRequest, file_id) -> HttpResponse:
    """Move a Drive file into another folder owned by the user."""
    drive_file = get_object_or_404(DriveFile, uuid=file_id, owner=request.user)
    target = get_object_or_404(Folder, uuid=request.POST.get("target_uuid"), owner=request.user)
    redirect_url = reverse("drive:folder", kwargs={"folder_id": target.uuid})

    if target.pk != drive_file.folder_id:
        drive_file.name = unique_drive_filename(target, drive_file.name, exclude_pk=drive_file.pk)
        drive_file.folder = target
        drive_file.save(update_fields=["folder", "name", "updated_at"])

    return _json_or_redirect(
        request,
        {"success": True, "message": f"Файл перемещён в «{target.name}»."},
        redirect_url,
    )


@login_required
@require_POST
def delete_file_handler(request: HttpRequest, file_id) -> HttpResponse:
    """Delete a Drive file (and physical asset if unreferenced)."""
    drive_file = get_object_or_404(DriveFile, uuid=file_id, owner=request.user)
    folder_uuid = drive_file.folder.uuid
    name = drive_file.name
    drive_file.delete()
    redirect_url = reverse("drive:folder", kwargs={"folder_id": folder_uuid})
    return _json_or_redirect(
        request,
        {"success": True, "message": f"Файл «{name}» удалён.", "redirect_url": redirect_url},
        redirect_url,
    )


@login_required
@require_POST
def share_drive_file_handler(request: HttpRequest, file_id) -> JsonResponse:
    """Create a public or password-protected Share link from a Drive file."""
    drive_file = get_object_or_404(DriveFile.objects.select_related("asset"), uuid=file_id, owner=request.user)

    payload = request.POST
    if request.content_type and "application/json" in request.content_type:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}

    title = (payload.get("title") or drive_file.name).strip()
    description = (payload.get("description") or "").strip()
    password = payload.get("password") or ""
    expire_preset = payload.get("expire_preset", "1w")
    is_anonymous = parse_bool_flag(payload.get("is_anonymous"))

    expire_date = parse_expiration(expire_preset=expire_preset)
    share = create_share_record(
        asset=drive_file.asset,
        title=title,
        description=description,
        user=request.user,
        is_anonymous=is_anonymous,
        password=password,
        expire_date=expire_date,
        source_drive_file=drive_file,
    )
    share_url = request.build_absolute_uri(reverse("shares:detail", kwargs={"hash_id": share.hash_id}))
    return JsonResponse(
        {
            "success": True,
            "hash_id": share.hash_id,
            "share_url": share_url,
            "message": "Ссылка для шеринга создана.",
        },
        status=201,
    )
