
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

import storage.database as database

from agents.factory import AgentFactory, AgentSpec
from storage.agent_repository import AgentRepository


class TestPersistentAgentFactory(unittest.TestCase):

    def setUp(self):

        self.temp_dir = tempfile.TemporaryDirectory()

        database.DB_PATH = Path(self.temp_dir.name) / "test.db"

        database.initialize_database()

        # Avoid initializing a real LLM.
        self.factory = AgentFactory.__new__(AgentFactory)

        self.factory.repository = AgentRepository()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_reconstruct_agent(self):

        print("\n1. Creating agent definition...")

        spec = AgentSpec(
            role="Content Writer",
            responsibility="Create and edit professional content",
            instructions="Write clearly and accurately.",
        )

        saved = self.factory.save_agent(
            spec=spec,
            config={
                "capabilities": ["writing", "editing"]
            },
        )

        agent_id = saved["agent_id"]

        print("Saved:", saved["name"])
        print("Permanent ID:", agent_id)

        self.assertEqual(saved["role"], "Content Writer")
        self.assertEqual(saved["version"], 1)

        print("\n2. Reconstructing agent...")

        fake_model = object()

        with patch.object(
            self.factory,
            "_build_model",
            return_value=fake_model,
        ) as mock_model:

            with patch(
                "agents.factory.create_deep_agent",
                return_value="FAKE_RUNNABLE",
            ) as mock_deep_agent:

                child = self.factory.load_saved_agent(agent_id)

        self.assertEqual(child.agent_id, agent_id)
        self.assertEqual(child.role, "Content Writer")
        self.assertEqual(child.runnable, "FAKE_RUNNABLE")

        mock_model.assert_called_once()
        mock_deep_agent.assert_called_once()

        print("Reconstructed:", child.role)
        print("Same permanent ID:", child.agent_id)

        print("\n3. Simulating database restart...")

        database.initialize_database()

        with patch.object(
            self.factory,
            "_build_model",
            return_value=fake_model,
        ):

            with patch(
                "agents.factory.create_deep_agent",
                return_value="RESTARTED_RUNNABLE",
            ):

                restarted_child = self.factory.load_saved_agent(
                    agent_id
                )

        self.assertEqual(restarted_child.agent_id, agent_id)

        print("Agent recovered:", restarted_child.role)
        print("ID remained unchanged.")

        print("\n4. Loading all saved agents...")

        with patch.object(
            self.factory,
            "_build_model",
            return_value=fake_model,
        ):

            with patch(
                "agents.factory.create_deep_agent",
                return_value="FAKE_RUNNABLE",
            ):

                agents = self.factory.load_saved_agents()

        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0].agent_id, agent_id)

        print("Loaded agents:", len(agents))

        print("\nALL PHASE 1B TESTS PASSED!")


if __name__ == "__main__":
    unittest.main()
