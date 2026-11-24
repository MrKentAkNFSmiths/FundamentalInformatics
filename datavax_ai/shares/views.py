"""Views for creating, viewing, unlocking, liking, reporting, and saving shares."""

from __future__ import annotations

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import F
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import FileAsset
from core.services import (
    build_file_response,
    fetch_remote_file,
    get_code_language,
    get_preview_category,
    read_text_preview,
)
from drive.models import DriveFile, Folder
from drive.services import unique_drive_filename, validate_upload_against_quota
from shares.forms import ReportForm, SharePasswordForm
from shares.models import Like, Report, Share
from shares.services import create_share_record, parse_bool_flag, parse_expiration

EDITOR_LANGUAGES = [
    ("text", "Обычный текст"),
    ("python", "Python"),
    ("javascript", "JavaScript / TypeScript"),
    ("htmlmixed", "HTML"),
    ("css", "CSS"),
    ("go", "Go"),
    ("clike", "C / C++"),
    ("java", "Java"),
    ("sql", "SQL"),
    ("shell", "Shell / Bash"),
    ("json", "JSON"),
    ("yaml", "YAML"),
    ("markdown", "Markdown"),
    ("xml", "XML"),
]

LANGUAGE_EXTENSIONS = {
    "python": ".py",
    "javascript": ".js",
    "htmlmixed": ".html",
    "xml": ".xml",
    "css": ".css",
    "java": ".java",
    "go": ".go",
    "clike": ".cpp",
    "sql": ".sql",
    "shell": ".sh",
    "json": ".json",
    "yaml": ".yml",
    "markdown": ".md",
    "text": ".txt",
}


def _is_ajax(request: HttpRequest) -> bool:
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )


def _session_unlock_key(hash_id: str) -> str:
    return f"share_{hash_id}_unlocked"


def _has_share_access(request: HttpRequest, share: Share) -> bool:
    if not share.has_password:
        return True
    return bool(request.session.get(_session_unlock_key(share.hash_id), False))


def new_share_page(request: HttpRequest) -> HttpResponse:
    """Render unified share creator: Code/Text Editor, File Upload, and URL Fetch."""
    context = {
        "languages": EDITOR_LANGUAGES,
        "report_reasons": Report.REASON_CHOICES,
        "max_size_mb": settings.DATAVAX_MAX_FILE_SIZE_MB,
        "max_size_bytes": settings.DATAVAX_MAX_FILE_SIZE_BYTES,
    }
    return render(request, "shares/editor.html", context)


