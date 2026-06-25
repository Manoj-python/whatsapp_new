from django.urls import path
from . import views

app_name = 'meghaai_app'

urlpatterns = [
    path('', views.chat_index, name='chat_index'),
    path('chat/', views.chat_api, name='chat_api'),
    path('schema/', views.schema_info, name='schema_info'),

     # ============================================================
    # VOICE COMMAND APIs - ADD THESE
    # ============================================================
   # Main voice command endpoint - accepts audio or text
    path('api/voice-command/', views.voice_command_api, name='voice_command_api'),
    
    # Get available voice features
    path('api/voice-commands/', views.get_voice_commands_api, name='get_voice_commands'),
    
    # Test voice functionality
    path('api/voice-test/', views.voice_test_api, name='voice_test_api'),
]

