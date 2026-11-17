
import asyncio
import httpx

from agents.agent_server import create_child_server
from a2a_comms.registry import AgentRegistry
from config.settings import settings


class TeamRuntime:
    """Manages the lifecycle of temporary and persistent A2A agents."""

    def __init__(self):

        # Tracks currently running agents and their endpoints.
        self.registry = AgentRegistry()

        # Keeps live Uvicorn server instances.
        self.servers = {}

        # Keeps the asyncio tasks running those servers.
        self.server_tasks = {}

        # Port allocation for this runtime instance.
        self.next_port = settings.a2a_port_start

    # ==================================================
    # START AGENTS
    # ==================================================

    async def start_team(self, children):
        """
        Start a temporary team.

        Kept for compatibility with the existing demo.
        """

        return await self.start_agents(children)

    async def start_agents(self, children):
        """
        Start one or more already-constructed ChildAgent objects.

        This method works for both temporary and saved agents.
        """

        newly_started = []

        try:

            for child in children:

                # Do not start the same agent twice.
                if child.agent_id in self.servers:
                    continue

                port = self._allocate_port()
                host = settings.a2a_host

                endpoint = f"http://{host}:{port}/"

                # Register the agent before starting its server.
                self.registry.register(child, endpoint)

                server = create_child_server(
                    child,
                    host,
                    port,
                )

                self.servers[child.agent_id] = server

                self.server_tasks[child.agent_id] = (
                    asyncio.create_task(server.serve())
                )

                newly_started.append(child)

                print(
                    f"Starting {child.role} "
                    f"on port {port}"
                )

            # Wait for each newly started server and its Agent Card.
            for child in newly_started:
                await self._wait_for_server(child.agent_id)

        except Exception:

            # If startup fails, clean up the servers started
            # during this operation.
            for child in newly_started:
                await self.stop_agent(child.agent_id)

            raise

        print("\nAll requested agents are online.")

        return [
            self.registry.get_agent(child.agent_id)
            for child in children
        ]

    async def start_saved_agent(
        self,
        factory,
        agent_id: str,
        owner_id: str = "local-user",
        event_callback=None,
    ):
        """
        Load one permanent agent from SQLite,
        reconstruct its runnable, and start its A2A server.
        """

        child = factory.load_saved_agent(
            agent_id=agent_id,
            registry=self.registry,
            owner_id=owner_id,
            event_callback=event_callback,
        )

        agents = await self.start_agents([child])

        return agents[0]

    async def start_saved_agents(
        self,
        factory,
        owner_id: str = "local-user",
        event_callback=None,
    ):
        """
        Load all active saved agents from SQLite
        and bring them online.
        """

        children = factory.load_saved_agents(
            registry=self.registry,
            owner_id=owner_id,
            event_callback=event_callback,
        )

        return await self.start_agents(children)

    # ==================================================
    # PORT ALLOCATION
    # ==================================================

    def _allocate_port(self):
        """Allocate the next port for this runtime."""

        port = self.next_port
        self.next_port += 1

        return port

    # ==================================================
    # SERVER READINESS
    # ==================================================

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
                    f"Agent {agent['role']} failed to start: "
                    f"{exception}"
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

    # ==================================================
    # STOP AGENTS
    # ==================================================

    async def stop_agent(self, agent_id: str):
        """
        Stop one running agent.

        Its permanent database definition is not deleted.
        """

        server = self.servers.get(agent_id)
        task = self.server_tasks.get(agent_id)

        if server is None:
            return

        print(
            f"Stopping agent: "
            f"{agent_id}"
        )

        server.should_exit = True

        if task is not None:

            await asyncio.gather(
                task,
                return_exceptions=True,
            )

        self.servers.pop(agent_id, None)
        self.server_tasks.pop(agent_id, None)

        self.registry.update_status(
            agent_id,
            "offline",
        )

        print("Agent stopped. Its saved definition remains intact.")

    async def stop_team(self):
        """
        Stop all currently running agents.

        This stops runtimes, not permanent agent definitions.
        """

        print("\nStopping all running agents...")

        agent_ids = list(self.servers.keys())

        await asyncio.gather(
            *(
                self.stop_agent(agent_id)
                for agent_id in agent_ids
            ),
            return_exceptions=True,
        )

        print("All running agents stopped.")