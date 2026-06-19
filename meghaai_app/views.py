from django.shortcuts import render
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
import json
import logging

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
