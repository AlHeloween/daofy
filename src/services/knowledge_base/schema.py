"""
Knowledge base schema definitions — unified table-creation script + database connection management

All knowledge base builders (SmartCache, ProjectKB, ThirdPartyKB, GenericDocumentKB)
should obtain the CREATE TABLE SQL and get_connection() from this module, so that table
structures and PRAGMA settings stay consistent.

Note: do not import any heavy library here that would slow down the
ProcessPoolExecutor child processes. Current imports are stdlib only — safe.
"""

import contextlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# ============================================================
# Schema version management
# ============================================================
SCHEMA_VERSION = 3
"""
Current knowledge base schema version.
Incremented on every table-structure change; used at load time to detect an old
database and run the upgrade migration.

Version history:
  - 3: vocabularies gains AST enhancement columns (code_block, signature, modifiers, end_line, etc.)
       + entity_refs relation table + audit_results table
  - 2: vocabularies gains the (type, name, file_id) unique index and deduplication.
  - 1: initial version. vocabularies unified schema + relative_path + name_lower_rev reverse index + metadata version management
"""

SCHEMA_VERSION_KEY = 'schema_version'
"""Key name under which the schema version number is stored in the metadata table"""


def get_schema_version_from_db(cursor) -> int:
    """Read the schema version from the metadata table; 0 means no version information (legacy database)"""
    try:
        cursor.execute("SELECT value FROM metadata WHERE key = ?", (SCHEMA_VERSION_KEY,))
        row = cursor.fetchone()
        if row:
            return int(row[0])
    except Exception as e:
        logger.debug("Ignoring non-fatal exception: %s", str(e))
    return 0


def set_schema_version_in_db(cursor, version=None):
    """Write the schema version number into the metadata table"""
    v = version if version is not None else SCHEMA_VERSION
    cursor.execute(
        "INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
        (SCHEMA_VERSION_KEY, str(v), datetime.now().timestamp())
    )


def check_schema_version(cursor, kb_name: str = "unknown") -> bool:
    """
    Check whether the schema version matches.
    Returns True when the version matches or is compatible, False when a rebuild is needed.
    """
    stored = get_schema_version_from_db(cursor)
    if stored == 0:
        logger.info(f"[{kb_name}] Knowledge base has no version information; assuming legacy schema (v1)")
        return True  # legacy compatibility handling
    if stored == SCHEMA_VERSION:
        return True  # version matches
    logger.warning(f"[{kb_name}] Knowledge base schema version mismatch: current v{stored}, expected v{SCHEMA_VERSION}; a rebuild is recommended")
    return False


# ============================================================
# Source knowledge base table structures (files / vocabularies / metadata)
# ============================================================

SOURCE_FILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_path TEXT UNIQUE NOT NULL,
    relative_path TEXT,
    extension TEXT,
    size INTEGER,
    line_count INTEGER,
    hash TEXT,
    last_modified TEXT,
    category TEXT,
    units_defined TEXT,
    units_imported TEXT,
    description TEXT,
    scan_timestamp REAL,
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now'))
)
"""

SOURCE_VOCABULARIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vocabularies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    name_lower TEXT NOT NULL,
    name_lower_rev TEXT,
    file_id INTEGER,
    line INTEGER,
    base_class TEXT,
    description TEXT,
    vector BLOB,
    vector_status TEXT DEFAULT 'pending',
    attributes TEXT,
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
)
"""

SOURCE_METADATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL DEFAULT (julianday('now'))
)
"""

SOURCE_INDEXES_SQL: List[str] = [
    "CREATE INDEX IF NOT EXISTS idx_files_path ON files(relative_path)",
    "CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension)",
    "CREATE INDEX IF NOT EXISTS idx_files_category ON files(category)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_type ON vocabularies(type)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_name ON vocabularies(name)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_name_lower ON vocabularies(name_lower)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_name_lower_rev ON vocabularies(name_lower_rev)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_file_id ON vocabularies(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_vocabularies_vector_status ON vocabularies(vector_status)",
]


# ============================================================
# AST / semantic-analysis enhancement tables (Schema v3+)
# ============================================================

# vocabularies AST enhancement columns (ALTER TABLE ADD COLUMN migration)
# Note: comments live on the Python side; do not mix them into the SQL strings (pyright reports false positives)
VOCABULARIES_AST_COLUMNS_SQL: List[str] = [
    "ALTER TABLE vocabularies ADD COLUMN end_line INTEGER",
    "ALTER TABLE vocabularies ADD COLUMN end_offset INTEGER",
    "ALTER TABLE vocabularies ADD COLUMN body_length INTEGER",
    "ALTER TABLE vocabularies ADD COLUMN code_block TEXT",
    "ALTER TABLE vocabularies ADD COLUMN signature TEXT",
    "ALTER TABLE vocabularies ADD COLUMN modifiers TEXT",
    "ALTER TABLE vocabularies ADD COLUMN visibility TEXT",
    "ALTER TABLE vocabularies ADD COLUMN type_refs TEXT",
    "ALTER TABLE vocabularies ADD COLUMN member_count INTEGER",
    "ALTER TABLE vocabularies ADD COLUMN inheritance_chain TEXT",
    "ALTER TABLE vocabularies ADD COLUMN generics TEXT",
    "ALTER TABLE vocabularies ADD COLUMN values TEXT",
    "ALTER TABLE vocabularies ADD COLUMN params TEXT",
    "ALTER TABLE vocabularies ADD COLUMN return_type TEXT",
    "ALTER TABLE vocabularies ADD COLUMN calls TEXT",
    "ALTER TABLE vocabularies ADD COLUMN ref_count INTEGER DEFAULT 0",
    "ALTER TABLE vocabularies ADD COLUMN source TEXT DEFAULT 'regex'",
]

# Entity reference relation table (basis of the reference graph)
ENTITY_REFS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS entity_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    target_name TEXT NOT NULL,
    target_kind TEXT,
    target_file_id INTEGER,
    ref_type TEXT NOT NULL,
    line INTEGER,
    code_snippet TEXT,
    created_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (source_id) REFERENCES vocabularies(id) ON DELETE CASCADE
)
"""

