"""Core utility services for file handling, MIME/code detection, and SSRF-safe fetching."""

from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import os
import re
import secrets
import socket
import string
from urllib.parse import quote, unquote, urlparse

import requests
from django.core.exceptions import ValidationError
from django.http import FileResponse

HASH_ALPHABET = string.ascii_lowercase + string.digits

CODE_EXTENSION_MODES: dict[str, str] = {
    "py": "python",
    "pyw": "python",
    "js": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "ts": "javascript",
    "jsx": "javascript",
    "tsx": "javascript",
    "html": "htmlmixed",
    "htm": "htmlmixed",
    "xml": "xml",
    "svg": "xml",
    "css": "css",
    "scss": "css",
    "go": "go",
    "c": "text/x-csrc",
    "h": "text/x-csrc",
    "cpp": "text/x-c++src",
    "cc": "text/x-c++src",
    "cxx": "text/x-c++src",
    "hpp": "text/x-c++src",
    "java": "text/x-java",
    "rs": "rust",
    "sql": "sql",
    "sh": "shell",
    "bash": "shell",
    "zsh": "shell",
    "json": "application/json",
    "yml": "text/x-yaml",
    "yaml": "text/x-yaml",
    "md": "markdown",
    "markdown": "markdown",
    "ini": "properties",
    "toml": "properties",
    "env": "properties",
    "dockerfile": "shell",
}

PLAIN_TEXT_EXTENSIONS = {"txt", "log", "csv", "tsv", "rst", "conf", "cfg"}

SUPPORTED_FORMAT_GROUPS = [
    {
        "title": "Изображения",
        "items": ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"],
    },
    {
        "title": "Код и текст",
        "items": ["py", "js", "ts", "html", "css", "go", "c/cpp", "java", "sql", "json", "yml", "md", "txt"],
    },
    {
        "title": "Видео и аудио",
        "items": ["mp4", "webm", "mov", "mkv", "mp3", "wav", "ogg", "flac"],
    },
    {
        "title": "Документы и архивы",
        "items": ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip", "rar", "7z", "tar", "gz"],
    },
]


def sanitize_filename(name: str, default: str = "file") -> str:
    """Return a safe single-segment filename preserving Unicode characters."""
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    base = re.sub(r"[\x00-\x1f\x7f<>:\"/\\|?*]+", "_", base)
    base = base.strip(". ")
    if not base:
        return default
    if len(base) > 200:
        stem, ext = os.path.splitext(base)
        base = f"{stem[: 200 - len(ext)]}{ext}"
    return base


def sanitize_folder_name(name: str) -> str:
    """Validate and normalize a folder name."""
    cleaned = (name or "").strip()
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", "", cleaned)
    if not cleaned or cleaned in (".", ".."):
        raise ValidationError("Некорректное имя папки.")
    if any(sep in cleaned for sep in ("/", "\\")):
        raise ValidationError("Имя папки не может содержать символы '/' или '\\'.")
    if len(cleaned) > 120:
        raise ValidationError("Имя папки не должно превышать 120 символов.")
    return cleaned


def generate_unique_hash_id(model_cls, field_name: str = "hash_id", length: int = 8) -> str:
    """Generate a unique URL-safe identifier not present in model_cls."""
    for _ in range(25):
        candidate = "".join(secrets.choice(HASH_ALPHABET) for _ in range(length))
        if not model_cls.objects.filter(**{field_name: candidate}).exists():
            return candidate
    raise RuntimeError("Failed to generate unique hash_id")


def get_extension(filename: str) -> str:
    """Extract lowercase file extension without leading dot."""
    if not filename or "." not in filename:
        base = os.path.basename(filename or "").lower()
        return base if base == "dockerfile" else ""
    return filename.rsplit(".", 1)[-1].lower()


def detect_mime_type(filename: str, declared_mime: str | None = None) -> str:
    """Determine reliable MIME type for a filename and optional declared content-type."""
    ext = get_extension(filename)
    if ext in CODE_EXTENSION_MODES or ext in PLAIN_TEXT_EXTENSIONS:
        if ext == "svg":
            return "image/svg+xml"
        if ext == "json":
            return "application/json"
        return "text/plain"

    if declared_mime and declared_mime not in ("application/octet-stream", "binary/octet-stream", ""):
        return declared_mime.split(";")[0].strip().lower()

    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed.lower()

    if declared_mime:
        return declared_mime.split(";")[0].strip().lower()
    return "application/octet-stream"


def get_code_language(filename: str) -> str:
    """Return CodeMirror mode name for a filename or 'text/plain'."""
    ext = get_extension(filename)
    return CODE_EXTENSION_MODES.get(ext, "text/plain")


