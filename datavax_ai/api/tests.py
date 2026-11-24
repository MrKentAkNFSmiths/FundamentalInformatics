import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from drive.models import DriveFile, Folder
from shares.models import Share


class ApiTests(TestCase):
    def setUp(self) -> None:
        self.temp_media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.temp_media)
        self.override.enable()
        self.user = User.objects.create_user(username="alice", email="alice@example.com", password="Password123!")

    def tearDown(self) -> None:
        self.override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_upload_and_download_with_password_and_plain_mode(self) -> None:
        resp = self.client.post(
            reverse("api:upload"),
            {
                "file": SimpleUploadedFile("hello.py", b"print('api')\n"),
                "title": "API Upload",
                "password": "secret",
                "expires": 12,
            },
        )
        self.assertEqual(resp.status_code, 201)
        payload = resp.json()
        hash_id = payload["hash_id"]

        # Metadata & download require password
        self.assertEqual(self.client.get(reverse("api:share_detail", kwargs={"hash_id": hash_id})).status_code, 403)
        self.assertEqual(self.client.get(reverse("api:download", kwargs={"hash_id": hash_id})).status_code, 403)

        dl_ok = self.client.get(
            reverse("api:download", kwargs={"hash_id": hash_id}),
            HTTP_X_SHARE_PASSWORD="secret",
        )
        self.assertEqual(dl_ok.status_code, 200)
        self.assertEqual(b"".join(dl_ok.streaming_content), b"print('api')\n")

        # Plain text CLI mode
        plain_resp = self.client.post(
            reverse("api:upload") + "?plain=1",
            {"file": SimpleUploadedFile("cli.txt", b"cli"), "title": "CLI"},
        )
        self.assertEqual(plain_resp.status_code, 201)
        self.assertIn("/s/", plain_resp.content.decode("utf-8"))

        # Expired share returns 410 via API
        share = Share.objects.get(hash_id=hash_id)
        share.expire_date = timezone.now() - timedelta(minutes=1)
        share.save()
        self.assertEqual(self.client.get(reverse("api:download", kwargs={"hash_id": hash_id})).status_code, 410)

    def test_api_ssrf_url_rejected(self) -> None:
        resp = self.client.post(
            reverse("api:upload"),
            {"url": "http://127.0.0.1:8080/internal", "title": "SSRF"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_drive_api_requires_auth_and_creates_folder_and_file(self) -> None:
        self.assertEqual(self.client.get(reverse("api:drive_root")).status_code, 403)

        self.client.force_login(self.user)
        folder_resp = self.client.post(reverse("api:drive_root"), {"name": "API_Folder"})
        self.assertEqual(folder_resp.status_code, 201)
        folder_uuid = folder_resp.json()["uuid"]

        upload_resp = self.client.post(
            reverse("api:drive_upload"),
            {"folder_uuid": folder_uuid, "file": SimpleUploadedFile("data.json", b'{"ok":true}')},
        )
        self.assertEqual(upload_resp.status_code, 201)
        self.assertEqual(DriveFile.objects.filter(owner=self.user, name="data.json").count(), 1)
        self.assertTrue(Folder.objects.filter(owner=self.user, uuid=folder_uuid).exists())
