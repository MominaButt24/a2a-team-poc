import json
import uuid

from storage.database import get_db


VALID_STATUSES = {
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
}

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class TaskRepository:

    def create_task(
        self,
        title,
        description,
        owner_id="local-user",
        conversation_id=None,
    ):
        task_id = str(uuid.uuid4())

        with get_db() as conn:

            # Verify conversation ownership if supplied.
            if conversation_id:
                conversation = conn.execute(
                    """
                    SELECT conversation_id
                    FROM conversations
                    WHERE conversation_id = ?
                    AND owner_id = ?
                    """,
                    (conversation_id, owner_id),
                ).fetchone()

                if not conversation:
                    raise ValueError(
                        "Conversation not found or access denied."
                    )

            conn.execute(
                """
                INSERT INTO tasks (
                    task_id,
                    owner_id,
                    conversation_id,
                    title,
                    description
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    owner_id,
                    conversation_id,
                    title,
                    description,
                ),
            )

            self._insert_event(
                conn,
                task_id,
                "task_created",
                {"title": title},
            )

        print(f"Task created: {task_id}")
        return self.get_task(task_id, owner_id)

    def get_task(self, task_id, owner_id="local-user"):

        with get_db() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM tasks
                WHERE task_id = ?
                AND owner_id = ?
                """,
                (task_id, owner_id),
            ).fetchone()

        return dict(row) if row else None

    def list_tasks(self, owner_id="local-user", status=None):

        with get_db() as conn:

            if status:
                if status not in VALID_STATUSES:
                    raise ValueError("Invalid task status.")

                rows = conn.execute(
                    """
                    SELECT *
                    FROM tasks
                    WHERE owner_id = ?
                    AND status = ?
                    ORDER BY created_at DESC, rowid DESC
                    """,
                    (owner_id, status),
                ).fetchall()

            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM tasks
                    WHERE owner_id = ?
                    ORDER BY created_at DESC, rowid DESC
                    """,
                    (owner_id,),
                ).fetchall()

        return [dict(row) for row in rows]

    def update_task(
        self,
        task_id,
        owner_id="local-user",
        status=None,
        result=None,
        error=None,
    ):

        updates = []
        values = []

        if status is not None:
            if status not in VALID_STATUSES:
                raise ValueError("Invalid task status.")

            updates.append("status = ?")
            values.append(status)

        if result is not None:
            updates.append("result = ?")
            values.append(result)

        if error is not None:
            updates.append("error = ?")
            values.append(error)

        if not updates:
            raise ValueError("No task fields provided for update.")

        updates.append("updated_at = CURRENT_TIMESTAMP")

        if status in TERMINAL_STATUSES:
            updates.append("completed_at = CURRENT_TIMESTAMP")

        values.extend([task_id, owner_id])

        with get_db() as conn:

            existing = conn.execute(
                """
                SELECT status
                FROM tasks
                WHERE task_id = ?
                AND owner_id = ?
                """,
                (task_id, owner_id),
            ).fetchone()

            if not existing:
                raise ValueError("Task not found or access denied.")

            conn.execute(
                f"""
                UPDATE tasks
                SET {", ".join(updates)}
                WHERE task_id = ?
                AND owner_id = ?
                """,
                values,
            )

            self._insert_event(
                conn,
                task_id,
                "task_updated",
                {
                    "previous_status": existing["status"],
                    "new_status": status,
                    "result_updated": result is not None,
                    "error_updated": error is not None,
                },
            )

        return self.get_task(task_id, owner_id)

    def assign_agent(
        self,
        task_id,
        agent_id,
        owner_id="local-user",
    ):

        with get_db() as conn:

            task = conn.execute(
                """
                SELECT task_id
                FROM tasks
                WHERE task_id = ?
                AND owner_id = ?
                """,
                (task_id, owner_id),
            ).fetchone()

            if not task:
                raise ValueError("Task not found or access denied.")

            agent = conn.execute(
                """
                SELECT agent_id
                FROM agents
                WHERE agent_id = ?
                AND owner_id = ?
                AND status = 'active'
                """,
                (agent_id, owner_id),
            ).fetchone()

            if not agent:
                raise ValueError("Agent not found or is not active.")

            conn.execute(
                """
                INSERT INTO task_agents (
                    task_id,
                    agent_id
                )
                VALUES (?, ?)
                ON CONFLICT(task_id, agent_id) DO NOTHING
                """,
                (task_id, agent_id),
            )

            self._insert_event(
                conn,
                task_id,
                "agent_assigned",
                {"agent_id": agent_id},
            )

        return self.list_task_agents(task_id, owner_id)

    def list_task_agents(
        self,
        task_id,
        owner_id="local-user",
    ):

        with get_db() as conn:

            task = conn.execute(
                """
                SELECT task_id
                FROM tasks
                WHERE task_id = ?
                AND owner_id = ?
                """,
                (task_id, owner_id),
            ).fetchone()

            if not task:
                raise ValueError("Task not found or access denied.")

            rows = conn.execute(
                """
                SELECT
                    ta.task_id,
                    ta.agent_id,
                    ta.assigned_at,
                    ta.status,
                    a.name,
                    a.role
                FROM task_agents ta
                JOIN agents a ON a.agent_id = ta.agent_id
                WHERE ta.task_id = ?
                ORDER BY ta.assigned_at
                """,
                (task_id,),
            ).fetchall()

        return [dict(row) for row in rows]

    def update_agent_status(
        self,
        task_id,
        agent_id,
        status,
        owner_id="local-user",
    ):

        valid_agent_statuses = {
            "assigned",
            "working",
            "completed",
            "failed",
        }

        if status not in valid_agent_statuses:
            raise ValueError("Invalid agent task status.")

        with get_db() as conn:

            task = conn.execute(
                """
                SELECT task_id
                FROM tasks
                WHERE task_id = ?
                AND owner_id = ?
                """,
                (task_id, owner_id),
            ).fetchone()

            if not task:
                raise ValueError("Task not found or access denied.")

            cursor = conn.execute(
                """
                UPDATE task_agents
                SET status = ?
                WHERE task_id = ?
                AND agent_id = ?
                """,
                (status, task_id, agent_id),
            )

            if cursor.rowcount == 0:
                raise ValueError("Agent is not assigned to this task.")

            self._insert_event(
                conn,
                task_id,
                "agent_status_updated",
                {
                    "agent_id": agent_id,
                    "status": status,
                },
            )

        return self.list_task_agents(task_id, owner_id)

    def get_task_events(
        self,
        task_id,
        owner_id="local-user",
    ):

        with get_db() as conn:

            task = conn.execute(
                """
                SELECT task_id
                FROM tasks
                WHERE task_id = ?
                AND owner_id = ?
                """,
                (task_id, owner_id),
            ).fetchone()

            if not task:
                raise ValueError("Task not found or access denied.")

            rows = conn.execute(
                """
                SELECT *
                FROM task_events
                WHERE task_id = ?
                ORDER BY created_at, rowid
                """,
                (task_id,),
            ).fetchall()

        events = []

        for row in rows:
            event = dict(row)
            event["details"] = json.loads(
                event.pop("details_json")
            )
            events.append(event)

        return events

    @staticmethod
    def _insert_event(
        conn,
        task_id,
        event_type,
        details=None,
    ):

        conn.execute(
            """
            INSERT INTO task_events (
                event_id,
                task_id,
                event_type,
                details_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                task_id,
                event_type,
                json.dumps(details or {}),
            ),
        )
