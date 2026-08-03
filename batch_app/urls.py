# batch_app/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='batch_dashboard'),
    
    # Jobs
    path('jobs/', views.batch_job_list, name='batch_job_list'),
    path('jobs/create/', views.batch_job_create, name='batch_job_create'),
    path('jobs/<str:job_id>/', views.batch_job_detail, name='batch_job_detail'),
    path('jobs/<str:job_id>/logs/', views.batch_job_logs, name='batch_job_logs'),
    path('jobs/<str:job_id>/report/', views.batch_job_report, name='batch_job_report'),
    
    # ✅ EDIT - MUST come BEFORE the action pattern
    path('jobs/<str:job_id>/edit/', views.batch_job_edit, name='batch_job_edit'),
    
    # ⚠️ IMPORTANT: delete/ must come BEFORE the action pattern
    path('jobs/<str:job_id>/delete/', views.batch_job_delete, name='batch_job_delete'),
    
    # Action pattern - catches all other actions (pause, resume, cancel, etc.)
    # ⚠️ This must be LAST
    path('jobs/<str:job_id>/<str:action>/', views.batch_job_action, name='batch_job_action'),
    
    # API
    path('api/apps/', views.get_apps_api, name='api_apps'),
    path('api/templates/', views.get_templates_api, name='api_templates'),
    path('api/batch/<str:job_id>/status/', views.batch_job_status_api, name='api_batch_status'),
    path('api/jobs/count/', views.job_count_api, name='job_count_api'),
    
    # NEW: Execution monitoring endpoints
    path('api/executions/<str:job_id>/', views.get_executions_api, name='api_executions'),
    path('api/execution/<int:execution_id>/', views.get_execution_detail_api, name='api_execution_detail'),
]
