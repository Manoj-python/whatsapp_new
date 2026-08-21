from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from .api.customer_views import (
    customer_create_ticket,
    customer_ticket_detail,
    customer_ticket_track,
    customer_tickets_by_mobile,
    customer_add_comment,
    customer_reopen_ticket,
)

urlpatterns = [
    path('', views.upload_and_send, name='upload_and_send'),

    # IMPORTANT: job_id must be <str>, NOT <uuid>
    path('job/<str:job_id>/', views.job_status, name='job_status'),
    path('download-success/<str:job_id>/', views.download_success_report, name='download_success_report'),
    path('download-failed/<str:job_id>/', views.download_failed_report, name='download_failed_report'),
    path('download-skipped/<str:job_id>/', views.download_skipped_report, name='download_skipped_report'), 
    

    path("chat/", views.chat_dashboard, name="chat_dashboard"),
    path("api/messages/<str:mobile>/", views.chat_messages_api, name="chat_messages_api"),
    path("api/send-reply/", views.send_reply_api, name="send_reply_api"),
    path("api/mark-read/<str:mobile>/", views.mark_read),
    path("login/", views.messaging_login, name="messaging_login"),
    path("logout/", views.messaging_logout, name="messaging_logout"),

    path("api/contacts/", views.contacts_api, name="contacts_api"),
    path("webhook/", views.whatsapp_webhook, name="whatsapp_webhook"),
    path("api/mark-read/<str:mobile>/", views.mark_read, name="mark_read"),
    path('api/contact-messages/', views.get_contact_messages, name='get_contact_messages'),
    path('secure-document/<int:log_id>/', views.view_secure_document, name='secure_document'),
    path('api/send-ptp-template/', views.send_ptp_template_view, name='send_ptp_template'),
    path('api/ptp-details/', views.get_ptp_details_view, name='get_ptp_details'),
    path('api/noc-details/', views.noc_details, name='noc_details'),
    path('api/send-noc/', views.send_noc, name='send_noc'),
    path('api/statement-details/', views.statement_details, name='statement_details'),
    path('api/send-statement/', views.send_statement, name='send_statement'),    
    path('download-skipped/<str:job_id>/', views.download_skipped_report, name='download_skipped_report'),    
    path('api/send-foreclosure/', views.send_foreclosure, name='send_foreclosure'),

    path('customer/tickets/create/', customer_create_ticket, name='customer_create_ticket'),
    path('customer/tickets/<uuid:token>/', customer_ticket_detail, name='customer_ticket_detail'),
    path('customer/tickets/<uuid:token>/track/', customer_ticket_track, name='customer_ticket_track'),
    path('customer/tickets/<uuid:token>/comments/', customer_add_comment, name='customer_add_comment'),
    path('customer/tickets/<uuid:token>/reopen/', customer_reopen_ticket, name='customer_reopen_ticket'),
    path('customer/tickets/', customer_tickets_by_mobile, name='customer_tickets_by_mobile'),        
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
