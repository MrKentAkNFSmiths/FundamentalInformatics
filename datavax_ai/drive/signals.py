"""Signals for cleaning up unreferenced physical assets when DriveFile rows are deleted."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from core.models import FileAsset
from drive.models import DriveFile


@receiver(post_delete, sender=DriveFile)
def cleanup_asset_after_drive_file_delete(sender, instance: DriveFile, **kwargs) -> None:
    """Remove physical FileAsset when no DriveFile or Share references it."""
    if instance.asset_id:
        asset = FileAsset.objects.filter(pk=instance.asset_id).first()
        if asset:
            asset.delete_if_unreferenced()
