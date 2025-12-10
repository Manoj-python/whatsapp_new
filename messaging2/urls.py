from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Bulk upload + WhatsApp sending
    path('', views.upload_and_send2, name='upload_and_send2'),

    # Job status and reports
    path('job/<uuid:job_id>/', views.job_status2, name='job_status2'),
    path('download-success/<uuid:job_id>/', views.download_success_report2, name='download_success_report2'),
    path('download-failed/<uuid:job_id>/', views.download_failed_report2, name='download_failed_report2'),

    # Chat dashboard and APIs
    path('chat/', views.chat_dashboard2, name='chat_dashboard2'),
    path('api/messages/<str:mobile>/', views.chat_messages_api2, name='chat_messages_api2'),
    path('api/send-reply/', views.send_reply_api2, name='send_reply_api2'),
    path("api/contacts2/", views.contacts_api2, name="contacts_api2"),
    path("api/mark-read/<str:mobile>/", views.mark_read),
    path("login/", views.messaging2_login, name="messaging2_login"),
    path("logout/", views.messaging2_logout, name="messaging2_logout"),



    # Webhook and exports
    path('webhook/', views.whatsapp_webhook2, name='whatsapp_webhook2'),
    path('export/received/', views.export_received_messages_to_excel2, name='export_received2'),


     # -----------------------------
    # Real-time Chat Features (App2)
    # -----------------------------

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
