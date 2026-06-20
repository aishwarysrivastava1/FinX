import os
import sqlite3

from dotenv import load_dotenv

load_dotenv(override=True)

DB_PATH = os.getenv("DATABASE_URL", "data/finx.db")


def get_conn():
    """
    Returns a SQLite connection with:
    - row_factory=sqlite3.Row so rows behave like dicts
    - WAL mode enabled for concurrent reads/writes (APScheduler + FastAPI run simultaneously)
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    """
    Idempotent schema creation. Safe to call multiple times.
    Called once at FastAPI startup via the @app.on_event('startup') hook.
    """
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS bulk_deals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            client_name TEXT,
            deal_type   TEXT,
            quantity    INTEGER,
            price       REAL,
            deal_date   TEXT,
            fetched_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS signals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id         INTEGER,
            symbol          TEXT NOT NULL,
            explanation     TEXT,
            signal_type     TEXT,
            risk_level      TEXT,
            confidence      INTEGER,
            key_observation TEXT,
            ai_provider     TEXT,
            disclaimer      TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (deal_id) REFERENCES bulk_deals(id)
        );

        CREATE TABLE IF NOT EXISTS news_cache (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol       TEXT,
            headline     TEXT,
            source       TEXT,
            url          TEXT,
            published_at TEXT,
            fetched_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS card_cache (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol     TEXT UNIQUE,
            card_json  TEXT,
            expires_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Price + indicator caches so the AI layer can distinguish
        -- fresh vs stale vs unavailable data.
        CREATE TABLE IF NOT EXISTS price_cache (
            symbol       TEXT PRIMARY KEY,
            price        REAL,
            change_pct  REAL,
            open         REAL,
            high         REAL,
            low          REAL,
            prev_close  REAL,
            volume       INTEGER,
            price_ts     TEXT,
            source       TEXT,
            freshness    TEXT,
            updated_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS close_series_cache (
            symbol       TEXT PRIMARY KEY,
            series_json  TEXT,
            series_ts    TEXT,
            source       TEXT,
            freshness    TEXT,
            updated_at   TEXT DEFAULT (datetime('now'))
        );

        -- Track AI usage (kept for legacy compatibility).
        CREATE TABLE IF NOT EXISTS gemini_usage (
            usage_date TEXT PRIMARY KEY,
            call_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_verified   INTEGER NOT NULL DEFAULT 0,
            verification_token TEXT,
            verification_expires_at TEXT,
            refresh_token_version INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_portfolios (
            user_id     INTEGER PRIMARY KEY,
            holdings_json TEXT NOT NULL,
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chat_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            session_id TEXT NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_signals_symbol  ON signals(symbol);
        CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_signals_symbol_created ON signals(symbol, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_signals_risk_level         ON signals(risk_level);
        CREATE INDEX IF NOT EXISTS idx_signals_signal_type      ON signals(signal_type);
        CREATE INDEX IF NOT EXISTS idx_chat_session    ON chat_sessions(session_id);
        CREATE INDEX IF NOT EXISTS idx_deals_symbol    ON bulk_deals(symbol);
    """
    )

    # Migrate existing DB: add key_observation if missing
    try:
        cur.execute('ALTER TABLE signals ADD COLUMN key_observation TEXT')
        print('[DB] Migrated: added key_observation column')
    except Exception:
        pass  # Column already exists — safe to ignore

    # Migrate existing DB: add ai_provider if missing
    try:
        cur.execute('ALTER TABLE signals ADD COLUMN ai_provider TEXT')
    except Exception:
        pass  # Column already exists — safe to ignore

    # Migrate existing DB: add user_id to chat sessions
    try:
        cur.execute('ALTER TABLE chat_sessions ADD COLUMN user_id INTEGER')
    except Exception:
        pass

    # Migrate existing DB: add index for user-scoped chat sessions
    try:
        cur.execute('CREATE INDEX IF NOT EXISTS idx_chat_user_session ON chat_sessions(user_id, session_id)')
    except Exception:
        pass

    # Migrate existing DB: add email verification columns
    try:
        cur.execute('ALTER TABLE users ADD COLUMN is_verified INTEGER NOT NULL DEFAULT 0')
        print('[DB] Migrated: added is_verified column')
    except Exception:
        pass
    try:
        cur.execute('ALTER TABLE users ADD COLUMN verification_token TEXT')
        print('[DB] Migrated: added verification_token column')
    except Exception:
        pass
    try:
        cur.execute('ALTER TABLE users ADD COLUMN verification_expires_at TEXT')
        print('[DB] Migrated: added verification_expires_at column')
    except Exception:
        pass
    try:
        cur.execute('ALTER TABLE users ADD COLUMN refresh_token_version INTEGER NOT NULL DEFAULT 0')
        print('[DB] Migrated: added refresh_token_version column')
    except Exception:
        pass

    conn.commit()
    conn.close()
    print("[DB] Initialized successfully")


def db_fetchall(query: str, params: tuple = ()) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_fetchone(query: str, params: tuple = ()) -> dict | None:
    conn = get_conn()
    row = conn.execute(query, params).fetchone()
    conn.close()
    return dict(row) if row else None


def db_execute(query: str, params: tuple = ()) -> int:
    conn = get_conn()
    cur = conn.execute(query, params)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id
