"""Database schema discovery and catalog building"""

import logging
# At the top of database.py, ensure you have:
import decimal # ✅ Already present
from django.conf import settings
from .database import get_db_connection
from datetime import datetime, date  # ✅ Add this import

logger = logging.getLogger(__name__)

class SchemaCatalog:
    """Builds and caches database schema information"""
    
    def __init__(self):
        self.db = get_db_connection()
        self._catalog = None
        self._table_names = None
        self._max_catalog_size = 16000
    
    def get_tables(self):
        """Get list of all tables"""
        if self._table_names is None:
            rows = self.db.execute_query(
                "SELECT table_name FROM information_schema.tables WHERE table_schema=%s",
                (settings.MEGHAAI_CONFIG['MYSQL_DATABASE'],)
            )
            self._table_names = {r["table_name"] for r in rows}
        return self._table_names
    
    def get_table_schema(self, table_name: str):
        """Get schema for a specific table"""
        if table_name not in self.get_tables():
            raise ValueError(f"Unknown table: {table_name}")
        
        columns = self.db.execute_query(
            """
            SELECT column_name, column_type, is_nullable, column_key, column_comment
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (settings.MEGHAAI_CONFIG['MYSQL_DATABASE'], table_name)
        )
        
        # Get sample rows
        sample = self.db.execute_query(f"SELECT * FROM `{table_name}` LIMIT 3")
        
        # ✅ Convert sample rows to JSON-safe format
        def make_json_safe(value):
            if isinstance(value, (date, datetime)):
                return value.isoformat()
            if isinstance(value, decimal.Decimal):
                return float(value)
            if isinstance(value, bytes):
                return value.decode('utf-8', errors='replace')
            return value
        
        safe_sample = []
        for row in sample:
            safe_sample.append({k: make_json_safe(v) for k, v in row.items()})
        
        return {
            "table": table_name,
            "columns": columns,
            "sample_rows": safe_sample
        }
    
    def build_catalog(self):
        """Build a text description of the database schema"""
        if self._catalog is not None:
            return self._catalog
        
        # Get all columns
        cols = self.db.execute_query(
            """
            SELECT table_name, column_name, column_type, column_comment
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
            """,
            (settings.MEGHAAI_CONFIG['MYSQL_DATABASE'],)
        )
        
        # Group by table
        by_table = {}
        for c in cols:
            line = f"{c['column_name']} {c['column_type']}"
            if c["column_comment"]:
                line += f" -- {c['column_comment']}"
            by_table.setdefault(c["table_name"], []).append(line)
        
        # Get foreign keys
        fks = self.db.execute_query(
            """
            SELECT table_name, column_name, referenced_table_name, referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_schema = %s AND referenced_table_name IS NOT NULL
            ORDER BY table_name
            """,
            (settings.MEGHAAI_CONFIG['MYSQL_DATABASE'],)
        )
        
        # Build catalog text
        parts = [
            f"Database `{settings.MEGHAAI_CONFIG['MYSQL_DATABASE']}` has {len(by_table)} tables:\n"
        ]
        
        for table, lines in by_table.items():
            parts.append(f"TABLE {table}")
            for line in lines:
                parts.append(f"  - {line}")
            parts.append("")
        
        if fks:
            parts.append("FOREIGN KEYS (use these for JOINs):")
            for fk in fks:
                parts.append(
                    f"  - {fk['table_name']}.{fk['column_name']} -> "
                    f"{fk['referenced_table_name']}.{fk['referenced_column_name']}"
                )
        
        catalog = "\n".join(parts)
        
        # Truncate if too large
        if len(catalog) > self._max_catalog_size:
            catalog = catalog[:self._max_catalog_size] + "\n... (schema truncated)"
        
        self._catalog = catalog
        return catalog

# Singleton
_schema_catalog = None

def get_schema_catalog():
    """Get singleton schema catalog"""
    global _schema_catalog
    if _schema_catalog is None:
        _schema_catalog = SchemaCatalog()
    return _schema_catalog
