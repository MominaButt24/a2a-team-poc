
import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "app.db"
DB_PATH = Path(os.getenv("A2A_DB_PATH", str(DEFAULT_DB_PATH)))


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    return conn


@contextmanager
def get_db():
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
    with get_db() as conn:

        # -------------------------
        # AGENT DEFINITIONS
        # -------------------------

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

        # -------------------------
        # CONVERSATIONS
        # -------------------------

        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                agent_id TEXT,
                title TEXT NOT NULL DEFAULT 'New conversation',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (agent_id)
                    REFERENCES agents(agent_id)
                    ON DELETE SET NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_owner
            ON conversations(owner_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_agent
            ON conversations(agent_id)
        """)

        # -------------------------
        # MESSAGES
        # -------------------------

        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(conversation_id)
                    ON DELETE CASCADE
            )
        """)

        
        # Tasks
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                conversation_id TEXT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(conversation_id)
                    ON DELETE SET NULL
            )
        """)

        # Agents participating in tasks
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_agents (
                task_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'assigned',
                PRIMARY KEY (task_id, agent_id),
                FOREIGN KEY (task_id)
                    REFERENCES tasks(task_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (agent_id)
                REFERENCES agents(agent_id)
                ON DELETE CASCADE
            )
        """)

        # Task lifecycle events
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_events (
                event_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id)
                    REFERENCES tasks(task_id)
                    ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_owner
            ON tasks(owner_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status
            ON tasks(status)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_events_task
            ON task_events(task_id)
        """)


        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, created_at)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_owner
            ON messages(owner_id)
        """)

    print(f"Database initialized: {DB_PATH}")
