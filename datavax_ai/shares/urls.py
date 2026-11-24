from django.urls import path

from shares import views

app_name = "shares"

urlpatterns = [
    path("new/", views.new_share_page, name="new"),
    path("upload/", views.create_share_handler, name="upload"),
    path("s/<str:hash_id>/", views.share_detail_page, name="detail"),
    path("post/<str:hash_id>/", views.share_detail_page, name="legacy_detail"),
    path("s/<str:hash_id>/raw/", views.serve_share_raw_handler, name="raw"),
    path("s/<str:hash_id>/download/", views.download_share_handler, name="download"),
    path("s/<str:hash_id>/save-to-drive/", views.save_share_to_drive_handler, name="save_to_drive"),
    path("s/<str:hash_id>/delete/", views.delete_share_handler, name="delete"),
    path("api/shares/<str:hash_id>/like/", views.like_share_handler, name="like"),
    path("api/like-post/<str:hash_id>/", views.like_share_handler, name="legacy_like"),
    path("api/shares/<str:hash_id>/report/", views.report_share_handler, name="report"),
    path("api/report-file/<str:hash_id>/", views.report_share_handler, name="legacy_report"),
]
