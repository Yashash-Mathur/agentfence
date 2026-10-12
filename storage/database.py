import os
import sqlite3
from typing import AsyncGenerator
import aiosqlite

DEFAULT_DB_PATH = os.getenv("DATABASE_PATH", "agentfence.db")


def configure_connection(conn: sqlite3.Connection):
    """Configures critical PRAGMAs for high-throughput concurrency and ACID safety."""
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    conn.execute("PRAGMA foreign_keys=ON;")


async def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> aiosqlite.Connection:
    """Creates an async SQLite connection with explicit PRAGMAs."""
    conn = await aiosqlite.connect(db_path, timeout=10.0, isolation_level=None)
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA synchronous=NORMAL;")
    await conn.execute("PRAGMA busy_timeout=10000;")
    await conn.execute("PRAGMA foreign_keys=ON;")
    return conn


async def init_schema(db_path: str = DEFAULT_DB_PATH):
    """Initializes strictly typed SQLite tables."""
    conn = await get_db_connection(db_path)
    try:
        # Schema versioning
        await conn.execute("PRAGMA user_version = 1;")

        # 1. Policies table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS policies (
                policy_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                policy_json TEXT NOT NULL,
                commitment_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_revoked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (policy_id, version)
            ) STRICT;
        """)

        # 2. Quota reservations table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS quota_reservations (
                reservation_id TEXT PRIMARY KEY,
                policy_id TEXT NOT NULL,
                window_bucket INTEGER NOT NULL,
                allocated_count INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            ) STRICT;
        """)

        # Index for fast quota window queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_quota_window 
            ON quota_reservations (policy_id, window_bucket);
        """)

        # 3. Audit events table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                policy_version INTEGER NOT NULL,
                tool_name TEXT NOT NULL,
                action_fingerprint TEXT NOT NULL,
                decision TEXT NOT NULL,
                execution_status TEXT NOT NULL,
                error_code TEXT,
                latency_ms REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            ) STRICT;
        """)

        # 4. Approvals table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_approvals (
                approval_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE,
                policy_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                action_fingerprint TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                resolved_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                resolved_at TEXT
            ) STRICT;
        """)

    finally:
        await conn.close()
