from django.urls import path
from . import views

app_name = 'meghaai_app'

urlpatterns = [
    path('', views.chat_index, name='chat_index'),
    path('chat/', views.chat_api, name='chat_api'),
    path('schema/', views.schema_info, name='schema_info'),
]
