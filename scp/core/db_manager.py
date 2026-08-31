from .db_manager_parts._get_path_conn import _get_path_conn
from .db_manager_parts.get_db import get_db
from .db_manager_parts._preflight_integrity_check import _preflight_integrity_check
from .db_manager_parts.db_exec import db_exec
from .db_manager_parts.db_batch_flush import db_batch_flush
from .db_manager_parts.init_db import init_db
from .db_manager_parts._init_all_module_tables import _init_all_module_tables
from .db_manager_parts._migrate_verdict_cache_schema import _migrate_verdict_cache_schema
from .db_manager_parts._migrate_knowledge_schema import _migrate_knowledge_schema
from .db_manager_parts._migrate_reverify_schema import _migrate_reverify_schema

"""
SCP - Viet Nam | Self-Correcting Pipeline
Copyright (c) 2026 SCP Vietnam Project. All Rights Reserved.




License: See LICENSE file
Contact: scp-vietnam@example.com
"""
'\nSCP V14 — Database Manager\nQuản lý kết nối SQLite, auto-cleanup, archive gzip.\n'
import gzip
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime
from typing import Optional
logger = logging.getLogger(__name__)
_RUNTIME_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(_RUNTIME_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'v13.db')
_persistent_conn = None
_db_lock = threading.RLock()
_path_conns: dict[str, sqlite3.Connection] = {}
_batch_buffer: list[tuple[str, tuple]] = []
_batch_lock = threading.Lock()
_BATCH_SIZE = 100
_BATCH_TIMEOUT = 1.0
_last_batch_flush = time.time()

def db_batch_exec(sql: str, params: tuple) -> None:
    """Buffer writes → flush in batch (100x faster than 1-by-1)."""
    with _batch_lock:
        _batch_buffer.append((sql, params))
        should_flush = len(_batch_buffer) >= _BATCH_SIZE or time.time() - _last_batch_flush > _BATCH_TIMEOUT
    if should_flush:
        db_batch_flush()
_read_lock = threading.Lock()

def db_query_all(sql: str, params=(), db_path: Optional[str]=None) -> list[dict]:
    if db_path:
        with _db_lock:
            conn = _get_path_conn(db_path)
    else:
        with _read_lock:
            conn = get_db()
    return [dict(r) for r in conn.execute(sql, params).fetchall()]

def db_query_one(sql: str, params=(), db_path: Optional[str]=None) -> Optional[dict]:
    if db_path:
        with _db_lock:
            conn = _get_path_conn(db_path)
    else:
        with _read_lock:
            conn = get_db()
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None

def checkpoint_wal():
    try:
        conn = get_db()
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    except Exception as e:
        logger.debug(f'[V104.37] core/db_manager.py: e={e}')

def vacuum_db():
    """ VACUUM database để reclaim disk space.
    Run định kỳ (mỗi 1000 cycles hoặc khi DB > 100MB).
    """
    try:
        conn = get_db()
        conn.execute('VACUUM')
        logger.info(' DB VACUUM complete')
        return True
    except Exception as e:
        logger.warning(f' VACUUM error: {e}')
        return False

def get_db_size_mb() -> float:
    """ Get DB file size in MB."""
    try:
        import os
        return os.path.getsize(str(DB_PATH)) / (1024 * 1024)
    except Exception:
        return 0.0
_VERDICT_CACHE_CANONICAL_COLS = {'cache_key', 'question_hash', 'question_text', 'verdict', 'confidence', 'final_answer', 'domain', 'reasoning', 'evidence_json', 'timestamp', 'cached_at', 'expires_at', 'times_used'}
_VERDICT_CACHE_CANONICAL_DDL = '\nCREATE TABLE verdict_cache (\n    cache_key TEXT PRIMARY KEY,\n    question_hash TEXT UNIQUE,\n    question_text TEXT,\n    verdict TEXT,\n    confidence REAL,\n    final_answer TEXT,\n    domain TEXT,\n    reasoning TEXT,\n    evidence_json TEXT,\n    timestamp REAL,\n    cached_at TEXT,\n    expires_at TEXT,\n    times_used INTEGER DEFAULT 1\n)\n'
_KNOWLEDGE_CANONICAL_COLS = {'entity', 'attribute', 'value', 'value_type', 'confidence', 'source', 'timestamp', 'times_verified', 'times_wrong', 'last_verified', 'bias_correction', 'notes'}
_KNOWLEDGE_CANONICAL_DDL = "\nCREATE TABLE IF NOT EXISTS knowledge (\n    entity TEXT, attribute TEXT, value TEXT, value_type TEXT,\n    confidence REAL, source TEXT, timestamp TEXT, times_verified INTEGER DEFAULT 1,\n    times_wrong INTEGER DEFAULT 0,\n    last_verified TEXT,\n    bias_correction REAL DEFAULT 0.0,\n    notes TEXT DEFAULT '',\n    PRIMARY KEY (entity, attribute)\n)\n"
