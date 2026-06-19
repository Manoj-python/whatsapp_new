"""Claude AI client for chat interactions"""

import json
import logging
from typing import List, Dict, Any
import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

class ClaudeClient:
    """Manages Claude AI interactions"""
    
    def __init__(self):
        self.api_key = settings.MEGHAAI_CONFIG['ANTHROPIC_API_KEY']
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = settings.MEGHAAI_CONFIG.get('MODEL', 'claude-sonnet-4-6')
        self.max_tokens = 3072
        
        # Tool definitions
        self.tools = [
            {
                "name": "run_sql",
                "description": "Run a read-only SQL query and get results",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "MySQL SELECT/WITH query"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "list_tables",
                "description": "List all tables in the database",
                "input_schema": {"type": "object", "properties": {}}
            },
            {
                "name": "describe_table",
                "description": "Show columns and sample data for a table",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "table_name": {"type": "string", "description": "Table name"}
                    },
                    "required": ["table_name"]
                }
            }
        ]
        
        # System prompt template
        self.system_prompt_template = """
You are MeghaAI Collections Intelligence, an analytics co-pilot for the COLLECTIONS MANAGER.

Your job: explain CUSTOMER BEHAVIOUR using the data, and help the manager IMPROVE COLLECTIONS.

HOW YOU WORK:
1. Use run_sql to query data - never invent numbers
2. Use one well-built query with JOINs
3. Use describe_table/list_tables to understand schema

DOMAIN KNOWLEDGE:
- DPD = days past due. Buckets: Current (0) / 1-30 / 31-60 / 61-90 / 90+
- POS = principal outstanding
- PTP = promise to pay
- NPA = 90+ days past due

HOW TO ANSWER:
- Lead with INSIGHT, then NUMBERS, then 2-4 CONCRETE ACTIONS
- Be concise and practical
- Identify customers by name/account only, not phone numbers or addresses

=== DATABASE SCHEMA ===
{schema}
"""
    
    def get_system_prompt(self, schema: str) -> str:
        """Generate system prompt with schema"""
        return self.system_prompt_template.format(schema=schema)
    
    def send_message(self, messages: List[Dict[str, Any]], schema: str):
        """
        Send a message to Claude and handle tool calls
        
        Yields:
            Dict with type: 'text' or 'tool_call' or 'error'
        """
        from .sql_tools import SQLTools
        
        system_prompt = self.get_system_prompt(schema)
        conversation = messages.copy()
        
        while True:
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system_prompt,
                    messages=conversation,
                    tools=self.tools,
                )
                
                # Add response to conversation
                conversation.append({"role": "assistant", "content": response.content})
                
                # Check for text response
                for block in response.content:
                    if block.type == "text":
                        yield {"type": "text", "content": block.text}
                
                # Check for tool calls
                if response.stop_reason == "tool_use":
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            # Execute tool
                            result, is_error = SQLTools.execute_tool(
                                block.name, block.input
                            )
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result, default=str),
                                "is_error": is_error
                            })
                            
                            # Yield tool call info
                            yield {
                                "type": "tool_call",
                                "name": block.name,
                                "input": block.input,
                                "result": result,
                                "is_error": is_error
                            }
                    
                    conversation.append({"role": "user", "content": tool_results})
                    continue
                
                # Done
                break
                
            except Exception as e:
                logger.error(f"Claude API error: {e}")
                yield {"type": "error", "content": str(e)}
                break
