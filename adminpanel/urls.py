# urls.py
from django.urls import path
from . import views



urlpatterns = [
    # ============================================
    # AUTHENTICATION
    # ============================================
    path('login/', views.login_view, name='admin_login'),
    path('logout/', views.logout_view, name='admin_logout'),

    # ============================================
    # DASHBOARD (supports ?app=psf|sms|spl)
    # ============================================
    path('', views.dashboard, name='admin_dashboard'),

    # ============================================
    # USER MANAGEMENT (unchanged)
    # ============================================
    path('users/', views.user_list, name='admin_user_list'),
    path('users/create/', views.user_create, name='admin_user_create'),
    path('users/edit/<int:user_id>/', views.user_edit, name='admin_user_edit'),
    path('users/delete/<int:user_id>/', views.user_delete, name='admin_user_delete'),

    # ============================================
    # FAILED MESSAGES – unified with app in path
    # ============================================
    path('failed/<str:app_key>/', views.failed_messages, name='failed_messages_unified'),
    
    # Legacy URLs – redirect to the unified version
    path('failed-messages/', views.failed_messages_legacy_sms, name='failed_messages'),
    path('failed-messages2/', views.failed_messages_legacy_psf, name='failed_messages2'),

    # ============================================
    # API ENDPOINTS – all support ?app= query param
    # ============================================
    # Statistics & charts
    path('api/level-distribution/', views.get_level_distribution_api, name='level_distribution'),
    path('api/weekly-trend/', views.get_weekly_trend_api, name='weekly_trend'),

    # Case listings
    path('api/open-cases/', views.get_open_cases_api, name='open_cases'),
    path('api/resolved-cases/', views.get_resolved_cases_api, name='resolved_cases'),
    path('api/closed-cases/', views.get_closed_cases_api, name='closed_cases'),
    path('api/esc5-cases/', views.get_esc5_cases_api, name='esc5_cases'),
    path('api/cases/', views.get_all_cases_api, name='all_cases'),
    path('api/esc3-cases/', views.get_esc3_cases_api, name='esc3_cases_api'),

    # Case detail & actions
    path('case/<str:case_id>/detail/', views.get_case_detail_api, name='case_detail'),
    path('case/<str:case_id>/close/', views.close_case_api, name='close_case'),
    path('case/<str:case_id>/reopen/', views.reopen_case_api, name='reopen_case'),
    path('case/<str:case_id>/resolve/', views.resolve_case_api, name='resolve_case'),
    path('case/<str:case_id>/timeline/', views.get_case_timeline_api, name='case_timeline'),
    path('case/<str:case_id>/edit/', views.edit_case_api, name='edit_case_api'),

    # Search & export
    path('api/search/', views.search_cases_api, name='search_cases_api'),
    path('export-esc3-cases/', views.export_esc3_cases_excel, name='export_esc3_cases'),
]