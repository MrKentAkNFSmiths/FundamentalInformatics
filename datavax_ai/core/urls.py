from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.home_page, name="home"),
    path("info/", views.api_docs_page, name="info"),
    path("api-docs/", views.api_docs_page, name="api_docs"),
]
