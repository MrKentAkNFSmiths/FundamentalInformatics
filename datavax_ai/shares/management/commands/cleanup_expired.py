"""Management command to remove expired shares and unreferenced physical assets."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from shares.models import Share


class Command(BaseCommand):
    help = "Delete expired shares and clean up unreferenced file assets."

    def handle(self, *args, **options) -> None:
        now = timezone.now()
        expired = Share.objects.filter(expire_date__isnull=False, expire_date__lte=now)
        count = expired.count()
        for share in expired:
            share.delete()
        self.stdout.write(self.style.SUCCESS(f"Удалено просроченных шейров: {count}"))
