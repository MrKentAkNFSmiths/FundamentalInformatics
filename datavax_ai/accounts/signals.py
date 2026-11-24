"""Signals to provision Profile and root Drive folder automatically for new users."""

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Profile


@receiver(post_save, sender=User)
def provision_user_workspace(sender, instance: User, created: bool, **kwargs) -> None:
    """Create Profile and root Drive folder when a User is created."""
    if created:
        Profile.objects.get_or_create(user=instance)
        from drive.models import Folder

        Folder.ensure_root_for_user(instance)
