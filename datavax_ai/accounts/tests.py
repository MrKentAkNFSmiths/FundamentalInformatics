import shutil
import tempfile
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import Profile
from core.models import FileAsset
from drive.models import Folder
from shares.services import create_share_record


def _make_png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (16, 16), color=(56, 189, 248)).save(buf, format="PNG")
    return buf.getvalue()


class AccountsTests(TestCase):
    def setUp(self) -> None:
        self.temp_media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.temp_media)
        self.override.enable()
        self.user = User.objects.create_user(username="alice", email="alice@example.com", password="Password123!")
        self.other = User.objects.create_user(username="bobuser", email="bob@example.com", password="Password123!")

    def tearDown(self) -> None:
        self.override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_registration_provisions_profile_and_root_folder(self) -> None:
        resp = self.client.post(
            reverse("accounts:sign_up"),
            {
                "username": "charlie",
                "email": "charlie@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertRedirects(resp, reverse("drive:root"))
        created = User.objects.get(username="charlie")
        self.assertTrue(Profile.objects.filter(user=created).exists())
        self.assertTrue(Folder.objects.filter(owner=created, is_root=True).exists())

    def test_registration_rejects_duplicate_and_mismatch(self) -> None:
        resp = self.client.post(
            reverse("accounts:sign_up"),
            {
                "username": "alice",
                "email": "new@example.com",
                "password1": "StrongPass123!",
                "password2": "OtherPass123!",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_login_and_logout(self) -> None:
        resp = self.client.post(
            reverse("accounts:sign_in"),
            {"username": "alice", "password": "Password123!"},
        )
        self.assertRedirects(resp, reverse("drive:root"))
        resp_out = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(resp_out, reverse("core:home"))

    def test_profile_hides_anonymous_shares_from_other_users(self) -> None:
        asset = FileAsset.create_from_bytes(b"secret", "secret.txt")
        create_share_record(asset=asset, title="PublicTitle", user=self.user, is_anonymous=False)
        create_share_record(asset=asset, title="HiddenAnonTitle", user=self.user, is_anonymous=True)

        guest_resp = self.client.get(reverse("accounts:profile", kwargs={"username": "alice"}))
        self.assertEqual(guest_resp.status_code, 200)
        self.assertContains(guest_resp, "PublicTitle")
        self.assertNotContains(guest_resp, "HiddenAnonTitle")

        self.client.force_login(self.user)
        owner_resp = self.client.get(reverse("accounts:profile", kwargs={"username": "alice"}))
        self.assertContains(owner_resp, "HiddenAnonTitle")

    def test_avatar_upload_validation_and_permissions(self) -> None:
        self.client.force_login(self.user)

        bad_avatar = SimpleUploadedFile("bad.png", b"not-an-image", content_type="image/png")
        bad_resp = self.client.post(
            reverse("accounts:upload_avatar", kwargs={"username": "alice"}),
            {"avatar": bad_avatar},
        )
        self.assertEqual(bad_resp.status_code, 400)

        good_avatar = SimpleUploadedFile("ok.png", _make_png_bytes(), content_type="image/png")
        good_resp = self.client.post(
            reverse("accounts:upload_avatar", kwargs={"username": "alice"}),
            {"avatar": good_avatar},
        )
        self.assertEqual(good_resp.status_code, 200)
        self.assertTrue(good_resp.json()["success"])

        # Other user cannot overwrite alice's avatar
        self.client.force_login(self.other)
        forbidden = self.client.post(
            reverse("accounts:upload_avatar", kwargs={"username": "alice"}),
            {"avatar": SimpleUploadedFile("ok2.png", _make_png_bytes(), content_type="image/png")},
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_update_nickname_uniqueness_and_bio(self) -> None:
        self.client.force_login(self.user)
        dup_resp = self.client.post(
            reverse("accounts:update_profile", kwargs={"username": "alice"}),
            {"nickname": "bobuser"},
        )
        self.assertEqual(dup_resp.status_code, 400)

        ok_resp = self.client.post(
            reverse("accounts:update_profile", kwargs={"username": "alice"}),
            {"nickname": "alice_v2", "bio": "Студент Фундаментальной Информатики"},
        )
        self.assertEqual(ok_resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "alice_v2")
        self.assertEqual(self.user.profile.bio, "Студент Фундаментальной Информатики")