ENTITY_REFS_INDEXES_SQL: List[str] = [
    "CREATE INDEX IF NOT EXISTS idx_entity_refs_source ON entity_refs(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_entity_refs_target ON entity_refs(target_name, target_kind)",
    "CREATE INDEX IF NOT EXISTS idx_entity_refs_target_file ON entity_refs(target_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_entity_refs_type ON entity_refs(ref_type)",
]

# Audit results cache table
AUDIT_RESULTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT NOT NULL,
    file_path TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    line INTEGER,
    code_snippet TEXT,
    message TEXT,
    is_ai_confirmed INTEGER DEFAULT 0,
    fix_suggestion TEXT,
    scan_timestamp REAL,
    created_at REAL DEFAULT (julianday('now')),
    UNIQUE(project_path, file_path, rule_id, line)
)
"""

AUDIT_RESULTS_INDEXES_SQL: List[str] = [
    "CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_results(project_path)",
    "CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_results(severity)",
    "CREATE INDEX IF NOT EXISTS idx_audit_rule ON audit_results(rule_id)",
]


def create_source_tables(cursor):
    """Create all tables + indexes of the source knowledge base"""
    cursor.execute(SOURCE_FILES_TABLE_SQL)
    cursor.execute(SOURCE_VOCABULARIES_TABLE_SQL)
    cursor.execute(SOURCE_METADATA_TABLE_SQL)
    for sql in SOURCE_INDEXES_SQL:
        cursor.execute(sql)


def drop_source_tables(cursor):
    """Drop all tables of the source knowledge base"""
    cursor.execute("DROP TABLE IF EXISTS audit_results")
    cursor.execute("DROP TABLE IF EXISTS entity_refs")
    cursor.execute("DROP TABLE IF EXISTS vocabularies")
    cursor.execute("DROP TABLE IF EXISTS files")
    cursor.execute("DROP TABLE IF EXISTS metadata")


def migrate_vocabularies_ast_columns(cursor):
    """
    Migration: add the AST enhancement columns to the vocabularies table (Schema v2 → v3).
    Safely idempotent: each ADD COLUMN is guarded by an IF NOT EXISTS equivalent.
    For a column that already exists a SQL error is raised; ignoring it is fine.
    """
    for sql in VOCABULARIES_AST_COLUMNS_SQL:
        try:
            cursor.execute(sql)
        except (sqlite3.OperationalError, sqlite3.ProgrammingError):
            pass  # column already exists; ignore
    logger.info("vocabularies AST enhancement column migration complete")


def create_ast_tables(cursor):
    """Create the AST / semantic-analysis enhancement tables (entity_refs + audit_results)"""
    cursor.execute(ENTITY_REFS_TABLE_SQL)
    for sql in ENTITY_REFS_INDEXES_SQL:
        cursor.execute(sql)
    cursor.execute(AUDIT_RESULTS_TABLE_SQL)
    for sql in AUDIT_RESULTS_INDEXES_SQL:
        cursor.execute(sql)


def drop_ast_tables(cursor):
    """Drop the AST enhancement tables"""
    cursor.execute("DROP TABLE IF EXISTS audit_results")
    cursor.execute("DROP TABLE IF EXISTS entity_refs")


# ============================================================
# Document knowledge base table structures (deprecated — the document KB now uses ZVec)
# These definitions are retained for reading legacy databases; new KBs no longer use SQLite
# ============================================================

DOCUMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    full_path TEXT NOT NULL,
    extension TEXT,
    title TEXT,
    title_lower TEXT,
    title_rev TEXT,
    content TEXT,
    content_type TEXT,
    file_size INTEGER,
    size INTEGER,
    line_count INTEGER,
    hash TEXT,
    last_modified TEXT,
    sections TEXT,
    code_examples TEXT,
    url TEXT,
    requires_extraction INTEGER DEFAULT 0,
    language TEXT DEFAULT 'en'
)
"""

