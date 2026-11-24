"""Core views for landing page, API documentation, and error pages."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from accounts.models import Profile
from core.services import SUPPORTED_FORMAT_GROUPS
from drive.models import Folder
from shares.models import Share


def home_page(request: HttpRequest) -> HttpResponse:
    """Render the redesigned DataVax landing page."""
    context: dict = {
        "format_groups": SUPPORTED_FORMAT_GROUPS,
    }
    if request.user.is_authenticated:
        profile = Profile.for_user(request.user)
        root_folder = Folder.ensure_root_for_user(request.user)
        recent_shares = Share.objects.filter(user=request.user).select_related("asset")[:4]
        context.update(
            {
                "profile": profile,
                "root_folder": root_folder,
                "drive_files_count": request.user.drive_files.count(),
                "recent_shares": recent_shares,
            }
        )
    return render(request, "core/home.html", context)


def api_docs_page(request: HttpRequest) -> HttpResponse:
    """Render DataVax REST API reference and CLI usage examples."""
    base_url = request.build_absolute_uri("/").rstrip("/")
    return render(request, "core/api_docs.html", {"base_url": base_url})


def page_not_found(request: HttpRequest, exception=None) -> HttpResponse:
    """Render styled 404 page."""
    return render(request, "404.html", status=404)
