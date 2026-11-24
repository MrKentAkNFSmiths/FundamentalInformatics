from django.urls import path

from drive import views

app_name = "drive"

urlpatterns = [
    path("", views.drive_explorer, name="root"),
    path("folder/<uuid:folder_id>/", views.drive_explorer, name="folder"),
    path("folders/create/", views.create_folder_handler, name="create_folder"),
    path("folders/<uuid:folder_id>/rename/", views.rename_folder_handler, name="rename_folder"),
    path("folders/<uuid:folder_id>/move/", views.move_folder_handler, name="move_folder"),
    path("folders/<uuid:folder_id>/delete/", views.delete_folder_handler, name="delete_folder"),
    path("folders/<uuid:folder_id>/download/", views.download_folder_zip_handler, name="download_folder_zip"),
    path("files/upload/", views.upload_files_handler, name="upload_files"),
    path("files/note/", views.create_note_handler, name="create_note"),
    path("files/<uuid:file_id>/preview/", views.preview_file_page, name="preview_file"),
    path("files/<uuid:file_id>/save-content/", views.update_file_content_handler, name="save_file_content"),
    path("files/<uuid:file_id>/download/", views.download_file_handler, name="download_file"),
    path("files/<uuid:file_id>/raw/", views.raw_file_handler, name="raw_file"),
    path("files/<uuid:file_id>/star/", views.toggle_star_handler, name="toggle_star"),
    path("files/<uuid:file_id>/rename/", views.rename_file_handler, name="rename_file"),
    path("files/<uuid:file_id>/move/", views.move_file_handler, name="move_file"),
    path("files/<uuid:file_id>/delete/", views.delete_file_handler, name="delete_file"),
    path("files/<uuid:file_id>/share/", views.share_drive_file_handler, name="share_file"),
]
