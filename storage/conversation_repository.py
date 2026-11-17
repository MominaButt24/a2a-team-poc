
import json
from uuid import uuid4

from storage.database import get_db


class ConversationRepository:
    """Stores conversations and their messages."""

    VALID_ROLES = {"user", "assistant", "system", "tool"}

    def create_conversation(
        self,
        title="New conversation",
        agent_id=None,
        owner_id="local-user",
    ):
        conversation_id = str(uuid4())

        with get_db() as conn:

            # If this is an agent conversation, verify ownership.
            if agent_id is not None:
                agent = conn.execute(
                    """
                    SELECT agent_id
                    FROM agents
                    WHERE agent_id = ? AND owner_id = ?
                      AND status = 'active'
                    """,
                    (agent_id, owner_id),
                ).fetchone()

                if agent is None:
                    raise ValueError(
                        "Agent not found or does not belong to this user."
                    )

            conn.execute(
                """
                INSERT INTO conversations (
                    conversation_id,
                    owner_id,
                    agent_id,
                    title
                )
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, owner_id, agent_id, title),
            )

        return self.get_conversation(conversation_id, owner_id)

    def get_conversation(
        self,
        conversation_id,
        owner_id="local-user",
    ):
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM conversations
                WHERE conversation_id = ? AND owner_id = ?
                """,
                (conversation_id, owner_id),
            ).fetchone()

        return dict(row) if row else None

    def list_conversations(
        self,
        owner_id="local-user",
        agent_id=None,
    ):
        with get_db() as conn:

            if agent_id is None:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM conversations
                    WHERE owner_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (owner_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM conversations
                    WHERE owner_id = ? AND agent_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (owner_id, agent_id),
                ).fetchall()

        return [dict(row) for row in rows]

    def add_message(
        self,
        conversation_id,
        role,
        content,
        metadata=None,
        owner_id="local-user",
    ):
        if role not in self.VALID_ROLES:
            raise ValueError(f"Invalid message role: {role}")

        if not isinstance(content, str) or not content.strip():
            raise ValueError("Message content cannot be empty.")

        message_id = str(uuid4())

        with get_db() as conn:

            conversation = conn.execute(
                """
                SELECT conversation_id
                FROM conversations
                WHERE conversation_id = ? AND owner_id = ?
                """,
                (conversation_id, owner_id),
            ).fetchone()

            if conversation is None:
                raise ValueError(
                    "Conversation not found or access denied."
                )

            conn.execute(
                """
                INSERT INTO messages (
                    message_id,
                    conversation_id,
                    owner_id,
                    role,
                    content,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    owner_id,
                    role,
                    content,
                    json.dumps(metadata or {}),
                ),
            )

            conn.execute(
                """
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE conversation_id = ? AND owner_id = ?
                """,
                (conversation_id, owner_id),
            )

        return self.get_message(message_id, owner_id)

    def get_message(
        self,
        message_id,
        owner_id="local-user",
    ):
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE message_id = ? AND owner_id = ?
                """,
                (message_id, owner_id),
            ).fetchone()

        return self._to_dict(row)

    def get_messages(
        self,
        conversation_id,
        owner_id="local-user",
    ):
        with get_db() as conn:

            conversation = conn.execute(
                """
                SELECT conversation_id
                FROM conversations
                WHERE conversation_id = ? AND owner_id = ?
                """,
                (conversation_id, owner_id),
            ).fetchone()

            if conversation is None:
                raise ValueError(
                    "Conversation not found or access denied."
                )

            rows = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE conversation_id = ? AND owner_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (conversation_id, owner_id),
            ).fetchall()

        return [self._to_dict(row) for row in rows]

    @staticmethod
    def _to_dict(row):
        if row is None:
            return None

        result = dict(row)
        result["metadata"] = json.loads(
            result.pop("metadata_json")
        )

        return result
