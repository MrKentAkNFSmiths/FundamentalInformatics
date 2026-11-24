"""Views for authentication and user profiles."""

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from accounts.forms import AvatarUploadForm, LoginForm, RegisterForm, validate_username_value
from accounts.models import Profile
from shares.models import Like, Share


def sign_in_page(request: HttpRequest) -> HttpResponse:
    """Authenticate an existing user."""
    if request.user.is_authenticated:
        return redirect("drive:root")

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.user)
        messages.success(request, f"Добро пожаловать, {form.user.username}!")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect("drive:root")

    return render(request, "accounts/sign_in.html", {"form": form, "next": next_url})


def sign_up_page(request: HttpRequest) -> HttpResponse:
    """Register a new user and provision their root Drive workspace."""
    if request.user.is_authenticated:
        return redirect("drive:root")

    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.create_user()
        login(request, user)
        messages.success(request, "Аккаунт создан, личный диск готов к работе!")
        return redirect("drive:root")

    return render(request, "accounts/sign_up.html", {"form": form})


def logout_handler(request: HttpRequest) -> HttpResponse:
    """Sign out the current user."""
    if request.user.is_authenticated:
        logout(request)
        messages.info(request, "Вы вышли из аккаунта.")
    return redirect("core:home")


def profile_page(request: HttpRequest, username: str) -> HttpResponse:
    """Display a user profile with public shares (or full dashboard for the owner)."""
    target_user = get_object_or_404(User, username=username)
    profile = Profile.for_user(target_user)
    is_owner = request.user.is_authenticated and request.user == target_user

    shares_qs = Share.objects.filter(user=target_user).select_related("asset").order_by("-created_at")
    if not is_owner:
        shares_qs = shares_qs.filter(is_anonymous=False)

    shares_list = list(shares_qs)
    if not is_owner:
        shares_list = [s for s in shares_list if not s.is_expired]

    total_likes = Like.objects.filter(share__user=target_user).count()
    drive_files_count = target_user.drive_files.count()

    context = {
        "profile_user": target_user,
        "profile": profile,
        "is_owner": is_owner,
        "shares_list": shares_list,
        "total_likes": total_likes,
        "drive_files_count": drive_files_count,
    }
    return render(request, "accounts/profile.html", context)


@login_required
def upload_avatar_handler(request: HttpRequest, username: str) -> JsonResponse:
    """Upload a verified avatar image for the authenticated profile owner."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Требуется POST-запрос."}, status=405)
    if request.user.username != username:
        return JsonResponse({"success": False, "error": "Нет прав на изменение этого профиля."}, status=403)

    form = AvatarUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        first_err = next(iter(form.errors.values()))[0]
        return JsonResponse({"success": False, "error": first_err}, status=400)

    profile = Profile.for_user(request.user)
    if profile.avatar:
        profile.avatar.delete(save=False)
    profile.avatar = form.cleaned_data["avatar"]
    profile.save()
    return JsonResponse({"success": True, "avatar_url": profile.avatar.url})


@login_required
def update_profile_handler(request: HttpRequest, username: str) -> JsonResponse:
    """Update nickname and/or bio for the authenticated profile owner."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Требуется POST-запрос."}, status=405)
    if request.user.username != username:
        return JsonResponse({"success": False, "error": "Нет прав на изменение этого профиля."}, status=403)

    new_nickname = request.POST.get("nickname")
    bio = request.POST.get("bio")
    profile = Profile.for_user(request.user)

    if new_nickname is not None:
        try:
            cleaned_nick = validate_username_value(new_nickname)
        except ValidationError as exc:
            return JsonResponse({"success": False, "error": exc.message}, status=400)

        if User.objects.filter(username__iexact=cleaned_nick).exclude(pk=request.user.pk).exists():
            return JsonResponse({"success": False, "error": "Этот никнейм уже занят."}, status=400)

        request.user.username = cleaned_nick
        request.user.save(update_fields=["username"])

    if bio is not None:
        profile.bio = bio.strip()[:300]
        profile.save(update_fields=["bio"])

    new_url = request.build_absolute_uri(reverse("accounts:profile", kwargs={"username": request.user.username}))
    return JsonResponse(
        {
            "success": True,
            "message": "Профиль обновлён.",
            "username": request.user.username,
            "bio": profile.bio,
            "new_url": new_url,
        }
    )
