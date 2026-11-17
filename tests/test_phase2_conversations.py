
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import storage.database as database

from storage.database import initialize_database
from storage.agent_repository import AgentRepository
from storage.conversation_repository import ConversationRepository


class TestConversationPersistence(unittest.TestCase):

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
        self.conversation_repo = ConversationRepository()

        self.agent = self.agent_repo.create_agent(
            name="Content Writer",
            role="Content Writer",
            responsibility="Write content",
            system_prompt="You are a content writer.",
            owner_id="local-user",
        )

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_conversation_and_message_persistence(self):

        print("\n1. Creating agent conversation...")

        conversation = self.conversation_repo.create_conversation(
            title="My Writing Chat",
            agent_id=self.agent["agent_id"],
        )

        conversation_id = conversation["conversation_id"]

        self.assertEqual(
            conversation["agent_id"],
            self.agent["agent_id"],
        )

        print("Conversation created:", conversation_id)

        print("\n2. Saving messages...")

        self.conversation_repo.add_message(
            conversation_id=conversation_id,
            role="user",
            content="Write a short introduction about AI.",
        )

        self.conversation_repo.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content="Artificial intelligence enables machines to perform tasks.",
            metadata={"agent_id": self.agent["agent_id"]},
        )

        messages = self.conversation_repo.get_messages(
            conversation_id
        )

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "assistant")

        print("Saved messages:", len(messages))

        print("\n3. Simulating application restart...")

        initialize_database()

        recovered = self.conversation_repo.get_conversation(
            conversation_id
        )

        recovered_messages = self.conversation_repo.get_messages(
            conversation_id
        )

        self.assertIsNotNone(recovered)
        self.assertEqual(len(recovered_messages), 2)
        self.assertEqual(
            recovered_messages[1]["content"],
            "Artificial intelligence enables machines to perform tasks.",
        )

        print("Conversation recovered:", recovered["title"])
        print("Messages recovered:", len(recovered_messages))

        print("\n4. Checking conversation ownership...")

        inaccessible = self.conversation_repo.get_conversation(
            conversation_id,
            owner_id="another-user",
        )

        self.assertIsNone(inaccessible)

        with self.assertRaises(ValueError):
            self.conversation_repo.get_messages(
                conversation_id,
                owner_id="another-user",
            )

        print("Cross-user access correctly rejected.")

        print("\nALL PHASE 2A TESTS PASSED!")


if __name__ == "__main__":
    unittest.main()
