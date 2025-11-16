from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    path('', views.upload_and_send, name='upload_and_send'),
    path("job/<uuid:job_id>/", views.job_status, name="job_status"),
    path('download-success/<uuid:job_id>/', views.download_success_report, name='download_success_report'),
    path('download-failed/<uuid:job_id>/', views.download_failed_report, name='download_failed_report'),
    path("chat/", views.chat_dashboard, name="chat_dashboard"),
    path("api/messages/<str:mobile>/", views.chat_messages_api, name="chat_messages_api"),
    path("api/send-reply/", views.send_reply_api, name="send_reply_api"),

    path("webhook/", views.whatsapp_webhook, name="whatsapp_webhook"),
    path("export/received/", views.export_received_messages_to_excel, name="export_received")

]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
