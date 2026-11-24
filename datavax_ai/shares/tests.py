import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import FileAsset
from drive.models import DriveFile
from shares.models import Like, Report, Share
from shares.services import create_share_record


class SharesTests(TestCase):
    def setUp(self) -> None:
        self.temp_media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.temp_media)
        self.override.enable()
        self.user = User.objects.create_user(username="alice", email="alice@example.com", password="Password123!")
        self.other = User.objects.create_user(username="bobuser", email="bob@example.com", password="Password123!")

    def tearDown(self) -> None:
        self.override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_authenticated_user_can_create_explicit_anonymous_share_and_save_to_drive(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("shares:upload"),
            {
                "title": "Anon Snippet",
                "code_content": "<script>alert(1)</script>",
                "language": "text",
                "expire_preset": "1d",
                "is_anonymous": "true",
                "save_to_drive": "true",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 201)
        hash_id = resp.json()["hash_id"]
        share = Share.objects.get(hash_id=hash_id)
        self.assertTrue(share.is_anonymous)
        self.assertEqual(share.display_author, "Аноним")
        self.assertEqual(DriveFile.objects.filter(owner=self.user).count(), 1)

        # XSS protection: HTML tags in text preview must be escaped, never raw
        detail_resp = self.client.get(reverse("shares:detail", kwargs={"hash_id": hash_id}))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertNotContains(detail_resp, "<script>alert(1)</script>")
        self.assertContains(detail_resp, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_password_protection_hashed_and_enforced_on_raw_and_download(self) -> None:
        asset = FileAsset.create_from_bytes(b"top secret bytes", "secret.txt")
        share = create_share_record(asset=asset, title="Secret", password="my-secret-password", user=self.user)
        self.assertNotEqual(share.password_hash, "my-secret-password")
        self.assertTrue(share.verify_password("my-secret-password"))

        # Raw stream blocked before unlock
        self.assertEqual(self.client.get(reverse("shares:raw", kwargs={"hash_id": share.hash_id})).status_code, 403)
        # Wrong password rejected
        wrong = self.client.post(
            reverse("shares:detail", kwargs={"hash_id": share.hash_id}),
            {"password": "wrong"},
        )
        self.assertContains(wrong, "Неверный пароль")

        # Correct password unlocks session
        ok = self.client.post(
            reverse("shares:detail", kwargs={"hash_id": share.hash_id}),
            {"password": "my-secret-password"},
        )
        self.assertRedirects(ok, reverse("shares:detail", kwargs={"hash_id": share.hash_id}))
        self.assertEqual(self.client.get(reverse("shares:raw", kwargs={"hash_id": share.hash_id})).status_code, 200)

        dl_resp = self.client.get(reverse("shares:download", kwargs={"hash_id": share.hash_id}))
        self.assertEqual(dl_resp.status_code, 200)
        self.assertEqual(b"".join(dl_resp.streaming_content), b"top secret bytes")
        share.refresh_from_db()
        self.assertEqual(share.downloads_count, 1)

    def test_expired_share_returns_410_and_cleanup_command_removes_it(self) -> None:
        asset = FileAsset.create_from_bytes(b"old data", "old.txt")
        share = create_share_record(
            asset=asset,
            title="Expired",
            expire_date=timezone.now() - timedelta(minutes=5),
        )
        self.assertEqual(self.client.get(reverse("shares:detail", kwargs={"hash_id": share.hash_id})).status_code, 410)
        self.assertEqual(self.client.get(reverse("shares:raw", kwargs={"hash_id": share.hash_id})).status_code, 410)
        self.assertEqual(
            self.client.get(reverse("shares:download", kwargs={"hash_id": share.hash_id})).status_code, 410
        )

        call_command("cleanup_expired")
        self.assertFalse(Share.objects.filter(pk=share.pk).exists())
        self.assertFalse(FileAsset.objects.filter(pk=asset.pk).exists())

    def test_like_report_save_to_drive_and_delete(self) -> None:
        asset = FileAsset.create_from_bytes(b"print(123)", "demo.py")
        share = create_share_record(asset=asset, title="Demo", user=self.user)

        # Unauthenticated report works cleanly
        rep = self.client.post(
            reverse("shares:report", kwargs={"hash_id": share.hash_id}),
            {"reason": "spam", "comment": "Test report"},
        )
        self.assertEqual(rep.status_code, 201)
        self.assertEqual(Report.objects.filter(share=share).count(), 1)

        # Authenticated other user can like & save to Drive, cannot delete
        self.client.force_login(self.other)
        like1 = self.client.post(reverse("shares:like", kwargs={"hash_id": share.hash_id}))
        self.assertEqual(like1.json()["likes_count"], 1)
        self.assertEqual(Like.objects.count(), 1)
        like2 = self.client.post(reverse("shares:like", kwargs={"hash_id": share.hash_id}))
        self.assertEqual(like2.json()["likes_count"], 0)

        save_resp = self.client.post(reverse("shares:save_to_drive", kwargs={"hash_id": share.hash_id}))
        self.assertEqual(save_resp.status_code, 201)
        self.assertEqual(DriveFile.objects.filter(owner=self.other).count(), 1)

        del_forbidden = self.client.post(reverse("shares:delete", kwargs={"hash_id": share.hash_id}))
        self.assertEqual(del_forbidden.status_code, 403)

        # Owner deletes share
        self.client.force_login(self.user)
        del_ok = self.client.post(reverse("shares:delete", kwargs={"hash_id": share.hash_id}))
        self.assertEqual(del_ok.status_code, 302)
        self.assertFalse(Share.objects.filter(pk=share.pk).exists())

    def test_legacy_post_route_and_file_upload(self) -> None:
        resp = self.client.post(
            reverse("shares:upload"),
            {
                "title": "LegacyFile",
                "uploaded_file": SimpleUploadedFile("note.txt", b"hello"),
                "expire_date": "2099-12-31",
            },
        )
        self.assertEqual(resp.status_code, 302)
        share = Share.objects.get(title="LegacyFile")
        self.assertEqual(
            self.client.get(reverse("shares:legacy_detail", kwargs={"hash_id": share.hash_id})).status_code,
            200,
        )

    def test_new_editor_and_admin_render(self) -> None:
        self.assertEqual(self.client.get(reverse("shares:new")).status_code, 200)
        admin_user = User.objects.create_superuser(
            username="rootadmin", email="adm@example.com", password="Password123!"
        )
        self.client.force_login(admin_user)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
