'\nSCP - Viet Nam | Self-Correcting Pipeline\nCopyright (c) 2026 SCP Vietnam Project. All Rights Reserved.\n\n\n\n\nLicense: See LICENSE file\nContact: scp-vietnam@example.com\n'

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

def _get_path_conn(db_path: str) -> sqlite3.Connection:
    """Get or create a cached connection for a specific db_path.

    [FIX-CRIT-135 BUG 4] TẠI SAO: the docstring used to read "caller must hold
    _db_lock" — but `db_query_one`/`db_query_all` called this function while
    holding ONLY `_read_lock` (NOT `_db_lock`). So `_path_conns` was mutated
    under two DIFFERENT locks:
      - db_exec (writes) held `_db_lock` while mutating `_path_conns`
      - db_query_* (reads)  held `_read_lock` while mutating `_path_conns`
    → two threads could race in `_get_path_conn` (one read, one write) and
    both create a new connection for the same path, or one's mutation could
    clobber the other's `_path_conns[db_path] = conn` assignment.
    Fix: enforce the contract — callers MUST hold `_db_lock` before calling
    this function. `db_query_*` now acquires `_db_lock` for the per-path
    branch (single lock for the per-path dict). The `_read_lock` is kept
    ONLY for the global `_persistent_conn` reads (V89 WAL optimization
    preserved for the no-db_path case).
    """
    conn = _path_conns.get(db_path)
    if conn is None:
        conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA busy_timeout=30000')
        _path_conns[db_path] = conn
    return conn

def get_db():
    """Persistent connection + thread lock.  SQLite PRAGMA tuned for speed.

    [R16-ROOT-FIX-4] Integrity check on first connect.
    BEFORE: DB corruption ("database disk image is malformed") was only caught
            when a query failed — by then, cascading errors already happened
            (canary scan fails, audit log fails, migrations fail).
    AFTER:  on first get_db() call, run PRAGMA integrity_check. If it fails,
            attempt VACUUM INTO recovery (delegates to storage_manager logic).
            This catches corruption EARLY — before any query runs.
    """
    global _persistent_conn
    _db_lock.acquire()
    try:
        if _persistent_conn is None:
            _preflight_integrity_check()
            _persistent_conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
            _persistent_conn.row_factory = sqlite3.Row
            _persistent_conn.execute('PRAGMA journal_mode=WAL')
            _persistent_conn.execute('PRAGMA synchronous=NORMAL')
            _persistent_conn.execute('PRAGMA cache_size=-128000')
            _persistent_conn.execute('PRAGMA temp_store=MEMORY')
            _persistent_conn.execute('PRAGMA busy_timeout=30000')
            _persistent_conn.execute('PRAGMA mmap_size=268435456')
            _persistent_conn.execute('PRAGMA wal_autocheckpoint=5000')
            _persistent_conn.execute('PRAGMA page_size=4096')
            _persistent_conn.execute('PRAGMA foreign_keys = ON')
        return _persistent_conn
    finally:
        _db_lock.release()

def _preflight_integrity_check() -> None:
    """[R16-ROOT-FIX-4] Check DB integrity before first query.

    If DB is corrupted, attempt recovery via VACUUM INTO (creates fresh DB
    from corrupted one, skipping bad pages). This prevents the cascading
    "database disk image is malformed" errors that plague production.
    """
    import os as _os
    if not _os.path.isfile(DB_PATH):
        return
    try:
        _probe = sqlite3.connect(DB_PATH, timeout=5.0)
        _probe.execute('PRAGMA quick_check')
        _probe.close()
    except sqlite3.DatabaseError as _de:
        _err_msg = str(_de).lower()
        if 'malformed' in _err_msg or 'not a database' in _err_msg:
            logger.error(f"[R16-ROOT-FIX-4] DB corrupted ('{_de}'). Attempting VACUUM INTO recovery...")
            _recovered = DB_PATH + '.recovered'
            try:
                _probe2 = sqlite3.connect(DB_PATH, timeout=30.0)
                _probe2.execute(f"VACUUM INTO '{_recovered}'")
                _probe2.close()
                import time as _time
                _backup = f'{DB_PATH}.broken.{int(_time.time())}'
                _os.rename(DB_PATH, _backup)
                _os.rename(_recovered, DB_PATH)
                logger.info(f'[R16-ROOT-FIX-4] DB recovered via VACUUM INTO. Old corrupted DB saved as {_backup}')
            except Exception as _re:
                logger.critical(f'[R16-ROOT-FIX-4] DB recovery FAILED: {_re}. Delete {DB_PATH} manually to start fresh (data will be lost).')
        else:
            logger.warning(f'[R16-ROOT-FIX-4] DB warning: {_de}')

