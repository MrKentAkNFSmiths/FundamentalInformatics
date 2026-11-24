import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import FileAsset
from core.services import (
    detect_mime_type,
    fetch_remote_file,
    get_preview_category,
    sanitize_filename,
    sanitize_folder_name,
)
from drive.models import DriveFile, Folder
from shares.services import create_share_record


class CoreViewsTests(TestCase):
    def setUp(self) -> None:
        self.temp_media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.temp_media)
        self.override.enable()

    def tearDown(self) -> None:
        self.override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_home_page_anonymous_and_authenticated(self) -> None:
        resp = self.client.get(reverse("core:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "DataVax")

        user = User.objects.create_user(username="alice", email="a@example.com", password="Password123!")
        self.client.force_login(user)
        resp = self.client.get(reverse("core:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ваше хранилище")

    def test_api_docs_and_404(self) -> None:
        self.assertEqual(self.client.get(reverse("core:api_docs")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:info")).status_code, 200)
        resp_404 = self.client.get("/nonexistent-route-xyz/")
        self.assertEqual(resp_404.status_code, 404)


class CoreServicesTests(TestCase):
    def test_sanitize_filename_preserves_unicode_and_strips_traversal(self) -> None:
        self.assertEqual(sanitize_filename("../../Дядя миша.png"), "Дядя миша.png")
        self.assertEqual(sanitize_filename(".."), "file")

    def test_sanitize_folder_name_validation(self) -> None:
        self.assertEqual(sanitize_folder_name("  Анапа2014  "), "Анапа2014")
        with self.assertRaises(ValidationError):
            sanitize_folder_name("../secret")
        with self.assertRaises(ValidationError):
            sanitize_folder_name("a/b")

    def test_mime_and_preview_category_for_code_and_svg(self) -> None:
        self.assertEqual(detect_mime_type("main.py", "application/octet-stream"), "text/plain")
        self.assertEqual(get_preview_category("main.py", "application/octet-stream"), "code")
        self.assertEqual(get_preview_category("vector.svg", "image/svg+xml"), "code")

    def test_ssrf_blocks_loopback_and_link_local(self) -> None:
        with self.assertRaises(ValidationError):
            fetch_remote_file("http://127.0.0.1:8000/admin/", max_bytes=1024)
        with self.assertRaises(ValidationError):
            fetch_remote_file("http://169.254.169.254/latest/meta-data/", max_bytes=1024)
        with self.assertRaises(ValidationError):
            fetch_remote_file("file:///etc/passwd", max_bytes=1024)


class FileAssetReferenceCountingTests(TestCase):
    def setUp(self) -> None:
        self.temp_media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.temp_media)
        self.override.enable()
        self.user = User.objects.create_user(username="bobuser", email="bob@example.com", password="Password123!")

    def tearDown(self) -> None:
        self.override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_physical_file_kept_until_last_reference_deleted(self) -> None:
        root = Folder.ensure_root_for_user(self.user)
        asset = FileAsset.create_from_bytes(b"hello world", "hello.txt")
        file_path = asset.file.path

        df = DriveFile.objects.create(owner=self.user, folder=root, asset=asset, name="hello.txt")
        share = create_share_record(asset=asset, title="hello", user=self.user)

        df.delete()
        self.assertTrue(FileAsset.objects.filter(pk=asset.pk).exists())
        self.assertTrue(share.asset.file.storage.exists(asset.file.name))

        share.delete()
        self.assertFalse(FileAsset.objects.filter(pk=asset.pk).exists())
        self.assertFalse(asset.file.storage.exists(file_path))
