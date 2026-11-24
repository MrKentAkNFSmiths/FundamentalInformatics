"""Authentication and profile management forms."""

import re
from io import BytesIO

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")
MAX_AVATAR_BYTES = 5 * 1024 * 1024


def validate_username_value(username: str) -> str:
    """Validate username format and length."""
    cleaned = (username or "").strip()
    if len(cleaned) < 3 or len(cleaned) > 32:
        raise ValidationError("Имя пользователя должно содержать от 3 до 32 символов.")
    if not USERNAME_PATTERN.match(cleaned):
        raise ValidationError("Допустимы только латинские буквы, цифры, точка, дефис и подчёркивание.")
    return cleaned


class LoginForm(forms.Form):
    """Form for user sign-in."""

    username = forms.CharField(
        label="Имя пользователя",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Введите имя пользователя",
                "id": "username",
                "class": "input-field",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Введите пароль",
                "id": "password",
                "class": "input-field",
                "autocomplete": "current-password",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        username = (cleaned_data.get("username") or "").strip()
        password = cleaned_data.get("password") or ""
        if username and password:
            user = authenticate(username=username, password=password)
            if user is None:
                raise ValidationError("Неверное имя пользователя или пароль.")
            if not user.is_active:
                raise ValidationError("Этот аккаунт деактивирован.")
            self.user = user
        return cleaned_data


class RegisterForm(forms.Form):
    """Form for new user registration."""

    username = forms.CharField(
        label="Имя пользователя",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Минимум 3 символа (латиница, цифры, . _ -)",
                "id": "username",
                "class": "input-field",
                "autocomplete": "username",
            }
        ),
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "you@example.com",
                "id": "email",
                "class": "input-field",
                "autocomplete": "email",
            }
        ),
    )
    password1 = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Минимум 8 символов",
                "id": "password1",
                "class": "input-field",
                "autocomplete": "new-password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Подтверждение пароля",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Повторите пароль",
                "id": "password2",
                "class": "input-field",
                "autocomplete": "new-password",
            }
        ),
    )

    def clean_username(self) -> str:
        username = validate_username_value(self.cleaned_data.get("username", ""))
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Пользователь с таким именем уже существует.")
        return username

    def clean_email(self) -> str:
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Пользователь с таким email уже существует.")
        return email

    def clean_password1(self) -> str:
        password1 = self.cleaned_data.get("password1") or ""
        if len(password1) < 8:
            raise ValidationError("Пароль должен содержать минимум 8 символов.")
        return password1

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password1")
        p2 = cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Пароли не совпадают.")
        return cleaned_data

    def create_user(self) -> User:
        """Create and return the new User instance."""
        return User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
        )


class AvatarUploadForm(forms.Form):
    """Validate uploaded avatar image via Pillow."""

    avatar = forms.FileField()

    def clean_avatar(self):
        avatar = self.cleaned_data["avatar"]
        if avatar.size > MAX_AVATAR_BYTES:
            raise ValidationError("Максимальный размер аватара — 5 МБ.")
        raw = avatar.read()
        avatar.seek(0)
        try:
            with Image.open(BytesIO(raw)) as img:
                img.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValidationError("Загруженный файл не является корректным изображением.") from exc
        return avatar
