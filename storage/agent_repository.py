import json
from uuid import uuid4

from storage.database import get_db


class AgentRepository:
    """Handles persistent storage of agent definitions."""

    def create_agent(
        self,
        name: str,
        role: str,
        responsibility: str,
        system_prompt: str,
        provider: str = "groq",
        model: str = "",
        config: dict | None = None,
        owner_id: str = "local-user",
    ):

        agent_id = str(uuid4())

        config_json = json.dumps(config or {})

        with get_db() as conn:

            conn.execute(
                """
                INSERT INTO agents (
                    agent_id,
                    owner_id,
                    name,
                    role,
                    responsibility,
                    system_prompt,
                    provider,
                    model,
                    config_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    owner_id,
                    name,
                    role,
                    responsibility,
                    system_prompt,
                    provider,
                    model,
                    config_json,
                ),
            )

        return self.get_agent(agent_id, owner_id)

    def get_agent(self, agent_id: str, owner_id: str = "local-user"):

        with get_db() as conn:

            row = conn.execute(
                """
                SELECT *
                FROM agents
                WHERE agent_id = ? AND owner_id = ?
                """,
                (agent_id, owner_id),
            ).fetchone()

        return self._to_dict(row)

    def list_agents(
        self,
        owner_id: str = "local-user",
        include_archived: bool = False,
    ):

        with get_db() as conn:

            if include_archived:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM agents
                    WHERE owner_id = ?
                    ORDER BY created_at DESC
                    """,
                    (owner_id,),
                ).fetchall()

            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM agents
                    WHERE owner_id = ? AND status = 'active'
                    ORDER BY created_at DESC
                    """,
                    (owner_id,),
                ).fetchall()

        return [self._to_dict(row) for row in rows]

    def update_agent(
        self,
        agent_id: str,
        updates: dict,
        owner_id: str = "local-user",
    ):

        allowed_fields = {
            "name",
            "role",
            "responsibility",
            "system_prompt",
            "provider",
            "model",
            "config",
        }

        invalid_fields = set(updates) - allowed_fields

        if invalid_fields:
            raise ValueError(
                f"Unsupported fields: {invalid_fields}"
            )

        if not updates:
            return self.get_agent(agent_id, owner_id)

        values = {}

        for key, value in updates.items():

            if key == "config":
                values["config_json"] = json.dumps(value or {})
            else:
                values[key] = value

        values["version"] = self._next_version(
            agent_id,
            owner_id,
        )

        values["updated_at"] = "CURRENT_TIMESTAMP"

        assignments = []

        params = []

        for key, value in values.items():

            if key == "updated_at":
                assignments.append("updated_at = CURRENT_TIMESTAMP")

            else:
                assignments.append(f"{key} = ?")
                params.append(value)

        params.extend([agent_id, owner_id])

        with get_db() as conn:

            cursor = conn.execute(
                f"""
                UPDATE agents
                SET {", ".join(assignments)}
                WHERE agent_id = ? AND owner_id = ?
                """,
                params,
            )

            if cursor.rowcount == 0:
                raise ValueError("Agent not found")

        return self.get_agent(agent_id, owner_id)

    def archive_agent(
        self,
        agent_id: str,
        owner_id: str = "local-user",
    ):

        with get_db() as conn:

            cursor = conn.execute(
                """
                UPDATE agents
                SET status = 'archived',
                    updated_at = CURRENT_TIMESTAMP
                WHERE agent_id = ? AND owner_id = ?
                """,
                (agent_id, owner_id),
            )

            if cursor.rowcount == 0:
                raise ValueError("Agent not found")

        return self.get_agent(agent_id, owner_id)

    def _next_version(self, agent_id, owner_id):

        with get_db() as conn:

            row = conn.execute(
                """
                SELECT version
                FROM agents
                WHERE agent_id = ? AND owner_id = ?
                """,
                (agent_id, owner_id),
            ).fetchone()

        if row is None:
            raise ValueError("Agent not found")

        return row["version"] + 1

    @staticmethod
    def _to_dict(row):

        if row is None:
            return None

        result = dict(row)

        result["config"] = json.loads(
            result.pop("config_json")
        )

        return result