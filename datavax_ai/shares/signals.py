"""Signals for cleaning up unreferenced physical assets when Share rows are deleted."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from core.models import FileAsset
from shares.models import Share


@receiver(post_delete, sender=Share)
def cleanup_asset_after_share_delete(sender, instance: Share, **kwargs) -> None:
    """Remove physical FileAsset when no DriveFile or Share references it."""
    if instance.asset_id:
        asset = FileAsset.objects.filter(pk=instance.asset_id).first()
        if asset:
            asset.delete_if_unreferenced()
