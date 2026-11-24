"""DRF serializers for Share upload/metadata and Drive REST API."""

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.models import FileAsset
from core.services import fetch_remote_file
from drive.models import DriveFile, Folder
from drive.services import unique_drive_filename, validate_upload_against_quota
from shares.models import Share
from shares.services import create_share_record, parse_expiration


class FileUploadSerializer(serializers.Serializer):
    """Validate file/URL upload and create a Share (and optional DriveFile)."""

    file = serializers.FileField(required=False, write_only=True)
    url = serializers.URLField(required=False, write_only=True)
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    password = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=255)
    expires = serializers.IntegerField(required=False, min_value=1, max_value=720)
    is_anonymous = serializers.BooleanField(required=False, default=False)
    save_to_drive = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        uploaded_file = attrs.get("file")
        remote_url = attrs.get("url")
        if not uploaded_file and not remote_url:
            raise serializers.ValidationError("Требуется либо file, либо url.")
        if uploaded_file and remote_url:
            raise serializers.ValidationError("Укажите только file или только url.")
        if uploaded_file and uploaded_file.size > settings.DATAVAX_MAX_FILE_SIZE_BYTES:
            max_mb = settings.DATAVAX_MAX_FILE_SIZE_MB
            raise serializers.ValidationError(f"Максимальный размер файла — {max_mb} МБ.")
        return attrs

    def create(self, validated_data) -> Share:
        request = self.context.get("request")
        user = request.user if (request and request.user.is_authenticated) else None

        uploaded_file = validated_data.get("file")
        remote_url = validated_data.get("url")
        title = (validated_data.get("title") or "").strip()

        if uploaded_file is not None:
            asset = FileAsset.create_from_uploaded(uploaded_file)
            if not title:
                title = uploaded_file.name
        else:
            try:
                data, filename, mime_type = fetch_remote_file(
                    remote_url,
                    max_bytes=settings.DATAVAX_MAX_FILE_SIZE_BYTES,
                )
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"url": exc.message}) from exc
            asset = FileAsset.create_from_bytes(data, filename=filename, declared_mime=mime_type)
            if not title:
                title = filename

        expires_hours = validated_data.get("expires", 24)
        expire_date = parse_expiration(expires_hours=expires_hours)

        share = create_share_record(
            asset=asset,
            title=title,
            description=validated_data.get("description", ""),
            user=user,
            is_anonymous=validated_data.get("is_anonymous", False),
            password=validated_data.get("password"),
            expire_date=expire_date,
        )

        if validated_data.get("save_to_drive") and user is not None:
            try:
                validate_upload_against_quota(user, asset.size)
                root = Folder.ensure_root_for_user(user)
                drive_name = unique_drive_filename(root, asset.original_name)
                DriveFile.objects.create(owner=user, folder=root, asset=asset, name=drive_name)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"save_to_drive": exc.message}) from exc

        return share


class ShareMetadataSerializer(serializers.ModelSerializer):
    """Public metadata serializer for Share objects."""

    author = serializers.SerializerMethodField()
    filename = serializers.CharField(source="asset.original_name", read_only=True)
    size = serializers.IntegerField(source="asset.size", read_only=True)
    mime_type = serializers.CharField(source="asset.mime_type", read_only=True)
    has_password = serializers.BooleanField(read_only=True)
    likes_count = serializers.SerializerMethodField()

    class Meta:
        model = Share
        fields = [
            "hash_id",
            "title",
            "description",
            "author",
            "filename",
            "size",
            "mime_type",
            "has_password",
            "views_count",
            "downloads_count",
            "likes_count",
            "expire_date",
            "created_at",
        ]

    def get_author(self, obj: Share) -> str:
        return obj.display_author

    def get_likes_count(self, obj: Share) -> int:
        return obj.likes.count()


class DriveFolderSerializer(serializers.ModelSerializer):
    """Serializer for Drive folders."""

    path = serializers.SerializerMethodField()

    class Meta:
        model = Folder
        fields = ["uuid", "name", "is_root", "path", "created_at", "updated_at"]

    def get_path(self, obj: Folder) -> str:
        return obj.get_virtual_path()


class DriveFileSerializer(serializers.ModelSerializer):
    """Serializer for Drive files."""

    size = serializers.IntegerField(source="asset.size", read_only=True)
    mime_type = serializers.CharField(source="asset.mime_type", read_only=True)
    folder_uuid = serializers.UUIDField(source="folder.uuid", read_only=True)

    class Meta:
        model = DriveFile
        fields = ["uuid", "name", "folder_uuid", "size", "mime_type", "is_starred", "created_at", "updated_at"]