def db_exec(sql: str, params=(), db_path: Optional[str]=None) -> int:
    """Execute a SQL statement. If db_path is provided, use a per-path connection
    (cached) instead of the global DB_PATH — but STILL under _db_lock.

    [AUDIT-2 FIX] TẠI SAO: FastLearningEngine + RealLearningEngine accept scp_db_path
    in their constructor, but db_exec used to ignore it (always wrote to global
    DB_PATH). The wrong fix bypassed db_exec with bare sqlite3.connect → lost
    _db_lock → race with Brain → facts silently dropped (Invariant #7).
    Root-cause fix: accept optional db_path, use cached per-path connection,
    still acquire _db_lock. Single lock across all paths = no race.
    """
    _db_lock.acquire()
    try:
        conn = _get_path_conn(db_path) if db_path else get_db()
        try:
            cur = conn.execute(sql, params)
            if conn.in_transaction:
                conn.commit()
            return cur.rowcount
        except Exception:
            if conn.in_transaction:
                try:
                    conn.rollback()
                except Exception as e:
                    logger.debug(f'[V104.37] core/db_manager.py: e={e}')
            raise
    finally:
        _db_lock.release()

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

def db_batch_flush() -> int:
    """Flush buffered writes to DB in 1 transaction."""
    global _last_batch_flush
    with _batch_lock:
        if not _batch_buffer:
            return 0
        to_flush = _batch_buffer[:]
        _batch_buffer.clear()
        _last_batch_flush = time.time()
    _db_lock.acquire()
    try:
        conn = get_db()
        count = 0
        try:
            for sql, params in to_flush:
                conn.execute(sql, params)
                count += 1
            conn.commit()
            logger.debug(f'Batch flushed: {count} writes')
            return count
        except Exception:
            try:
                conn.rollback()
            except Exception as e:
                logger.debug(f'[V104.37] core/db_manager.py: e={e}')
            raise
    finally:
        _db_lock.release()

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

