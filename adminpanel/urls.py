from django.urls import path
from . import views
from messaging2 import views as messaging2


urlpatterns = [
    path('', views.dashboard, name='admin_dashboard'),
    path('login/', views.login_view, name='admin_login'),
    path('logout/', views.logout_view, name='admin_logout'),

    # User management
    path('users/', views.user_list, name='admin_user_list'),
    path('users/create/', views.user_create, name='admin_user_create'),
    path('users/edit/<int:user_id>/', views.user_edit, name='admin_user_edit'),
    path('users/delete/<int:user_id>/', views.user_delete, name='admin_user_delete'),
    path('failed-messages/', views.failed_messages, name='failed_messages'),
    path('failed-messages2/', views.failed_messages2, name='failed_messages2'),

    path('api/level-distribution/', views.get_level_distribution_api, name='level_distribution'),
    path('api/weekly-trend/', views.get_weekly_trend_api, name='weekly_trend'),
    
    # ============================================
    # CASE LISTING APIs
    # ============================================
    path('api/open-cases/', views.get_open_cases_api, name='open_cases'),
    path('api/resolved-cases/', messaging2.get_resolved_cases_api2, name='resolved_cases'),
    path('api/closed-cases/', views.get_closed_cases_api, name='closed_cases'),
    path('api/esc5-cases/', views.get_esc5_cases_api, name='esc5_cases'),
    path('api/cases/', views.get_all_cases_api, name='all_cases'),
    path('api/esc3-cases/', views.get_esc3_cases_api, name='esc3_cases_api'),    
    # ============================================
    # CASE DETAIL & ACTION APIs
    # ============================================
    path('case/<str:case_id>/detail/', messaging2.get_case_detail_api2, name='case_detail'),
    path('case/<str:case_id>/close/', messaging2.close_case_api2, name='close_case'),
    path('case/<str:case_id>/reopen/', views.reopen_case_api, name='reopen_case'),
    path('case/<str:case_id>/resolve/', messaging2.resolve_case_api2, name='resolve_case'),
    path('case/<str:case_id>/timeline/', messaging2.get_case_timeline_api2, name='case_timeline'),
    path('export-esc3-cases/', views.export_esc3_cases_excel, name='export_esc3_cases'),

    path('api/search/', views.search_cases_api, name='search_cases_api'),
]

