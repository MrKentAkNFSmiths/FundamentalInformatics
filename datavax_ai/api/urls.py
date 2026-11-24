from django.urls import path

from api import views

app_name = "api"

urlpatterns = [
    path("upload/", views.FileUploadView.as_view(), name="upload"),
    path("download/<str:hash_id>/", views.DownloadFileView.as_view(), name="download"),
    path("shares/<str:hash_id>/", views.ShareDetailApiView.as_view(), name="share_detail"),
    path("drive/", views.DriveFolderApiView.as_view(), name="drive_root"),
    path("drive/folders/<uuid:folder_id>/", views.DriveFolderApiView.as_view(), name="drive_folder"),
    path("drive/upload/", views.DriveUploadApiView.as_view(), name="drive_upload"),
]
