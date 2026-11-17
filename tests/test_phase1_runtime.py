
import asyncio
import unittest

from unittest.mock import Mock, patch

from agents.factory import ChildAgent
from team.runtime import TeamRuntime


class FakeServer:
    """A lightweight stand-in for a real Uvicorn server."""

    def __init__(self):
        self.started = False
        self.should_exit = False

    async def serve(self):

        self.started = True

        while not self.should_exit:
            await asyncio.sleep(0.01)


class TestPersistentAgentRuntime(unittest.IsolatedAsyncioTestCase):

    async def test_start_and_stop_saved_agent(self):

        print("\n1. Preparing a saved agent...")

        child = ChildAgent(
            agent_id="saved-agent-123",
            role="Content Writer",
            responsibility="Write and edit content",
            runnable=object(),
        )

        factory = Mock()

        factory.load_saved_agent.return_value = child

        runtime = TeamRuntime()

        fake_server = FakeServer()

        # Simulate successful server readiness without
        # making an actual HTTP request.
        async def mark_online(agent_id, timeout=20):
            runtime.registry.update_status(
                agent_id,
                "online",
            )

        with patch(
            "team.runtime.create_child_server",
            return_value=fake_server,
        ):

            with patch.object(
                runtime,
                "_wait_for_server",
                side_effect=mark_online,
            ):

                print("\n2. Starting the saved agent...")

                agent = await runtime.start_saved_agent(
                    factory=factory,
                    agent_id="saved-agent-123",
                )

                self.assertEqual(
                    agent["agent_id"],
                    "saved-agent-123",
                )

                self.assertEqual(
                    agent["status"],
                    "online",
                )

                self.assertIn(
                    "saved-agent-123",
                    runtime.servers,
                )

                print("Agent:", agent["role"])
                print("Endpoint:", agent["endpoint"])
                print("Status:", agent["status"])

                print("\n3. Checking saved agent identity...")

                factory.load_saved_agent.assert_called_once()

                loaded_child = (
                    factory.load_saved_agent.call_args.kwargs
                )

                self.assertEqual(
                    loaded_child["agent_id"],
                    "saved-agent-123",
                )

                self.assertIs(
                    loaded_child["registry"],
                    runtime.registry,
                )

                print("Same permanent ID confirmed.")

                print("\n4. Stopping the agent...")

                await runtime.stop_agent("saved-agent-123")

                self.assertNotIn(
                    "saved-agent-123",
                    runtime.servers,
                )

                self.assertNotIn(
                    "saved-agent-123",
                    runtime.server_tasks,
                )

                stopped_agent = runtime.registry.get_agent(
                    "saved-agent-123"
                )

                self.assertEqual(
                    stopped_agent["status"],
                    "offline",
                )

                print("Runtime stopped.")
                print("Registry status:", stopped_agent["status"])

        print("\nALL PHASE 1 RUNTIME TESTS PASSED!")


if __name__ == "__main__":
    unittest.main()
