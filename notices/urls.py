from django.urls import path
from .views import upload_excel, upload_excel_api, get_task_status

urlpatterns = [
    path('', upload_excel, name='upload_excel'),
    path('upload_api/', upload_excel_api, name='upload_api'),
    path('status/<str:task_id>/', get_task_status, name='task_status'),
]
