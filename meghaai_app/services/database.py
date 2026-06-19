"""Database connection and query execution services with connection pooling"""

import os
import logging
import pymysql
from pymysql.cursors import DictCursor
from django.conf import settings
from sshtunnel import SSHTunnelForwarder
import decimal
from datetime import datetime, date
from dbutils.pooled_db import PooledDB
import threading

logger = logging.getLogger(__name__)

class DatabaseConnectionPool:
    """Manages database connection pool with SSH tunneling"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.config = settings.MEGHAAI_CONFIG
        self._use_ssh = bool(self.config.get('SSH_HOST'))
        self._tunnel = None
        self._tunnel_lock = threading.Lock()
        self._pool = None
        self._pool_initialized = False
        self._pool_lock = threading.Lock()
        
        # Connection pool settings
        self._pool_size = self.config.get('DB_POOL_SIZE', 15)
        self._max_pool_size = self.config.get('DB_MAX_POOL_SIZE', 30)
        
        self._start_tunnel_if_needed()
        self._init_pool()
    
    def _start_tunnel_if_needed(self):
        """Start SSH tunnel if configured - thread-safe"""
        if not self._use_ssh:
            return
        
        with self._tunnel_lock:
            if self._tunnel is not None and self._tunnel.is_active:
                return
            
            try:
                import paramiko
                
                # Fix for paramiko version compatibility
                if not hasattr(paramiko, "DSSKey"):
                    paramiko.DSSKey = paramiko.RSAKey
                
                kwargs = {
                    "ssh_username": self.config['SSH_USER'],
                    "remote_bind_address": (self.config['MYSQL_HOST'], self.config['MYSQL_PORT']),
                }
                
                if self.config.get('SSH_KEY_FILE'):
                    kwargs["ssh_pkey"] = self.config['SSH_KEY_FILE']
                    if self.config.get('SSH_KEY_PASSPHRASE'):
                        kwargs["ssh_private_key_password"] = self.config['SSH_KEY_PASSPHRASE']
                
                if self.config.get('SSH_PASSWORD'):
                    kwargs["ssh_password"] = self.config['SSH_PASSWORD']
                
                self._tunnel = SSHTunnelForwarder(
                    (self.config['SSH_HOST'], self.config['SSH_PORT']),
                    **kwargs
                )
                self._tunnel.start()
                logger.info(f"SSH tunnel established to {self.config['SSH_HOST']}")
                
            except Exception as e:
                logger.error(f"Failed to establish SSH tunnel: {e}")
                raise
    
    def _init_pool(self):
        """Initialize the connection pool"""
        with self._pool_lock:
            if self._pool_initialized:
                return
            
            try:
                if self._use_ssh and self._tunnel:
                    host, port = "127.0.0.1", self._tunnel.local_bind_port
                else:
                    host, port = self.config['MYSQL_HOST'], self.config['MYSQL_PORT']
                
                # Create connection pool
                self._pool = PooledDB(
                    creator=pymysql,
                    maxconnections=self._max_pool_size,
                    mincached=self._pool_size,
                    maxcached=self._max_pool_size,
                    maxshared=10,
                    blocking=True,
                    maxusage=None,
                    setsession=[],
                    ping=1,  # Ping connection before use
                    host=host,
                    port=port,
                    user=self.config['MYSQL_USER'],
                    password=self.config['MYSQL_PASSWORD'],
                    database=self.config['MYSQL_DATABASE'],
                    cursorclass=DictCursor,
                    charset="utf8mb4",
                    connect_timeout=10,
                    read_timeout=max(30, self.config.get('QUERY_TIMEOUT_MS', 30000) // 1000 + 5),
                    autocommit=True,
                )
                
                self._pool_initialized = True
                logger.info(f"Database connection pool initialized (min: {self._pool_size}, max: {self._max_pool_size})")
                
            except Exception as e:
                logger.error(f"Failed to initialize connection pool: {e}")
                raise
    
    def get_connection(self):
        """Get a connection from the pool"""
        if not self._pool_initialized:
            self._init_pool()
        
        try:
            return self._pool.connection()
        except Exception as e:
            logger.error(f"Failed to get connection from pool: {e}")
            # Try to reinitialize
            self._pool_initialized = False
            self._init_pool()
            return self._pool.connection()
    
    def execute_query(self, sql, params=None):
        """Execute a SELECT query and return results"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Set query timeout if supported
            try:
                cursor.execute("SET SESSION MAX_EXECUTION_TIME=%s", 
                             (self.config.get('QUERY_TIMEOUT_MS', 30000),))
            except pymysql.err.MySQLError:
                pass
            
            cursor.execute(sql, params or ())
            rows = cursor.fetchall()
            
            # Convert to JSON-safe format
            def make_json_safe(value):
                if isinstance(value, (date, datetime)):
                    return value.isoformat()
                if isinstance(value, decimal.Decimal):
                    return float(value)
                if isinstance(value, bytes):
                    return value.decode('utf-8', errors='replace')
                return value
            
            safe_rows = []
            for row in rows:
                safe_rows.append({k: make_json_safe(v) for k, v in row.items()})
            
            return safe_rows
            
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()  # Returns connection to pool
    
    def close_all(self):
        """Close all connections in the pool"""
        if self._pool:
            self._pool.close()
            self._pool = None
            self._pool_initialized = False
            logger.info("Connection pool closed")
        
        if self._tunnel:
            try:
                self._tunnel.stop()
                self._tunnel = None
                logger.info("SSH tunnel closed")
            except Exception as e:
                logger.error(f"Error closing tunnel: {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close_all()

# Singleton instance with thread-safe locking
_db_pool = None

def get_db_connection():
    """Get the singleton database connection pool"""
    global _db_pool
    if _db_pool is None:
        _db_pool = DatabaseConnectionPool()
    return _db_pool
