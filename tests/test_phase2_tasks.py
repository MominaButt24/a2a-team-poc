
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

import storage.database as database

from storage.database import initialize_database
from storage.agent_repository import AgentRepository
from storage.task_repository import TaskRepository


class TestTaskPersistence(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"

        self.db_patch = patch.object(
            database,
            "DB_PATH",
            self.db_path,
        )
        self.db_patch.start()

        initialize_database()

        self.agent_repo = AgentRepository()
        self.task_repo = TaskRepository()

        self.agent = self.agent_repo.create_agent(
            name="Content Writer",
            role="Writer",
            responsibility="Write content",
            system_prompt="You are a content writer.",
            owner_id="local-user",
        )

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_task_lifecycle_and_persistence(self):

        print("\n1. Creating task...")

        task = self.task_repo.create_task(
            title="Prepare AI Research Report",
            description="Research and prepare a report.",
        )

        task_id = task["task_id"]

        self.assertEqual(task["status"], "pending")

        print("\n2. Assigning specialist...")

        agents = self.task_repo.assign_agent(
            task_id,
            self.agent["agent_id"],
        )

        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["name"], "Content Writer")

        print("\n3. Updating task and agent status...")

        self.task_repo.update_agent_status(
            task_id,
            self.agent["agent_id"],
            "working",
        )

        updated_task = self.task_repo.update_task(
            task_id,
            status="running",
        )

        self.assertEqual(updated_task["status"], "running")

        self.task_repo.update_agent_status(
            task_id,
            self.agent["agent_id"],
            "completed",
        )

        self.task_repo.update_task(
            task_id,
            status="completed",
            result="Research report prepared.",
        )

        print("\n4. Checking task events...")

        events = self.task_repo.get_task_events(task_id)

        self.assertGreaterEqual(len(events), 5)

        print("\n5. Simulating application restart...")

        initialize_database()

        recovered_task = self.task_repo.get_task(task_id)

        self.assertIsNotNone(recovered_task)
        self.assertEqual(recovered_task["status"], "completed")
        self.assertEqual(
            recovered_task["result"],
            "Research report prepared.",
        )

        recovered_agents = self.task_repo.list_task_agents(task_id)

        self.assertEqual(len(recovered_agents), 1)
        self.assertEqual(recovered_agents[0]["status"], "completed")

        print("Task recovered:", recovered_task["title"])
        print("Task events recovered:", len(events))

        print("\n6. Checking ownership protection...")

        self.assertIsNone(
            self.task_repo.get_task(
                task_id,
                owner_id="another-user",
            )
        )

        with self.assertRaises(ValueError):
            self.task_repo.update_task(
                task_id,
                owner_id="another-user",
                status="failed",
            )

        print("Cross-user access correctly rejected.")

        print("\nALL PHASE 2B TESTS PASSED!")


if __name__ == "__main__":
    unittest.main()
