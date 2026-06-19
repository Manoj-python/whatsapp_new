"""SQL security validation and sanitization"""

import re
import logging

logger = logging.getLogger(__name__)

# Blocked SQL keywords (write operations and dangerous functions)
BANNED_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|"
    r"into\s+outfile|into\s+dumpfile|load_file|benchmark|sleep)\b",
    re.IGNORECASE,
)

class SQLSecurityError(Exception):
    """Raised when SQL query fails security checks"""
    pass

def sanitize_sql(query: str, max_rows: int = 500) -> str:
    """
    Validate and sanitize a SQL query.
    
    Args:
        query: Raw SQL query string
        max_rows: Maximum rows to return
    
    Returns:
        Sanitized SQL query
    
    Raises:
        SQLSecurityError: If query fails security checks
    """
    q = (query or "").strip().rstrip(";").strip()
    
    if not q:
        raise SQLSecurityError("Empty query")
    
    # Check for multiple statements
    if ";" in q:
        raise SQLSecurityError("Multiple SQL statements not allowed")
    
    # Check query type
    low = q.lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise SQLSecurityError("Only SELECT and WITH queries are allowed")
    
    # Check for banned keywords
    hit = BANNED_KEYWORDS.search(q)
    if hit:
        raise SQLSecurityError(f"Disallowed keyword: '{hit.group(0)}'")
    
    # Ensure LIMIT is present and capped
    if not re.search(r"\blimit\b", low):
        q = f"{q}\nLIMIT {max_rows}"
    else:
        # Parse and cap existing LIMIT
        limit_match = re.search(r"limit\s+(\d+)", low, re.IGNORECASE)
        if limit_match and int(limit_match.group(1)) > max_rows:
            q = re.sub(r"limit\s+\d+", f"LIMIT {max_rows}", q, flags=re.IGNORECASE)
    
    logger.info(f"SQL query validated: {q[:100]}...")
    return q

def validate_table_name(table_name: str, known_tables: set) -> bool:
    """Validate that a table name exists in the database"""
    return table_name in known_tables
