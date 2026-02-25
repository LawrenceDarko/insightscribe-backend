"""
InsightScribe - Account URLs
All auth endpoints are function-based views.
"""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Authentication
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("token/refresh/", views.token_refresh_view, name="token-refresh"),
    path("logout/", views.logout_view, name="logout"),
    # Profile
    path("profile/", views.profile_view, name="profile"),
    path("change-password/", views.change_password_view, name="change-password"),
]
