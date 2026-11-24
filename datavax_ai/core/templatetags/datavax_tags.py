"""Custom template filters for DataVax."""

from django import template

from core.services import get_extension, get_preview_category

register = template.Library()


@register.filter
def format_bytes(value) -> str:
    """Format byte count into human-readable Russian unit string."""
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        return "0 Б"
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
    idx = 0
    while num >= 1024 and idx < len(units) - 1:
        num /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(num)} {units[idx]}"
    return f"{num:.1f} {units[idx]}"


@register.filter
def file_ext(filename: str) -> str:
    """Return short uppercase extension badge for a file."""
    ext = get_extension(filename or "")
    return (ext[:5] if ext else "FILE").upper()


@register.simple_tag
def file_kind(filename: str, mime_type: str = "") -> str:
    """Return preview category string for icons/badges."""
    return get_preview_category(filename, mime_type)
