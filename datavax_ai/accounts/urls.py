from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("sign_in/", views.sign_in_page, name="sign_in"),
    path("sign_up/", views.sign_up_page, name="sign_up"),
    path("logout/", views.logout_handler, name="logout"),
    path("profile/<str:username>/", views.profile_page, name="profile"),
    path("profile/<str:username>/upload-avatar/", views.upload_avatar_handler, name="upload_avatar"),
    path("profile/<str:username>/update/", views.update_profile_handler, name="update_profile"),
    path("profile/<str:username>/update-nickname/", views.update_profile_handler, name="update_nickname"),
]