def create_share_handler(request: HttpRequest) -> HttpResponse:
    """Create a Share from an uploaded file, editor code snippet, or remote URL."""
    if request.method != "POST":
        return redirect("shares:new")

    uploaded_file = request.FILES.get("uploaded_file") or request.FILES.get("file")
    code_content = request.POST.get("code_content")
    remote_url = (request.POST.get("remote_url") or request.POST.get("url") or "").strip()

    title = (request.POST.get("title") or "").strip()
    description = (request.POST.get("description") or "").strip()
    password = request.POST.get("password") or ""
    expire_preset = request.POST.get("expire_preset")
    expire_date_str = request.POST.get("expire_date")
    is_anonymous = parse_bool_flag(request.POST.get("is_anonymous"))
    save_to_drive = parse_bool_flag(request.POST.get("save_to_drive"))

    asset: FileAsset | None = None
    try:
        if uploaded_file is not None:
            if uploaded_file.size > settings.DATAVAX_MAX_FILE_SIZE_BYTES:
                raise ValidationError(f"Максимальный размер файла — {settings.DATAVAX_MAX_FILE_SIZE_MB} МБ.")
            asset = FileAsset.create_from_uploaded(uploaded_file)
            if not title:
                title = uploaded_file.name
        elif remote_url:
            data, filename, mime_type = fetch_remote_file(remote_url, max_bytes=settings.DATAVAX_MAX_FILE_SIZE_BYTES)
            asset = FileAsset.create_from_bytes(data, filename=filename, declared_mime=mime_type)
            if not title:
                title = filename
        elif code_content is not None and code_content != "":
            language = request.POST.get("language", "text")
            ext = LANGUAGE_EXTENSIONS.get(language, ".txt")
            raw_filename = (request.POST.get("filename") or "").strip()
            if not raw_filename:
                base_title = title or "snippet"
                raw_filename = base_title if "." in base_title else f"{base_title}{ext}"
            data = code_content.encode("utf-8")
            if len(data) > settings.DATAVAX_MAX_FILE_SIZE_BYTES:
                raise ValidationError(f"Максимальный размер файла — {settings.DATAVAX_MAX_FILE_SIZE_MB} МБ.")
            asset = FileAsset.create_from_bytes(data, filename=raw_filename)
            if not title:
                title = raw_filename
        else:
            raise ValidationError("Загрузите файл, введите текст/код или укажите URL.")
    except ValidationError as exc:
        if _is_ajax(request):
            return JsonResponse({"success": False, "error": exc.message}, status=400)
        messages.error(request, exc.message)
        return redirect("shares:new")

    expire_date = parse_expiration(expire_preset=expire_preset, expire_date_str=expire_date_str)
    share = create_share_record(
        asset=asset,
        title=title,
        description=description,
        user=request.user,
        is_anonymous=is_anonymous,
        password=password,
        expire_date=expire_date,
    )

    if save_to_drive and request.user.is_authenticated:
        try:
            validate_upload_against_quota(request.user, asset.size)
            root = Folder.ensure_root_for_user(request.user)
            drive_name = unique_drive_filename(root, asset.original_name)
            DriveFile.objects.create(owner=request.user, folder=root, asset=asset, name=drive_name)
        except ValidationError as exc:
            messages.warning(request, f"Шейр создан, но не сохранён на диск: {exc.message}")

    share_path = reverse("shares:detail", kwargs={"hash_id": share.hash_id})
    if _is_ajax(request):
        return JsonResponse(
            {
                "success": True,
                "hash_id": share.hash_id,
                "share_url": request.build_absolute_uri(share_path),
                "redirect_url": share_path,
            },
            status=201,
        )
    return redirect(share_path)


def share_detail_page(request: HttpRequest, hash_id: str) -> HttpResponse:
    """Display a shared file/code page with expiration and password enforcement."""
    share = get_object_or_404(Share.objects.select_related("asset", "user", "user__profile"), hash_id=hash_id)

    if share.is_expired:
        return render(request, "shares/expired.html", {"share": share}, status=410)

    if share.has_password and not _has_share_access(request, share):
        form = SharePasswordForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            if share.verify_password(form.cleaned_data["password"]):
                request.session[_session_unlock_key(hash_id)] = True
                if _is_ajax(request):
                    return JsonResponse({"success": True})
                return redirect("shares:detail", hash_id=hash_id)
            error_msg = "Неверный пароль доступа."
            if _is_ajax(request):
                return JsonResponse({"success": False, "error": error_msg}, status=403)
            messages.error(request, error_msg)
        return render(request, "shares/password_protected.html", {"form": form, "share": share})

    Share.objects.filter(pk=share.pk).update(views_count=F("views_count") + 1)
    share.refresh_from_db(fields=["views_count"])

    category = get_preview_category(share.asset.original_name, share.asset.mime_type)
    code_language = get_code_language(share.asset.original_name)
    file_content = None
    is_truncated = False
    if category in ("code", "text"):
        file_content, is_truncated = read_text_preview(share.asset.file)

    like_count = share.likes.count()
    user_liked = (
        request.user.is_authenticated and share.likes.filter(user=request.user).exists()
    )
    can_delete = request.user.is_authenticated and (
        request.user == share.user or request.user.is_superuser
    )

    context = {
        "share": share,
        "category": category,
        "code_language": code_language,
        "file_content": file_content,
        "is_truncated": is_truncated,
        "like_count": like_count,
        "user_liked": user_liked,
        "can_delete": can_delete,
        "report_reasons": Report.REASON_CHOICES,
        "share_url": request.build_absolute_uri(reverse("shares:detail", kwargs={"hash_id": share.hash_id})),
    }
    return render(request, "shares/detail.html", context)


def serve_share_raw_handler(request: HttpRequest, hash_id: str) -> HttpResponse:
    """Serve share file inline for authorized previews (enforcing expiration and password)."""
    share = get_object_or_404(Share.objects.select_related("asset"), hash_id=hash_id)
    if share.is_expired:
        return HttpResponse("Срок действия ссылки истёк.", status=410)
    if not _has_share_access(request, share):
        return HttpResponse("Требуется ввод пароля.", status=403)
    return build_file_response(
        share.asset.file,
        share.asset.original_name,
        share.asset.mime_type,
        as_attachment=False,
    )


