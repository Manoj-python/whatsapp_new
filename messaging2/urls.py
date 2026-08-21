from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from adminpanel.views import edit_case_api

urlpatterns = [
    # Bulk upload + WhatsApp send
    path('', views.upload_and_send2, name='upload_and_send2'),

    # Job status and reports
    path('job/<uuid:job_id>/', views.job_status2, name='job_status2'),
    path('download-success/<uuid:job_id>/', views.download_success_report2, name='download_success_report2'),
    path('download-failed/<uuid:job_id>/', views.download_failed_report2, name='download_failed_report2'),
    path('download-skipped/<uuid:job_id>/', views.download_skipped_report2, name='download_skipped_report2'),
    # Chat dashboard and APIs
    path('chat/', views.chat_dashboard2, name='chat_dashboard2'),
    path('api/messages/<str:mobile>/', views.chat_messages_api2, name='chat_messages_api2'),
    path('api/send-reply2/', views.send_reply_api2, name='send_reply_api2'),
    path("api/contacts2/", views.contacts_api2, name="contacts_api2"),
    path("login/", views.messaging2_login, name="messaging2_login"),
    path("logout/", views.messaging2_logout, name="messaging2_logout"),
    path("api/mark-read/<str:mobile>/", views.mark_read2, name="mark_read2"),
    path('api/contact-messages2/', views.get_contact_messages2, name='get_contact_messages2'),
    path('agent-case-list/', views.agent_case_list_api, name='agent_case_list_api'),



    # Webhook and exports
    path('webhook/', views.whatsapp_webhook2, name='whatsapp_webhook2'),
    path('secure-document2/<int:log_id>/', views.view_secure_document2, name='secure_document2'),
    #path('export/received/', views.export_received_messages_to_excel2, name='export_received2'),


   path('agent-dashboard/', views.agent_dashboard2, name='agent_dashboard'),
   path('executive-dashboard/', views.executive_dashboard2, name='executive_dashboard'),
   path('manager-dashboard/', views.manager_dashboard2, name='manager_dashboard'),
   path('head-dashboard/', views.head_dashboard2, name='head_dashboard'),
    # path('admin_dashboard/', admin_dashboard, name='admin_dashboard'),
    
    # ============================================
    # CASE API ENDPOINTS (CRITICAL - Fixes 404)
    # ============================================
    path('case/<str:case_id>/detail/', views.get_case_detail_api2, name='get_case_detail'),
    path('case/<str:case_id>/escalate/', views.escalate_case_api2, name='escalate_case'),
    path('case/<str:case_id>/resolve/', views.resolve_case_api2, name='resolve_case'),
    #path('case/<str:case_id>/close/', views.close_case_api2, name='close_case'),
    # path('case/<str:case_id>/reopen/', reopen_case_api, name='reopen_case'),
    path('case/<str:case_id>/assign/', views.assign_case_api2, name='assign_case'),
    path('case/<str:case_id>/timeline/', views.get_case_timeline_api2, name='case_timeline'),
    path('case/<str:case_id>/permissions/', views.get_case_action_permissions2, name='case_permissions'),
    path('case/by-mobile/', views.get_case_by_mobile2, name='get_case_by_mobile'),
    path('case/create-from-chat/', views.create_case_from_chat_api2, name='create_case_from_chat'),
    path('case/<str:case_id>/description-history/', views.get_description_history_api, name='get_description_history_api'),
    # ============================================
    # STATISTICS APIs
    # ============================================
    path('api/mark-unread/', views.mark_unread_api2, name='mark_unread_api2'),
    path('api/resolved-cases/', views.get_resolved_cases_api2, name='get_resolved_cases'),
    path('api/dashboard-stats/', views.get_dashboard_stats_api2, name='dashboard_stats'),
    path('api/user-role/', views.get_user_role_api2, name='user_role_api'),
    path('case/<str:case_id>/edit/', edit_case_api, name='edit_case_api'),

    path('api/groups/', views.get_groups_api, name='get_groups_api'),
    path('api/subgroups/', views.get_subgroups_api, name='get_subgroups_api'),
    path('api/categories/', views.api_categories, name='api_categories'),

    path('manager-cases/', views.manager_cases_api, name='manager_cases_api'),
    path('head-cases/', views.head_cases_api, name='head_cases_api'),
    path('export-cases-excel/', views.export_cases_excel, name='export_cases_excel'),
    path('export-group-cases/', views.export_group_cases_excel, name='export_group_cases_excel'),
     path('api/fetch-padmasai/', views.fetch_padmasai_details, name='fetch_padmasai'),
     path('executive/export/', views.export_executive_cases, name='export_executive_cases'),
      path('api/payment-details/', views.get_payment_details_view, name='payment_details'),
     path('api/send-payment-template/', views.send_payment_template_view, name='send_payment_template'),
     path('export-manager-cases/', views.export_manager_cases, name='export_manager_cases'),
     # -----------------------------
    # Real-time Chat Features (App2)
    # -----------------------------
    path('download-skipped/<uuid:job_id>/', views.download_skipped_report2, name='download_skipped_report2')

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
