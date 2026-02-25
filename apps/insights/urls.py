"""
InsightScribe - Insight URLs
"""

from django.urls import path

from . import views

app_name = "insights"

urlpatterns = [
    path("generate/", views.generate_report_view, name="generate-report"),
    path("", views.report_list_view, name="report-list"),
    path("<uuid:report_id>/", views.report_detail_view, name="report-detail"),
    path("<uuid:report_id>/delete/", views.delete_report_view, name="report-delete"),
]