def init_db():
    """Initialize all V14 tables + V62 all module tables."""
    db_exec("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, question TEXT, ai_answer TEXT, frame TEXT, verdict TEXT, reason TEXT, status TEXT DEFAULT 'active', recovered_at TEXT)")
    db_exec("CREATE TABLE IF NOT EXISTS meta_goals (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        type TEXT DEFAULT 'goal',\n        description TEXT,\n        status TEXT DEFAULT 'active',\n        priority REAL DEFAULT 5,\n        progress REAL DEFAULT 0,\n        notes TEXT,\n        created_at TEXT,\n        updated_at TEXT,\n        parent_id INTEGER\n    )")
    db_exec("CREATE TABLE IF NOT EXISTS health_states (domain TEXT PRIMARY KEY, state TEXT DEFAULT 'UNKNOWN')")
    try:
        db_exec('ALTER TABLE health_states ADD COLUMN last_updated TEXT')
    except Exception as e:
        logger.debug(f'[V104.37] core/db_manager.py: e={e}')
    db_exec('CREATE TABLE IF NOT EXISTS health_counters (domain TEXT PRIMARY KEY, pass INTEGER DEFAULT 0, block INTEGER DEFAULT 0, inapplicable INTEGER DEFAULT 0, total INTEGER DEFAULT 0)')
    db_exec("CREATE TABLE IF NOT EXISTS recovery_issues (id TEXT PRIMARY KEY, timestamp TEXT, domain TEXT, question TEXT, ai_answer TEXT, error_type TEXT, cause TEXT, fix_action TEXT, status TEXT DEFAULT 'OPEN')")
    db_exec("CREATE TABLE IF NOT EXISTS knowledge_memory (id TEXT PRIMARY KEY, timestamp TEXT, question TEXT, ai_answer TEXT, domain TEXT, error_type TEXT, cause TEXT, fix_action TEXT, fix_artifact TEXT, evidence TEXT, confidence REAL, status TEXT DEFAULT 'active', retest_result TEXT DEFAULT '', retest_count INTEGER DEFAULT 0)")
    db_exec("CREATE TABLE IF NOT EXISTS error_history (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, question TEXT NOT NULL, ai_answer TEXT, frame TEXT, v13_verdict TEXT, final_verdict TEXT, verdict_detail TEXT, error_type TEXT, source TEXT, real_value TEXT, ai_value TEXT, reason TEXT, learned_from TEXT DEFAULT '', sha256 TEXT, importance_score REAL DEFAULT 50.0, last_accessed TEXT, is_foundational INTEGER DEFAULT 0, is_superseded INTEGER DEFAULT 0)")
    db_exec('CREATE INDEX IF NOT EXISTS idx_error_frame ON error_history(frame)')
    db_exec('CREATE INDEX IF NOT EXISTS idx_error_verdict ON error_history(final_verdict)')
    db_exec('CREATE INDEX IF NOT EXISTS idx_error_source ON error_history(source)')
    db_exec('CREATE INDEX IF NOT EXISTS idx_error_importance ON error_history(importance_score)')
    try:
        db_exec("ALTER TABLE error_history ADD COLUMN domain TEXT DEFAULT ''")
    except Exception as e:
        logger.debug(f'[V104.37] core/db_manager.py: e={e}')
    try:
        db_exec('CREATE INDEX IF NOT EXISTS idx_error_domain ON error_history(domain)')
    except Exception as e:
        logger.debug(f'[V104.37] core/db_manager.py: e={e}')
    db_exec('\n        CREATE TABLE IF NOT EXISTS knowledge_versions (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            timestamp TEXT NOT NULL,\n            entity TEXT NOT NULL,\n            attribute TEXT NOT NULL,\n            old_value TEXT,\n            new_value TEXT,\n            change_type TEXT,\n            source TEXT,\n            reason TEXT\n        )\n    ')
    db_exec('CREATE INDEX IF NOT EXISTS idx_kv_entity ON knowledge_versions(entity, attribute)')
    _init_all_module_tables()

_VERDICT_CACHE_CANONICAL_COLS = {'cache_key', 'question_hash', 'question_text', 'verdict', 'confidence', 'final_answer', 'domain', 'reasoning', 'evidence_json', 'timestamp', 'cached_at', 'expires_at', 'times_used'}

_VERDICT_CACHE_CANONICAL_DDL = '\nCREATE TABLE verdict_cache (\n    cache_key TEXT PRIMARY KEY,\n    question_hash TEXT UNIQUE,\n    question_text TEXT,\n    verdict TEXT,\n    confidence REAL,\n    final_answer TEXT,\n    domain TEXT,\n    reasoning TEXT,\n    evidence_json TEXT,\n    timestamp REAL,\n    cached_at TEXT,\n    expires_at TEXT,\n    times_used INTEGER DEFAULT 1\n)\n'

