from django.shortcuts import render
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
import json
import logging
from meghaai_app.services.voice_commands import VoiceCommandHandler
from .services.claude_client import ClaudeClient
from .services.schema_builder import get_schema_catalog
from .services.database import get_db_connection

logger = logging.getLogger(__name__)

@login_required
def chat_index(request):
    """Render the chat interface"""
    return render(request, 'meghaai_app/index.html')

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def chat_api(request):
    """
    API endpoint for chat messages.
    """
    try:
        data = json.loads(request.body)
        messages = data.get('messages', [])

        if not messages:
            return JsonResponse({'error': 'No messages provided'}, status=400)

        # Get schema
        schema = get_schema_catalog()
        schema_text = schema.build_catalog()

        # Create Claude client
        claude = ClaudeClient()

        # Process message
        response_data = {
            'messages': [],
            'tool_calls': []
        }

        for chunk in claude.send_message(messages, schema_text):
            if chunk['type'] == 'text':
                response_data['messages'].append({
                    'role': 'assistant',
                    'content': chunk['content']
                })
            elif chunk['type'] == 'tool_call':
                response_data['tool_calls'].append({
                    'name': chunk['name'],
                    'success': chunk.get('success', False),
                    'message': chunk.get('message', '')
                })
            elif chunk['type'] == 'error':
                return JsonResponse({'error': chunk['content']}, status=500)

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def schema_info(request):
    """Get schema information - PUBLIC endpoint (no login required)"""
    try:
        logger.info("Schema info endpoint called")
        schema = get_schema_catalog()
        tables = schema.get_tables()

        return JsonResponse({
            'database': settings.MEGHAAI_CONFIG.get('MYSQL_DATABASE', 'Unknown'),
            'tables': list(tables),
            'table_count': len(tables)
        })
    except Exception as e:
        logger.error(f"Schema error: {e}")
        return JsonResponse({
            'database': 'Error',
            'tables': [],
            'table_count': 0,
            'error': str(e)
        }, status=200)






# ============================================================
# VOICE COMMAND API VIEWS - FREE CONVERSATION MODE
# ============================================================

# Create singleton instance of voice handler
voice_handler = VoiceCommandHandler()


@csrf_exempt
@login_required
def voice_command_api(request):
    """
    🎤 Voice Command API - Complete Free Conversation
    
    Accepts audio file or text input and returns AI response.
    
    POST /meghaai/api/voice-command/
    
    Form Data:
        - audio: (file) Audio recording (webm, wav, mp3)
        - text: (string) Text command (for testing)
    
    Returns:
        {
            'success': bool,
            'text': str,              # What user said
            'result': str,            # AI response
            'free_conversation': bool, # True if free conversation mode
            'error': str              # Error message if failed
        }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        # Get audio file or text
        audio_file = request.FILES.get('audio')
        text = request.POST.get('text')

        if audio_file:
            # Process audio with Whisper
            logger.info(f"Processing voice command from audio: {audio_file.name}")
            result = voice_handler.process_voice_input(audio_file)

        elif text:
            # Process text directly (for testing)
            logger.info(f"Processing voice command from text: {text[:50]}")
            
            # Send text to Claude directly
            try:
                from .services.claude_client import ClaudeClient
                from .services.schema_builder import get_schema_catalog
                
                schema = get_schema_catalog()
                schema_text = schema.build_catalog()
                claude = ClaudeClient()
                
                enhanced_text = f"""User asked: "{text}"

This is MeghaAI Collections Intelligence - a collections management assistant.

The user can ask ANYTHING:
1. General conversation (greetings, jokes, help, personal questions)
2. Collections data questions (portfolio, PTP, NPA, DPD, branches, executives, cases, payments)
3. Business insights and recommendations
4. Explanations of collections terminology
5. ANY other question they might have

Please respond naturally and helpfully.

=== DATABASE SCHEMA ===
{schema_text}
"""
                
                messages = [{'role': 'user', 'content': enhanced_text}]
                response_text = []
                
                for chunk in claude.send_message(messages, schema_text):
                    if chunk['type'] == 'text':
                        response_text.append(chunk['content'])
                
                result = {
                    'success': True,
                    'text': text,
                    'result': ''.join(response_text),
                    'message': 'Response from Claude',
                    'free_conversation': True
                }
                
            except Exception as e:
                logger.error(f"Text processing failed: {e}")
                result = {
                    'success': False,
                    'text': text,
                    'error': str(e),
                    'suggestion': 'Try: "Show morning briefing" or ask a collections question'
                }

        else:
            return JsonResponse({
                'error': 'Either audio file or text is required'
            }, status=400)

        return JsonResponse(result)

    except Exception as e:
        logger.error(f"Voice command API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def get_voice_commands_api(request):
    """
    Get information about voice capabilities
    
    GET /meghaai/api/voice-commands/
    
    Returns:
        {
            'success': bool,
            'message': str,
            'features': list,
            'examples': list
        }
    """
    return JsonResponse({
        'success': True,
        'message': '🎤 Voice is in FREE CONVERSATION mode! Ask anything!',
        'features': [
            'General conversation (greetings, jokes, help)',
            'Collections data questions (portfolio, PTP, NPA, DPD)',
            'Business insights and recommendations',
            'Explanations of collections terminology',
            'ANY question you have!'
        ],
        'examples': [
            "Hello, how are you?",
            "Show me portfolio health",
            "What's the NPA rate?",
            "Explain DPD to me",
            "Tell me a joke",
            "Show me something interesting",
            "Who are the top executives?",
            "What should I focus on today?"
        ]
    })


@login_required
def voice_test_api(request):
    """
    Test voice functionality
    
    GET /meghaai/api/voice-test/
    """
    return JsonResponse({
        'success': True,
        'message': '🎤 Voice API is working in FREE CONVERSATION mode!',
        'status': 'Active',
        'mode': 'Free Conversation',
        'sample_queries': [
            "Show morning briefing",
            "Show PTP tracker", 
            "Show risk report",
            "Show geo clustering",
            "Export worklist",
            "Send reminders",
            "Log call outcome",
            "Help",
            "Hello, how are you?",
            "Tell me about collections",
            "Explain DPD to me"
        ]
    })
