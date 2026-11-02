
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api.email_api import EmailTemplateViewSet
from . import views

router = DefaultRouter()
router.register(
    "templates",
    EmailTemplateViewSet,
    basename="email-template",
)

urlpatterns = [
    path("api/", include(router.urls)),
    path("templates/", views.email_templates, name="email_templates"),

    path(
        "campaigns/",
        views.email_campaigns,
        name="email_campaigns",
    ),
    path(
        "campaigns/upload/",
        views.upload_email_campaign,
        name="upload_email_campaign",
    ),
    path(
        "campaigns/<int:campaign_id>/progress/",
        views.email_campaign_progress,
        name="email_campaign_progress",
    ),
    path(
        "campaigns/<int:campaign_id>/report.csv",
        views.email_campaign_report,
        name="email_campaign_report",
    ),
    path(
        "campaigns/<int:campaign_id>/failed.csv",
        views.email_campaign_failed_report,
        name="email_campaign_failed_report",
    ),
    path(
        "campaigns/<int:campaign_id>/delete/",
        views.delete_email_campaign,
        name="delete_email_campaign",
    ),
]