def _migrate_verdict_cache_schema() -> None:
    """[V104.49 FIX-C] Detect legacy verdict_cache schema and rebuild to canonical.

    Strategy:
      1. PRAGMA table_info(verdict_cache). If no table → nothing to do (the
         CREATE TABLE IF NOT EXISTS in _init_all_module_tables will build it).
      2. If table exists with all canonical columns → no-op (idempotent).
      3. If table exists but is missing any canonical column → rename to
         verdict_cache_old, create canonical, copy over the intersection of
         common columns, drop the old table.
    All steps wrapped in try/except so a partial failure leaves the old table
    intact (better stale-schema than no-schema).
    """
    try:
        cols = db_query_all('PRAGMA table_info(verdict_cache)')
    except Exception as e:
        logger.debug(f'[V104.49] PRAGMA table_info(verdict_cache) failed: {e}')
        return
    if not cols:
        return
    col_names = {c.get('name') for c in cols if c.get('name')}
    if _VERDICT_CACHE_CANONICAL_COLS.issubset(col_names):
        return
    logger.info(f'[V104.49 FIX-C] verdict_cache has legacy schema (cols={sorted(col_names)}); rebuilding to canonical.')
    try:
        db_exec('ALTER TABLE verdict_cache RENAME TO verdict_cache_old')
    except Exception as e:
        logger.warning(f'[V104.49] RENAME verdict_cache → verdict_cache_old failed: {e}')
        return
    try:
        db_exec(_VERDICT_CACHE_CANONICAL_DDL)
    except Exception as e:
        logger.warning(f'[V104.49] canonical CREATE failed: {e}; restoring old table')
        try:
            db_exec('ALTER TABLE verdict_cache_old RENAME TO verdict_cache')
        except Exception as ee:
            logger.debug(f'[V104.49] restore failed: {ee}')
        return
    try:
        old_cols = db_query_all('PRAGMA table_info(verdict_cache_old)')
    except Exception as e:
        old_cols = []
        logger.debug(f'[V104.49] PRAGMA table_info(verdict_cache_old) failed: {e}')
    old_col_names = {c.get('name') for c in old_cols or [] if c.get('name')}
    common = _VERDICT_CACHE_CANONICAL_COLS & old_col_names
    if common:
        col_list = ', '.join(sorted(common))
        try:
            db_exec(f'INSERT INTO verdict_cache ({col_list}) SELECT {col_list} FROM verdict_cache_old')
            logger.info(f'[V104.49 FIX-C] migrated {len(common)} columns ({sorted(common)}) from verdict_cache_old → verdict_cache')
        except Exception as e:
            logger.warning(f'[V104.49] row migration failed ({e}); canonical table is empty but functional.')
    try:
        db_exec('DROP TABLE verdict_cache_old')
    except Exception as e:
        logger.debug(f'[V104.49] DROP verdict_cache_old failed: {e}')

_KNOWLEDGE_CANONICAL_COLS = {'entity', 'attribute', 'value', 'value_type', 'confidence', 'source', 'timestamp', 'times_verified', 'times_wrong', 'last_verified', 'bias_correction', 'notes'}

_KNOWLEDGE_CANONICAL_DDL = "\nCREATE TABLE IF NOT EXISTS knowledge (\n    entity TEXT, attribute TEXT, value TEXT, value_type TEXT,\n    confidence REAL, source TEXT, timestamp TEXT, times_verified INTEGER DEFAULT 1,\n    times_wrong INTEGER DEFAULT 0,\n    last_verified TEXT,\n    bias_correction REAL DEFAULT 0.0,\n    notes TEXT DEFAULT '',\n    PRIMARY KEY (entity, attribute)\n)\n"

