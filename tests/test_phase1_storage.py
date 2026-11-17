import tempfile
import unittest

from pathlib import Path

import storage.database as database
from storage.agent_repository import AgentRepository


class TestAgentStorage(unittest.TestCase):

    def setUp(self):

        self.temp_dir = tempfile.TemporaryDirectory()

        # Use a temporary database so the test
        # does not modify your actual application database.
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"

        database.initialize_database()

        self.repository = AgentRepository()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_agent_persistence(self):

        print("\n1. Creating agent...")

        agent = self.repository.create_agent(
            name="Content Writer",
            role="Writer",
            responsibility="Create high-quality content",
            system_prompt="You are a professional content writer.",
            provider="groq",
            model="openai/gpt-oss-20b",
            config={
                "capabilities": ["writing", "editing"],
                "tools": [],
            },
        )

        agent_id = agent["agent_id"]

        print("Created:", agent["name"])
        print("ID:", agent_id)

        self.assertEqual(agent["name"], "Content Writer")

        print("\n2. Retrieving agent...")

        saved_agent = self.repository.get_agent(agent_id)

        self.assertEqual(saved_agent["agent_id"], agent_id)
        self.assertEqual(saved_agent["config"]["capabilities"], ["writing", "editing"])

        print("Retrieved:", saved_agent["name"])

        print("\n3. Updating agent...")

        updated_agent = self.repository.update_agent(
            agent_id,
            {
                "responsibility": "Write and edit professional content"
            },
        )

        self.assertEqual(
            updated_agent["version"],
            2,
        )

        print("Updated version:", updated_agent["version"])

        print("\n4. Simulating application restart...")

        database.initialize_database()

        restarted_agent = self.repository.get_agent(agent_id)

        self.assertIsNotNone(restarted_agent)
        self.assertEqual(restarted_agent["agent_id"], agent_id)

        print("Agent survived restart:", restarted_agent["name"])

        print("\n5. Archiving agent...")

        self.repository.archive_agent(agent_id)

        active_agents = self.repository.list_agents()
        all_agents = self.repository.list_agents(include_archived=True)

        self.assertEqual(len(active_agents), 0)
        self.assertEqual(len(all_agents), 1)
        self.assertEqual(all_agents[0]["status"], "archived")

        print("Archived successfully.")

        print("\nALL PHASE 1 STORAGE TESTS PASSED!")

if __name__ == "__main__":
    unittest.main()