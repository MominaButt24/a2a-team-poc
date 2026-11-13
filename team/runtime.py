import asyncio
import httpx

from agents.agent_server import create_child_server
from a2a_comms.registry import AgentRegistry
from config.settings import settings


class TeamRuntime:
    """Manages the lifecycle of dynamically created A2A agents."""

    def __init__(self):
        self.registry = AgentRegistry()
        self.servers = {}
        self.server_tasks = {}

    async def start_team(self, children):
        """Start all child agents and register their Agent Cards."""

        for index, child in enumerate(children):
            port = settings.a2a_port_start + index
            host = settings.a2a_host

            endpoint = f"http://{host}:{port}/"

            self.registry.register(child, endpoint)

            server = create_child_server(child, host, port)

            self.servers[child.agent_id] = server

            self.server_tasks[child.agent_id] = asyncio.create_task(
                server.serve()
            )

            print(f"Starting {child.role} on port {port}")

        # Wait until all servers are ready.
        for child in children:
            await self._wait_for_server(child.agent_id)

        print("\nAll child agents are online.")

        return self.registry.get_all_agents()

    async def _wait_for_server(self, agent_id, timeout=20):
        """Wait for a server to start and discover its Agent Card."""

        server = self.servers[agent_id]
        task = self.server_tasks[agent_id]
        agent = self.registry.get_agent(agent_id)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while not server.started:
            if task.done():
                exception = task.exception()
                raise RuntimeError(
                    f"Agent {agent['role']} failed to start: {exception}"
                )

            if loop.time() >= deadline:
                raise TimeoutError(
                    f"Agent {agent['role']} did not start in time."
                )

            await asyncio.sleep(0.1)

        card_url = (
            agent["endpoint"].rstrip("/")
            + "/.well-known/agent-card.json"
        )

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(card_url)
            response.raise_for_status()
            card = response.json()

        self.registry.update_agent_card(agent_id, card)
        self.registry.update_status(agent_id, "online")

        print(f"Registered: {agent['role']}")

    async def stop_team(self):
        """Gracefully stop all child servers."""

        print("\nStopping child agents...")

        for server in self.servers.values():
            server.should_exit = True

        await asyncio.gather(
            *self.server_tasks.values(),
            return_exceptions=True,
        )

        self.servers.clear()
        self.server_tasks.clear()

        print("All child agents stopped.")