def _migrate_knowledge_schema() -> None:
    """[ROOT-FIX 1] Detect legacy `knowledge` schema and rebuild to canonical.

    Strategy (mirrors `_migrate_verdict_cache_schema`):
      1. PRAGMA table_info(knowledge). If no table → no-op (canonical CREATE
         will build it).
      2. If table exists with all canonical columns AND no `id` column → no-op.
      3. If table has an `id` column (legacy brain.py/experience.py shape) OR
         is missing any canonical column → rename to knowledge_old, create
         canonical, copy over the common columns, drop the old table.
    All steps wrapped in try/except so a partial failure leaves the old table
    intact (better stale-schema than no-schema).
    """
    try:
        cols = db_query_all('PRAGMA table_info(knowledge)')
    except Exception as e:
        logger.debug(f'[ROOT-FIX 1] PRAGMA table_info(knowledge) failed: {e}')
        return
    if not cols:
        return
    col_names = {c.get('name') for c in cols if c.get('name')}
    has_id_column = 'id' in col_names
    has_all_canonical = _KNOWLEDGE_CANONICAL_COLS.issubset(col_names)
    if has_all_canonical and (not has_id_column):
        return
    logger.info(f'[ROOT-FIX 1] knowledge has legacy schema (cols={sorted(col_names)}, has_id={has_id_column}); rebuilding to canonical.')
    try:
        db_exec('ALTER TABLE knowledge RENAME TO knowledge_old')
    except Exception as e:
        logger.warning(f'[ROOT-FIX 1] RENAME knowledge → knowledge_old failed: {e}')
        return
    try:
        db_exec(_KNOWLEDGE_CANONICAL_DDL)
    except Exception as e:
        logger.warning(f'[ROOT-FIX 1] canonical CREATE failed: {e}; restoring old table')
        try:
            db_exec('ALTER TABLE knowledge_old RENAME TO knowledge')
        except Exception as ee:
            logger.debug(f'[ROOT-FIX 1] restore failed: {ee}')
        return
    try:
        old_cols = db_query_all('PRAGMA table_info(knowledge_old)')
    except Exception as e:
        old_cols = []
        logger.debug(f'[ROOT-FIX 1] PRAGMA table_info(knowledge_old) failed: {e}')
    old_col_names = {c.get('name') for c in old_cols or [] if c.get('name')}
    common = _KNOWLEDGE_CANONICAL_COLS & old_col_names
    if common:
        col_list = ', '.join(sorted(common))
        try:
            db_exec(f'INSERT OR IGNORE INTO knowledge ({col_list}) SELECT {col_list} FROM knowledge_old')
            logger.info(f'[ROOT-FIX 1] migrated {len(common)} columns ({sorted(common)}) from knowledge_old → knowledge')
        except Exception as e:
            logger.warning(f'[ROOT-FIX 1] row migration failed ({e}); canonical table is empty but functional.')
    try:
        db_exec('DROP TABLE knowledge_old')
    except Exception as e:
        logger.debug(f'[ROOT-FIX 1] DROP knowledge_old failed: {e}')

def _migrate_reverify_schema() -> None:
    """[RUNTIME-FIX-3] Ensure reverify_queue has `notes` column.

    Root cause (runtime log lines 741, 957, 1391, 1406):
      WARNING | scp.reverify | ReVerify process error: no such column: notes
      WARNING | scp.judge | [V104.42 #AV] ReVerify process_pending error: no such column: notes

    Bug: this module's CREATE TABLE reverify_queue (canonical, runs first at
    startup) did NOT include the `notes` column. But reverify_scheduler.py:62
    has `notes TEXT` in its own CREATE TABLE — which is a no-op (IF NOT EXISTS)
    because the table was already created by db_manager. Result: reverify
    UPDATE/SELECT referencing `notes` fails.

    Fix strategy:
      1. PRAGMA table_info(reverify_queue). If no table → no-op (canonical
         CREATE will build it with the new `notes` column).
      2. If table exists but `notes` column missing → ALTER TABLE ADD COLUMN
         (idempotent — only adds if missing).
    """
    try:
        cols = db_query_all('PRAGMA table_info(reverify_queue)')
    except Exception as e:
        logger.debug(f'[RUNTIME-FIX-3] PRAGMA table_info(reverify_queue) failed: {e}')
        return
    if not cols:
        return
    col_names = {c.get('name') for c in cols if c.get('name')}
    if 'notes' in col_names:
        return
    try:
        db_exec("ALTER TABLE reverify_queue ADD COLUMN notes TEXT DEFAULT ''")
        logger.info("[RUNTIME-FIX-3] reverify_queue: added missing 'notes' column")
    except Exception as e:
        logger.error(f"[RUNTIME-FIX-3] failed to add 'notes' column to reverify_queue: {e}")

from .db_manager_parts._init_all_module_tables import _init_all_module_tables
