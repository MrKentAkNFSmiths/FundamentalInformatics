"""REST API views for Shares and personal Drive operations."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import (
    DriveFileSerializer,
    DriveFolderSerializer,
    FileUploadSerializer,
    ShareMetadataSerializer,
)
from core.models import FileAsset
from core.services import build_file_response, sanitize_folder_name
from drive.models import DriveFile, Folder
from drive.services import unique_drive_filename, validate_upload_against_quota
from shares.models import Share


def _extract_password(request) -> str:
    return request.headers.get("X-Share-Password") or request.GET.get("password", "")


class FileUploadView(APIView):
    """Upload a file or fetch a URL to create a Share."""

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request) -> Response | HttpResponse:
        serializer = FileUploadSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        share = serializer.save()
        share_url = request.build_absolute_uri(reverse("shares:detail", kwargs={"hash_id": share.hash_id}))
        download_url = request.build_absolute_uri(reverse("api:download", kwargs={"hash_id": share.hash_id}))

        wants_plain = request.GET.get("plain") == "1" or "text/plain" in request.headers.get("Accept", "")
        if wants_plain:
            return HttpResponse(content=f"{share_url}\n", content_type="text/plain", status=status.HTTP_201_CREATED)

        return Response(
            {
                "hash_id": share.hash_id,
                "title": share.title,
                "url": share_url,
                "download_url": download_url,
                "expire_date": share.expire_date,
            },
            status=status.HTTP_201_CREATED,
        )


class DownloadFileView(APIView):
    """Download a Share's file via REST API with expiration and hashed password checks."""

    def get(self, request, hash_id: str):
        share = get_object_or_404(Share.objects.select_related("asset"), hash_id=hash_id)
        if share.is_expired:
            return Response({"error": "Share link has expired."}, status=status.HTTP_410_GONE)

        if share.has_password:
            provided = _extract_password(request)
            if not share.verify_password(provided):
                return Response({"error": "Invalid or missing password."}, status=status.HTTP_403_FORBIDDEN)

        Share.objects.filter(pk=share.pk).update(downloads_count=F("downloads_count") + 1)
        return build_file_response(
            share.asset.file,
            share.asset.original_name,
            share.asset.mime_type,
            as_attachment=True,
        )


class ShareDetailApiView(APIView):
    """Inspect metadata or delete an owned Share via REST API."""

    def get(self, request, hash_id: str) -> Response:
        share = get_object_or_404(Share.objects.select_related("asset", "user"), hash_id=hash_id)
        if share.is_expired:
            return Response({"error": "Share link has expired."}, status=status.HTTP_410_GONE)

        if share.has_password and not share.verify_password(_extract_password(request)):
            return Response(
                {"hash_id": share.hash_id, "has_password": True, "error": "Password required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(ShareMetadataSerializer(share).data)

    def delete(self, request, hash_id: str) -> Response:
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        share = get_object_or_404(Share, hash_id=hash_id)
        if share.user != request.user and not request.user.is_superuser:
            return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
        share.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DriveFolderApiView(APIView):
    """List folder contents or create a subfolder in the authenticated user's Drive."""

    permission_classes = [IsAuthenticated]

    def get(self, request, folder_id=None) -> Response:
        if folder_id is not None:
            folder = get_object_or_404(Folder, uuid=folder_id, owner=request.user)
        else:
            folder = Folder.ensure_root_for_user(request.user)

        subfolders = folder.subfolders.all().order_by("name")
        files = folder.files.select_related("asset").order_by("-updated_at")
        return Response(
            {
                "folder": DriveFolderSerializer(folder).data,
                "subfolders": DriveFolderSerializer(subfolders, many=True).data,
                "files": DriveFileSerializer(files, many=True).data,
            }
        )

    def post(self, request, folder_id=None) -> Response:
        if folder_id is not None:
            parent = get_object_or_404(Folder, uuid=folder_id, owner=request.user)
        else:
            parent = Folder.ensure_root_for_user(request.user)

        try:
            name = sanitize_folder_name(request.data.get("name", ""))
        except DjangoValidationError as exc:
            return Response({"error": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        if Folder.objects.filter(owner=request.user, parent=parent, name=name).exists():
            return Response({"error": "Folder already exists."}, status=status.HTTP_400_BAD_REQUEST)

        created = Folder.objects.create(owner=request.user, parent=parent, name=name, is_root=False)
        return Response(DriveFolderSerializer(created).data, status=status.HTTP_201_CREATED)


class DriveUploadApiView(APIView):
    """Upload a file directly into the authenticated user's Drive folder."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request) -> Response:
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response({"error": "Missing 'file' upload."}, status=status.HTTP_400_BAD_REQUEST)

        folder_uuid = request.data.get("folder_uuid")
        if folder_uuid:
            folder = get_object_or_404(Folder, uuid=folder_uuid, owner=request.user)
        else:
            folder = Folder.ensure_root_for_user(request.user)

        try:
            validate_upload_against_quota(request.user, uploaded_file.size)
        except DjangoValidationError as exc:
            return Response({"error": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        unique_name = unique_drive_filename(folder, uploaded_file.name)
        asset = FileAsset.create_from_uploaded(uploaded_file, filename=unique_name)
        drive_file = DriveFile.objects.create(owner=request.user, folder=folder, asset=asset, name=unique_name)
        return Response(DriveFileSerializer(drive_file).data, status=status.HTTP_201_CREATED)