def get_preview_category(filename: str, mime_type: str | None) -> str:
    """Categorize how a file should be previewed in the UI."""
    ext = get_extension(filename)
    mime = (mime_type or "").lower()

    # Do not render untrusted uploaded SVG inline as HTML; show via <img> or code
    if mime.startswith("image/") and ext != "svg":
        return "image"
    if ext == "svg":
        return "code"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime == "application/pdf" or ext == "pdf":
        return "pdf"
    if ext in CODE_EXTENSION_MODES:
        return "code"
    if mime.startswith("text/") or ext in PLAIN_TEXT_EXTENSIONS or mime == "application/json":
        return "text"
    return "binary"


def read_text_preview(file_field, max_bytes: int = 512 * 1024) -> tuple[str, bool]:
    """Read up to max_bytes from a text FileField safely."""
    try:
        with file_field.open("rb") as fh:
            raw = fh.read(max_bytes + 1)
        truncated = len(raw) > max_bytes
        if truncated:
            raw = raw[:max_bytes]
        return raw.decode("utf-8", errors="replace"), truncated
    except OSError:
        return "Не удалось прочитать содержимое файла.", False


def compute_sha256_bytes(data: bytes) -> str:
    """Return hex SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def _validate_public_ip(hostname: str) -> None:
    """Reject localhost, private, link-local, loopback, and reserved IP targets (SSRF protection)."""
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValidationError("Не удалось разрешить доменное имя URL.") from exc

    if not addr_info:
        raise ValidationError("Не удалось определить IP-адрес хоста.")

    for entry in addr_info:
        ip_str = entry[4][0]
        # Strip IPv6 scope ID if present
        ip_str = ip_str.split("%")[0]
        ip_obj = ipaddress.ip_address(ip_str)
        if not ip_obj.is_global:
            raise ValidationError("Доступ к локальным или внутренним сетевым адресам запрещён.")


def fetch_remote_file(url: str, max_bytes: int, timeout: int = 10) -> tuple[bytes, str, str]:
    """Download a remote file safely with SSRF checks and streaming byte limits."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValidationError("Поддерживаются только корректные HTTP/HTTPS ссылки.")

    _validate_public_ip(parsed.hostname)

    current_url = url
    response = None
    for _ in range(4):
        current_parsed = urlparse(current_url)
        if current_parsed.scheme not in ("http", "https") or not current_parsed.hostname:
            raise ValidationError("Некорректный URL перенаправления.")
        _validate_public_ip(current_parsed.hostname)
        try:
            response = requests.get(
                current_url,
                stream=True,
                timeout=timeout,
                allow_redirects=False,
                headers={"User-Agent": "DataVax-Fetcher/2.0"},
            )
        except requests.RequestException as exc:
            raise ValidationError(f"Ошибка загрузки URL: {exc}") from exc

        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValidationError("Некорректное перенаправление при загрузке URL.")
            current_url = requests.compat.urljoin(current_url, location)
            continue
        break
    else:
        raise ValidationError("Слишком много перенаправлений при загрузке URL.")

    assert response is not None
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        response.close()
        raise ValidationError(f"Сервер вернул ошибку: {exc}") from exc

    content_length = response.headers.get("Content-Length")
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        response.close()
        raise ValidationError("Размер файла по URL превышает допустимый лимит.")

    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValidationError("Размер файла по URL превышает допустимый лимит.")
            chunks.append(chunk)
    finally:
        response.close()

    raw_name = unquote(urlparse(current_url).path.rsplit("/", 1)[-1]) or "downloaded_file"
    filename = sanitize_filename(raw_name, default="downloaded_file")
    declared_mime = response.headers.get("Content-Type", "")
    mime_type = detect_mime_type(filename, declared_mime)
    return b"".join(chunks), filename, mime_type


def build_file_response(
    file_field,
    filename: str,
    mime_type: str | None = None,
    as_attachment: bool = True,
) -> FileResponse:
    """Create a FileResponse with safe UTF-8 Content-Disposition and nosniff header."""
    safe_name = sanitize_filename(filename)
    resolved_mime = mime_type or detect_mime_type(safe_name)
    # Force attachment for active web documents when served directly
    if not as_attachment and resolved_mime in ("text/html", "application/xhtml+xml", "image/svg+xml"):
        resolved_mime = "text/plain; charset=utf-8"

    fh = file_field.open("rb")
    response = FileResponse(fh, content_type=resolved_mime, as_attachment=as_attachment)
    disposition = "attachment" if as_attachment else "inline"
    ascii_fallback = safe_name.encode("ascii", "ignore").decode("ascii") or "file"
    response["Content-Disposition"] = (
        f'{disposition}; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(safe_name)}'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
