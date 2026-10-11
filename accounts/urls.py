from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("mypage/", views.mypage, name="mypage"),
    path("password/change/", views.AccountPasswordChangeView.as_view(), name="password_change"),
    path("signup/", views.signup, name="signup"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True,
            redirect_field_name=None,
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(redirect_field_name=None),
        name="logout",
    ),
]
