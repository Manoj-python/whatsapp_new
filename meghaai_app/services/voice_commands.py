# meghaai_app/services/voice_commands.py

import re
import logging
import requests
import tempfile
import os
import time
from typing import Dict, Any, Optional
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile

logger = logging.getLogger(__name__)


class VoiceCommandHandler:
    """Handle voice commands - FREE CONVERSATION MODE!"""

    def __init__(self):
        # Whisper API configuration
        self.whisper_api_url = settings.MEGHAAI_CONFIG.get('WHISPER_API_URL', '')
        self.whisper_api_key = settings.MEGHAAI_CONFIG.get('WHISPER_API_KEY', '')
        
        # Try to use OpenAI SDK
        self.openai_client = None
        self.use_sdk = False
        
        if self.whisper_api_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=self.whisper_api_key)
                self.use_sdk = True
                logger.info("✅ OpenAI SDK initialized for Whisper")
            except ImportError:
                logger.warning("⚠️ OpenAI SDK not installed. Install with: pip install openai")
            except Exception as e:
                logger.warning(f"⚠️ OpenAI SDK init failed: {e}")
        
        if not self.use_sdk:
            logger.info("📡 Using requests fallback for Whisper API")
        
        logger.info("🎤 VoiceCommandHandler initialized - FREE CONVERSATION MODE!")

    def transcribe_audio(self, audio_file) -> str:
        """
        Transcribe audio using Whisper API
        Priority: OpenAI SDK > Requests
        """
        
        if not self.whisper_api_url:
            raise ValueError("WHISPER_API_URL not configured in MEGHAAI_CONFIG")
        
        if not self.whisper_api_key:
            raise ValueError("WHISPER_API_KEY not configured in MEGHAAI_CONFIG")
        
        # ✅ Try SDK first with proper file handling
        if self.use_sdk and self.openai_client:
            try:
                # Reset file pointer
                audio_file.seek(0)
                audio_bytes = audio_file.read()
                
                # Create BytesIO object for SDK
                from io import BytesIO
                file_obj = BytesIO(audio_bytes)
                file_obj.name = getattr(audio_file, 'name', 'audio.webm')
                
                # Call Whisper API via SDK
                response = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=file_obj,
                    response_format="text",
                    language="en"
                )
                
                text = response if isinstance(response, str) else response.text
                
                if text:
                    logger.info(f"✅ Transcribed (SDK): {text[:50]}...")
                    return text.strip()
                    
            except Exception as e:
                logger.warning(f"SDK transcription failed: {e}, falling back to requests")
                audio_file.seek(0)
        
        # ✅ Fallback to requests
        return self._transcribe_with_requests(audio_file)

    def _transcribe_with_requests(self, audio_file) -> str:
        """Transcribe using requests (fallback)"""
        
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Reset file pointer
                audio_file.seek(0)
                
                # Read file content
                audio_content = audio_file.read()
                
                if not audio_content:
                    raise ValueError("Empty audio file")
                
                # Get file info
                filename = getattr(audio_file, 'name', 'audio.webm')
                content_type = getattr(audio_file, 'content_type', 'audio/webm')
                
                # Create temp file with correct extension
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
                temp_file.write(audio_content)
                temp_file.flush()
                temp_file.close()
                
                logger.info(f"📤 Attempt {attempt + 1}: File: {filename}, Size: {len(audio_content)} bytes")
                
                try:
                    # Open temp file and send
                    with open(temp_file.name, 'rb') as f:
                        files = {
                            'file': (filename.replace('.webm', '.mp3'), f, 'audio/mpeg')
                        }
                        
                        data = {
                            'model': 'whisper-1',
                            'response_format': 'text',
                            'language': 'en'
                        }
                        
                        headers = {
                            'Authorization': f'Bearer {self.whisper_api_key}'
                        }
                        
                        # Send request with timeout
                        response = requests.post(
                            self.whisper_api_url,
                            files=files,
                            data=data,
                            headers=headers,
                            timeout=90
                        )
                        
                        # Handle 503 with retry
                        if response.status_code == 503:
                            logger.warning(f"⚠️ 503 Error (attempt {attempt + 1}/{max_retries})")
                            if attempt < max_retries - 1:
                                time.sleep(3 * (attempt + 1))
                                continue
                            else:
                                raise Exception("OpenAI servers are overloaded. Please try again later.")
                        
                        if response.status_code != 200:
                            logger.error(f"❌ API Error {response.status_code}")
                            logger.error(f"Response: {response.text[:500]}")
                            
                            try:
                                error_data = response.json()
                                error_msg = error_data.get('error', {}).get('message', response.text)
                            except:
                                error_msg = response.text
                            
                            raise Exception(f"Whisper API error: {error_msg}")
                        
                        # Parse response
                        try:
                            result = response.json()
                            text = result.get('text', '')
                        except ValueError as json_err:
                            logger.error(f"JSON parse error: {json_err}")
                            logger.error(f"Raw response: {response.text[:200]}")
                            raise Exception("Invalid response from Whisper API")
                        
                        if not text:
                            raise ValueError("No transcription text in response")
                        
                        logger.info(f"✅ Transcribed: {text[:50]}...")
                        return text.strip()
                        
                finally:
                    # Clean up temp file
                    try:
                        if os.path.exists(temp_file.name):
                            os.unlink(temp_file.name)
                            logger.info(f"🧹 Cleaned up temp file: {temp_file.name}")
                    except:
                        pass
                    
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)[:100]}")
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                else:
                    raise

    def process_voice_input(self, audio_file) -> Dict[str, Any]:
        """
        🎯 COMPLETE FREE CONVERSATION - EVERYTHING GOES TO CLAUDE!
        
        This handles:
        1. General conversation (greetings, jokes, help)
        2. Collections data questions (portfolio, PTP, NPA, DPD, etc.)
        3. Business insights and recommendations
        4. ANYTHING else the user wants to ask!
        """
        
        # 1. Transcribe audio
        try:
            text = self.transcribe_audio(audio_file)
        except Exception as e:
            return {
                'success': False,
                'error': f'Transcription failed: {str(e)}',
                'text': ''
            }

        if not text:
            return {
                'success': False,
                'error': 'No speech detected',
                'text': ''
            }

        logger.info(f"🎤 User said: {text}")

        # 2. 🚀 SEND EVERYTHING TO CLAUDE - FREE CONVERSATION!
        try:
            from ..services.claude_client import ClaudeClient
            from ..services.schema_builder import get_schema_catalog
            
            # Get database schema
            schema = get_schema_catalog()
            schema_text = schema.build_catalog()
            
            # Create Claude client
            claude = ClaudeClient()
            
            # ✅ Enhanced context for Claude
            enhanced_text = f"""User asked: "{text}"

This is MeghaAI Collections Intelligence - a collections management assistant.

The user can ask ANYTHING:
1. General conversation (greetings, jokes, help, personal questions)
2. Collections data questions (portfolio, PTP, NPA, DPD, branches, executives, cases, payments)
3. Business insights and recommendations
4. Explanations of collections terminology
5. ANY other question they might have

Please respond naturally and helpfully. 
- If it's a data question, use the database schema to provide insights.
- If it's general conversation, respond conversationally.
- If it's a question about collections, provide helpful information.

=== DATABASE SCHEMA ===
{schema_text}
"""
            
            # Send to Claude
            messages = [{'role': 'user', 'content': enhanced_text}]
            result = []
            
            for chunk in claude.send_message(messages, schema_text):
                if chunk['type'] == 'text':
                    result.append(chunk['content'])
            
            response_text = ''.join(result)
            
            if not response_text:
                response_text = "I received your message but couldn't generate a response. Please try again."
            
            return {
                'success': True,
                'text': text,
                'result': response_text,
                'message': 'Response from Claude',
                'free_conversation': True
            }
            
        except Exception as e:
            logger.error(f"Claude processing failed: {e}")
            
            # Fallback response if Claude fails
            return {
                'success': True,
                'text': text,
                'result': f"""🤖 I heard you say: "{text}"

I understand you want to ask questions freely. For data-related questions, I can help with:
- Portfolio health and metrics
- Customer behavior analysis  
- DPD bucket distributions
- PTP (Promise to Pay) performance
- Branch and executive performance
- NPA and risk analysis
- Collections strategy recommendations

For general conversation, I'm here to chat too! 

What would you like to know?""",
                'message': 'Fallback response',
                'is_fallback': True
            }