def download_share_handler(request: HttpRequest, hash_id: str) -> HttpResponse:
    """Download a shared file as an attachment (enforcing expiration and password)."""
    share = get_object_or_404(Share.objects.select_related("asset"), hash_id=hash_id)
    if share.is_expired:
        return render(request, "shares/expired.html", {"share": share}, status=410)
    if not _has_share_access(request, share):
        return redirect("shares:detail", hash_id=hash_id)

    Share.objects.filter(pk=share.pk).update(downloads_count=F("downloads_count") + 1)
    return build_file_response(
        share.asset.file,
        share.asset.original_name,
        share.asset.mime_type,
        as_attachment=True,
    )


@login_required
@require_POST
def save_share_to_drive_handler(request: HttpRequest, hash_id: str) -> JsonResponse:
    """Save a copy reference of a shared file into the current user's Drive root."""
    share = get_object_or_404(Share.objects.select_related("asset"), hash_id=hash_id)
    if share.is_expired:
        return JsonResponse({"success": False, "error": "Срок действия ссылки истёк."}, status=410)
    if not _has_share_access(request, share):
        return JsonResponse({"success": False, "error": "Шейр защищён паролем."}, status=403)

    try:
        validate_upload_against_quota(request.user, share.asset.size)
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.message}, status=400)

    root = Folder.ensure_root_for_user(request.user)
    filename = unique_drive_filename(root, share.asset.original_name)
    df = DriveFile.objects.create(
        owner=request.user,
        folder=root,
        asset=share.asset,
        name=filename,
    )
    return JsonResponse(
        {
            "success": True,
            "message": f"Файл «{df.name}» сохранён в Мой диск.",
            "drive_url": reverse("drive:preview_file", kwargs={"file_id": df.uuid}),
        },
        status=201,
    )


@login_required
@require_POST
def delete_share_handler(request: HttpRequest, hash_id: str) -> HttpResponse:
    """Delete a share owned by the current user (or superuser)."""
    share = get_object_or_404(Share, hash_id=hash_id)
    if share.user != request.user and not request.user.is_superuser:
        if _is_ajax(request):
            return JsonResponse({"success": False, "error": "Нет прав на удаление этого шейра."}, status=403)
        return HttpResponse("Нет прав на удаление.", status=403)

    share.delete()
    redirect_url = reverse("accounts:profile", kwargs={"username": request.user.username})
    if _is_ajax(request):
        return JsonResponse({"success": True, "message": "Шейр удалён.", "redirect_url": redirect_url})
    messages.success(request, "Шейр удалён.")
    return redirect(redirect_url)


@login_required
@require_POST
def like_share_handler(request: HttpRequest, hash_id: str) -> JsonResponse:
    """Toggle user like on an active share."""
    share = get_object_or_404(Share, hash_id=hash_id)
    if share.is_expired:
        return JsonResponse({"success": False, "error": "Шейр истёк."}, status=410)
    if not _has_share_access(request, share):
        return JsonResponse({"success": False, "error": "Требуется разблокировка паролем."}, status=403)

    like, created = Like.objects.get_or_create(share=share, user=request.user)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True

    return JsonResponse(
        {
            "success": True,
            "liked": liked,
            "likes_count": share.likes.count(),
        }
    )


@require_POST
def report_share_handler(request: HttpRequest, hash_id: str) -> JsonResponse:
    """Submit an abuse/malware/copyright report against a share."""
    share = get_object_or_404(Share, hash_id=hash_id)
    if share.is_expired:
        return JsonResponse({"success": False, "error": "Шейр уже недоступен."}, status=410)

    data = request.POST
    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}

    form = ReportForm(
        {
            "reason": data.get("reason", "other"),
            "comment": (data.get("comment") or "").strip(),
        }
    )
    if not form.is_valid():
        return JsonResponse({"success": False, "error": "Некорректные данные жалобы."}, status=400)

    report = form.save(commit=False)
    report.share = share
    if request.user.is_authenticated:
        report.reporter = request.user
    report.save()

    return JsonResponse(
        {
            "success": True,
            "message": "Жалоба отправлена на рассмотрение модераторам.",
        },
        status=201,
    )
