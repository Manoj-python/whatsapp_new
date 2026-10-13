# sms_app/urls.py

from django.urls import path,include
from .views import *
from .apis.template_api import TemplateViewSet,NotificationViewSet
from rest_framework.routers import DefaultRouter

router=DefaultRouter()
router.register('templates', TemplateViewSet, basename='template')
router.register('notificationtype',NotificationViewSet,basename='notify')



urlpatterns = [
    path('api/', include(router.urls)),
    path('', upload_excel, name='upload_excel'),
    path('templates/', ad_template, name='ad_template'),
    path('notifys/',add_notification,name='add_notification'),
    path('campaign-status/<int:campaign_id>/', campaign_status_api, name='campaign_status_api'),
    path(
        "campaign/<int:campaign_id>/report/",
        download_sms_campaign_report,
        name="download_sms_campaign_report",
    ),
    path(
    "batch/<str:job_id>/sms-fallback-report/",
    batch_sms_fallback_report,
    name="batch_sms_fallback_report",
),

] 
