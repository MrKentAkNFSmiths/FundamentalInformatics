import io
import shutil
import tempfile
import zipfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile
from drive.models import DriveFile, Folder
from shares.models import Share


class DriveTests(TestCase):
    def setUp(self) -> None:
        self.temp_media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.temp_media)
        self.override.enable()
        self.user = User.objects.create_user(username="alice", email="alice@example.com", password="Password123!")
        self.other = User.objects.create_user(username="bobuser", email="bob@example.com", password="Password123!")
        self.root = Folder.ensure_root_for_user(self.user)
        self.client.force_login(self.user)

    def tearDown(self) -> None:
        self.override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_folder_crud_and_cycle_prevention(self) -> None:
        resp = self.client.post(
            reverse("drive:create_folder"),
            {"parent_uuid": str(self.root.uuid), "name": "Анапа2014"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 201)
        anapa = Folder.objects.get(owner=self.user, name="Анапа2014")

        resp_child = self.client.post(
            reverse("drive:create_folder"),
            {"parent_uuid": str(anapa.uuid), "name": "Фото"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp_child.status_code, 201)
        child = Folder.objects.get(owner=self.user, name="Фото")

        # Cannot move parent folder into its own descendant
        cycle_resp = self.client.post(
            reverse("drive:move_folder", kwargs={"folder_id": anapa.uuid}),
            {"target_uuid": str(child.uuid)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(cycle_resp.status_code, 400)

        # Rename folder
        ren_resp = self.client.post(
            reverse("drive:rename_folder", kwargs={"folder_id": child.uuid}),
            {"name": "Лето"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(ren_resp.status_code, 200)
        child.refresh_from_db()
        self.assertEqual(child.name, "Лето")

    def test_upload_deduplication_quota_and_zip_download(self) -> None:
        sub = Folder.objects.create(owner=self.user, parent=self.root, name="Проект")
        f1 = SimpleUploadedFile("main.py", b"print('hello')\n", content_type="text/x-python")
        f2 = SimpleUploadedFile("main.py", b"print('v2')\n", content_type="text/x-python")
        resp = self.client.post(
            reverse("drive:upload_files"),
            {"folder_uuid": str(sub.uuid), "files": [f1, f2]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 201)
        names = set(DriveFile.objects.filter(folder=sub).values_list("name", flat=True))
        self.assertEqual(names, {"main.py", "main (1).py"})

        # ZIP download includes nested folder and both files
        zip_resp = self.client.get(reverse("drive:download_folder_zip", kwargs={"folder_id": self.root.uuid}))
        self.assertEqual(zip_resp.status_code, 200)
        archive_bytes = b"".join(zip_resp.streaming_content)
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            members = set(zf.namelist())
            self.assertIn("Мой диск/Проект/main.py", members)
            self.assertIn("Мой диск/Проект/main (1).py", members)

        # Quota check
        profile = Profile.for_user(self.user)
        profile.storage_quota = 5
        profile.save()
        over_resp = self.client.post(
            reverse("drive:upload_files"),
            {"folder_uuid": str(self.root.uuid), "files": [SimpleUploadedFile("big.txt", b"1234567890")]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(over_resp.status_code, 400)

    def test_create_note_edit_star_share_and_ownership_isolation(self) -> None:
        create_resp = self.client.post(
            reverse("drive:create_note"),
            {"folder_uuid": str(self.root.uuid), "filename": "script.py", "content": "x = 1\n"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(create_resp.status_code, 201)
        df = DriveFile.objects.get(owner=self.user, name="script.py")

        # Update note content
        save_resp = self.client.post(
            reverse("drive:save_file_content", kwargs={"file_id": df.uuid}),
            {"content": "x = 42\n"},
        )
        self.assertEqual(save_resp.status_code, 200)
        df.refresh_from_db()
        with df.asset.file.open("rb") as fh:
            self.assertEqual(fh.read(), b"x = 42\n")

        # Star toggle
        star_resp = self.client.post(reverse("drive:toggle_star", kwargs={"file_id": df.uuid}))
        self.assertTrue(star_resp.json()["is_starred"])

        # Share from Drive
        share_resp = self.client.post(
            reverse("drive:share_file", kwargs={"file_id": df.uuid}),
            {"title": "My Script", "expire_preset": "1d", "password": "pw"},
        )
        self.assertEqual(share_resp.status_code, 201)
        hash_id = share_resp.json()["hash_id"]
        self.assertTrue(Share.objects.filter(hash_id=hash_id, source_drive_file=df).exists())

        # Isolation: other user cannot preview or delete alice's file
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(reverse("drive:preview_file", kwargs={"file_id": df.uuid})).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("drive:delete_file", kwargs={"file_id": df.uuid})).status_code,
            404,
        )

    def test_explorer_views_and_preview_rendering(self) -> None:
        df = DriveFile.objects.create(
            owner=self.user,
            folder=self.root,
            asset=self._make_asset(),
            name="readme.md",
            is_starred=True,
        )
        self.assertEqual(self.client.get(reverse("drive:root")).status_code, 200)
        self.assertEqual(self.client.get(reverse("drive:root") + "?filter=starred").status_code, 200)
        self.assertEqual(self.client.get(reverse("drive:root") + "?filter=recent").status_code, 200)
        self.assertEqual(self.client.get(reverse("drive:root") + "?q=readme").status_code, 200)
        preview_resp = self.client.get(reverse("drive:preview_file", kwargs={"file_id": df.uuid}))
        self.assertEqual(preview_resp.status_code, 200)
        self.assertContains(preview_resp, "readme.md")

    def _make_asset(self):
        from core.models import FileAsset

        return FileAsset.create_from_bytes(b"# Title\nhello", "readme.md")
