"""Service helpers for creating and validating shares."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from core.models import FileAsset
from core.services import generate_unique_hash_id
from shares.models import Share

EXPIRATION_PRESETS: dict[str, timedelta | None] = {
    "10m": timedelta(minutes=10),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "1w": timedelta(days=7),
    "1m": timedelta(days=30),
    "never": None,
}


def parse_bool_flag(value) -> bool:
    """Parse checkbox/JS/API boolean representations consistently."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "on", "yes")


def parse_expiration(
    expire_preset: str | None = None,
    expire_date_str: str | None = None,
    expires_hours: int | None = None,
) -> datetime | None:
    """Resolve expiration datetime from preset, hours, or ISO/date string."""
    now = timezone.now()

    if expires_hours is not None:
        return now + timedelta(hours=int(expires_hours))

    if expire_preset is not None:
        preset = expire_preset.strip().lower()
        if preset in EXPIRATION_PRESETS:
            delta = EXPIRATION_PRESETS[preset]
            return now + delta if delta is not None else None

    if expire_date_str:
        raw = expire_date_str.strip()
        if raw.lower() in EXPIRATION_PRESETS:
            delta = EXPIRATION_PRESETS[raw.lower()]
            return now + delta if delta is not None else None

        dt = parse_datetime(raw)
        if dt is not None:
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt

        d = parse_date(raw)
        if d is not None:
            dt = datetime.combine(d, time(23, 59, 59))
            return timezone.make_aware(dt, timezone.get_current_timezone())

    return now + timedelta(days=1)


def create_share_record(
    *,
    asset: FileAsset,
    title: str,
    description: str = "",
    user: User | None = None,
    is_anonymous: bool = False,
    password: str | None = None,
    expire_date: datetime | None = None,
    source_drive_file=None,
) -> Share:
    """Create a Share with unique hash_id and securely hashed optional password."""
    resolved_user = user if (user is not None and user.is_authenticated) else None
    resolved_anonymous = True if resolved_user is None else bool(is_anonymous)
    hash_id = generate_unique_hash_id(Share, length=8)

    share = Share(
        hash_id=hash_id,
        user=resolved_user,
        source_drive_file=source_drive_file,
        asset=asset,
        title=(title or asset.original_name).strip()[:255],
        description=(description or "").strip(),
        is_anonymous=resolved_anonymous,
        expire_date=expire_date,
    )
    share.set_password(password)
    share.save()
    return share
