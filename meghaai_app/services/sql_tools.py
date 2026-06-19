"""SQL tool implementations for Claude"""

import json
import logging
import decimal
from datetime import datetime, date, timedelta  # ✅ Correct import
from typing import Dict, Any, Tuple
from .database import get_db_connection
from .schema_builder import get_schema_catalog
from .security import sanitize_sql, validate_table_name
from django.conf import settings

logger = logging.getLogger(__name__)

class SQLTools:
    """Tools that Claude can call"""
    
    @staticmethod
    def list_tables() -> Dict[str, Any]:
        """List all tables in the database"""
        db = get_db_connection()
        
        rows = db.execute_query(
            """
            SELECT table_name, table_rows as approx_rows, table_comment as comment
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name
            """,
            (settings.MEGHAAI_CONFIG['MYSQL_DATABASE'],)
        )
        
        return {
            "database": settings.MEGHAAI_CONFIG['MYSQL_DATABASE'],
            "table_count": len(rows),
            "tables": rows
        }
    
    @staticmethod
    def describe_table(table_name: str) -> Dict[str, Any]:
        """Describe a table structure and show sample rows"""
        schema = get_schema_catalog()
        tables = schema.get_tables()
        
        if table_name not in tables:
            raise ValueError(f"Unknown table '{table_name}'")
        
        return schema.get_table_schema(table_name)
    
    @staticmethod
    def run_sql(query: str) -> Dict[str, Any]:
        """Execute a guarded SQL query"""
        max_rows = settings.MEGHAAI_CONFIG.get('MAX_ROWS', 500)
        
        # Validate and sanitize
        safe_sql = sanitize_sql(query, max_rows)
        
        # Execute
        db = get_db_connection()
        rows = db.execute_query(safe_sql)
        
        # ✅ FIXED: Proper JSON serialization
        def make_json_safe(value):
            if isinstance(value, (date, datetime)):
                return value.isoformat()
            if isinstance(value, decimal.Decimal):
                return float(value)
            if isinstance(value, bytes):
                return value.decode('utf-8', errors='replace')
            if isinstance(value, timedelta):
                return str(value)
            return value
        
        safe_rows = []
        for row in rows[:max_rows]:
            safe_rows.append({k: make_json_safe(v) for k, v in row.items()})
        
        return {
            "sql_executed": safe_sql,
            "row_count": len(safe_rows),
            "truncated": len(rows) >= max_rows,
            "columns": list(safe_rows[0].keys()) if safe_rows else [],
            "rows": safe_rows
        }
    
    @staticmethod
    def execute_tool(name: str, input_data: Dict) -> Tuple[Any, bool]:
        """Execute a tool and return (result, is_error)"""
        try:
            if name == "list_tables":
                result = SQLTools.list_tables()
            elif name == "describe_table":
                result = SQLTools.describe_table(input_data.get("table_name"))
            elif name == "run_sql":
                result = SQLTools.run_sql(input_data.get("query"))
            else:
                return f"Unknown tool: {name}", True
            
            return result, False
            
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return str(e), True