DOCUMENT_ENTITIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS document_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER,
    definition TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id)
)
"""

DOCUMENTS_INDEXES_SQL: List[str] = [
    "CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path)",
    "CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(hash)",
    "CREATE INDEX IF NOT EXISTS idx_documents_title_lower ON documents(title_lower)",
    "CREATE INDEX IF NOT EXISTS idx_documents_title_rev ON documents(title_rev)",
    "CREATE INDEX IF NOT EXISTS idx_documents_language ON documents(language)",
    "CREATE INDEX IF NOT EXISTS idx_document_entities_name ON document_entities(name)",
]

# Document knowledge bases also record build information in the unified metadata table
DOCUMENTS_METADATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL DEFAULT (julianday('now'))
)
"""


def create_document_tables(cursor):
    """Create all tables + indexes of the document knowledge base"""
    cursor.execute(DOCUMENTS_TABLE_SQL)
    cursor.execute(DOCUMENT_ENTITIES_TABLE_SQL)
    cursor.execute(DOCUMENTS_METADATA_TABLE_SQL)
    for sql in DOCUMENTS_INDEXES_SQL:
        cursor.execute(sql)


def drop_document_tables(cursor):
    """Drop all tables of the document knowledge base"""
    cursor.execute("DROP TABLE IF EXISTS document_entities")
    cursor.execute("DROP TABLE IF EXISTS documents")
    cursor.execute("DROP TABLE IF EXISTS metadata")


# ============================================================
# Common PRAGMA settings
# ============================================================

def get_connection(db_path: str, use_wal: bool = True) -> sqlite3.Connection:
    """
    Create a SQLite connection and apply the unified performance PRAGMA settings.

    All knowledge base code should obtain connections through this function, ensuring:
    - Consistent PRAGMA settings (avoid mixing WAL/DELETE, which leads to "locked")
    - A unified busy_timeout (avoids "database is locked")
    - Centralised tuning of connection parameters later

    Args:
        db_path: Database file path
        use_wal: Whether to use WAL mode (build = WAL for write performance; query = DELETE to avoid leftover .wal files)

    Returns:
        A configured sqlite3.Connection
    """
    conn = sqlite3.connect(str(db_path))
    apply_performance_pragmas(conn, use_wal=use_wal)
    return conn


@contextlib.contextmanager
def use_connection(db_path: str, use_wal: bool = True) -> Iterator[sqlite3.Connection]:
    """
    Safe context: create a connection → yield → close automatically.
    Even if an exception is raised in between, conn.close() is guaranteed to be called, avoiding resource leaks.

    Args:
        db_path: Database file path
        use_wal: Whether to use WAL mode

    Yields:
        sqlite3.Connection
    """
    conn = None
    try:
        conn = get_connection(db_path, use_wal=use_wal)
        yield conn
    finally:
        if conn is not None:
            conn.close()


def apply_performance_pragmas(conn, use_wal: bool = False):
    """
    Apply SQLite performance-tuning PRAGMAs

    Args:
        conn: SQLite connection
        use_wal: Whether to use WAL mode. WAL is used uniformly to avoid mode-switching conflicts
                 (DELETE mode needs an exclusive lock and reports "locked" when the same DB
                 already has a WAL connection)
    """
    if use_wal:
        conn.execute("PRAGMA journal_mode=WAL")
    else:
        # Queries also use WAL mode, to avoid conflicting with existing WAL connections
        # PRAGMA journal_mode=DELETE needs an exclusive lock and would report "database is locked"
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-200000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA locking_mode=NORMAL")


__all__ = [
    'SCHEMA_VERSION',
    'SCHEMA_VERSION_KEY',
    'get_schema_version_from_db',
    'set_schema_version_in_db',
    'check_schema_version',
    'SOURCE_FILES_TABLE_SQL',
    'SOURCE_VOCABULARIES_TABLE_SQL',
    'SOURCE_METADATA_TABLE_SQL',
    'SOURCE_INDEXES_SQL',
    'VOCABULARIES_AST_COLUMNS_SQL',
    'ENTITY_REFS_TABLE_SQL',
    'ENTITY_REFS_INDEXES_SQL',
    'AUDIT_RESULTS_TABLE_SQL',
    'AUDIT_RESULTS_INDEXES_SQL',
    'create_source_tables',
    'drop_source_tables',
    'migrate_vocabularies_ast_columns',
    'create_ast_tables',
    'drop_ast_tables',
    'DOCUMENTS_TABLE_SQL',
    'DOCUMENT_ENTITIES_TABLE_SQL',
    'DOCUMENTS_INDEXES_SQL',
    'create_document_tables',
    'drop_document_tables',
    'get_connection',
    'use_connection',
    'apply_performance_pragmas',
]
