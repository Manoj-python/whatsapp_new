from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.upload_and_send, name='upload_and_send'),

    # IMPORTANT: job_id must be <str>, NOT <uuid>
    path('job/<str:job_id>/', views.job_status, name='job_status'),
    path('download-success/<str:job_id>/', views.download_success_report, name='download_success_report'),
    path('download-failed/<str:job_id>/', views.download_failed_report, name='download_failed_report'),

    path("chat/", views.chat_dashboard, name="chat_dashboard"),
    path("api/messages/<str:mobile>/", views.chat_messages_api, name="chat_messages_api"),
    path("api/send-reply/", views.send_reply_api, name="send_reply_api"),
    path("api/mark-read/<str:mobile>/", views.mark_read),
    path("login/", views.messaging_login, name="messaging_login"),
    path("logout/", views.messaging_logout, name="messaging_logout"),

    path("api/contacts/", views.contacts_api, name="contacts_api"),
    path("webhook/", views.whatsapp_webhook, name="whatsapp_webhook"),
    path("api/mark-read/<str:mobile>/", views.mark_read, name="mark_read"),
    

   
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
