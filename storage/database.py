import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager


# Project root
BASE_DIR = Path(__file__).resolve().parent.parent

# Allow a custom database path through environment variables.
DEFAULT_DB_PATH = BASE_DIR / "data" / "app.db"
DB_PATH = Path(os.getenv("A2A_DB_PATH", str(DEFAULT_DB_PATH)))


def get_connection():
    """Create a SQLite database connection."""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    return conn


@contextmanager
def get_db():
    """Provide a connection and automatically commit or rollback."""

    conn = get_connection()

    try:
        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def initialize_database():
    """Create the database tables if they do not exist."""

    with get_db() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,

                name TEXT NOT NULL,
                role TEXT NOT NULL,
                responsibility TEXT NOT NULL,
                system_prompt TEXT NOT NULL,

                provider TEXT,
                model TEXT,

                config_json TEXT NOT NULL DEFAULT '{}',

                version INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agents_owner
            ON agents(owner_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agents_status
            ON agents(status)
        """)

    print(f"Database initialized: {DB_PATH}")