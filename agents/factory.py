from dataclasses import dataclass
from uuid import uuid4

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_anthropic import ChatAnthropic
from deepagents import create_deep_agent

from config.settings import settings

from a2a_comms.peer_tools import (
    create_peer_tool,
    create_list_peers_tool,
)
from a2a_comms.registry import AgentRegistry

from storage.database import initialize_database
from storage.agent_repository import AgentRepository


# ---------- Dynamic team plan ----------

class AgentSpec(BaseModel):
    role: str = Field(description="The agent's dynamically chosen role")
    responsibility: str = Field(description="Its specific responsibility")
    instructions: str = Field(description="Instructions for this agent")


class TeamPlan(BaseModel):
    agents: list[AgentSpec]


# ---------- Runtime agent instance ----------

@dataclass
class ChildAgent:
    agent_id: str
    role: str
    responsibility: str
    runnable: object


# ---------- Agent Factory ----------

class AgentFactory:

    def __init__(self):

        # Ensure persistent storage exists.
        initialize_database()

        # Repository handles permanent agent definitions.
        self.repository = AgentRepository()

        # Existing default model used by the planner
        # and temporary team agents.
        self.llm = self._build_model(
            provider=settings.llm_provider
        )

    # ---------- Model creation ----------

    def _build_model(self, provider, model=None):

        if provider == "groq":

            return ChatGroq(
                model=model or settings.groq_model,
                api_key=settings.groq_api_key,
                max_tokens=settings.groq_max_tokens,
            )

        if provider == "anthropic":

            return ChatAnthropic(
                model=model or settings.anthropic_model,
                api_key=settings.anthropic_api_key,
                max_tokens=settings.anthropic_max_tokens,
            )

        raise ValueError(f"Unsupported provider: {provider}")

    # ---------- Agent instructions ----------

    @staticmethod
    def _build_system_prompt(spec: AgentSpec):

        return f"""
        You are a specialist AI agent.

        Role: {spec.role}

        Responsibility:
        {spec.responsibility}

        Instructions:
        {spec.instructions}

        You are a leaf agent.
        You MUST NOT create or spawn other agents.

        You may collaborate with existing team members
        through the A2A communication tools provided to you.
        """

    # ==================================================
    # PERSISTENT AGENT METHODS
    # ==================================================

    def save_agent(
        self,
        spec: AgentSpec,
        name: str | None = None,
        owner_id: str = "local-user",
        config: dict | None = None,
    ):
        """
        Save an agent definition permanently.

        This does not start its runtime or A2A server.
        """

        system_prompt = self._build_system_prompt(spec)

        provider = settings.llm_provider

        model = (
            settings.groq_model
            if provider == "groq"
            else settings.anthropic_model
        )

        agent = self.repository.create_agent(
            name=name or spec.role,
            role=spec.role,
            responsibility=spec.responsibility,
            system_prompt=system_prompt,
            provider=provider,
            model=model,
            config=config or {},
            owner_id=owner_id,
        )

        return agent

    def load_saved_agent(
        self,
        agent_id: str,
        registry: AgentRegistry | None = None,
        owner_id: str = "local-user",
        event_callback=None,
    ):
        """
        Reconstruct a saved agent's runnable using
        its permanent database configuration.
        """

        record = self.repository.get_agent(
            agent_id,
            owner_id,
        )

        if record is None:
            raise ValueError("Saved agent not found")

        if record["status"] != "active":
            raise ValueError("This agent is archived")

        # Recreate the model from the saved configuration.
        model = self._build_model(
            provider=record["provider"],
            model=record["model"],
        )

        # The original ID is reused.
        child = ChildAgent(
            agent_id=record["agent_id"],
            role=record["role"],
            responsibility=record["responsibility"],
            runnable=None,
        )

        tools = []

        # Peer tools are added when a live registry is supplied.
        if registry is not None:

            tools = [
                create_list_peers_tool(child, registry),
                create_peer_tool(
                    child,
                    registry,
                    event_callback,
                ),
            ]

        child.runnable = create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=record["system_prompt"],
        )

        return child

    def load_saved_agents(
        self,
        registry: AgentRegistry | None = None,
        owner_id: str = "local-user",
        event_callback=None,
    ):
        """
        Load all active saved agents into runtime objects.
        """

        records = self.repository.list_agents(owner_id)

        return [
            self.load_saved_agent(
                agent_id=record["agent_id"],
                registry=registry,
                owner_id=owner_id,
                event_callback=event_callback,
            )
            for record in records
        ]

    # ==================================================
    # EXISTING DYNAMIC TEAM METHODS
    # ==================================================

    def plan_team(self, user_request: str) -> TeamPlan:

        planner = self.llm.with_structured_output(TeamPlan)

        plan = planner.invoke(
            f"""
            You are the parent agent's team planner.

            Analyze this user request:
            {user_request}

            Decide dynamically:
            - Whether this task needs multiple specialist agents.
            - What distinct roles they should have.
            - What responsibility each should handle.
            - What instructions each agent needs.
            - The smallest number of agents that can handle it effectively.
            - Create between 1 and {settings.max_child_agents} agents.
            - Do not create unnecessary agents just to reach the maximum.

            Avoid overlapping responsibilities.
            Do not create a fixed or predefined team.
            """
        )

        if not 1 <= len(plan.agents) <= settings.max_child_agents:
            raise ValueError(
                f"Planner returned {len(plan.agents)} agents. "
                f"Expected 1 to {settings.max_child_agents}."
            )

        return plan

    def create_team(
        self,
        user_request: str,
        registry: AgentRegistry,
        event_callback=None,
    ) -> list[ChildAgent]:

        plan = self.plan_team(user_request)

        children = []

        for spec in plan.agents:

            child = ChildAgent(
                agent_id=str(uuid4()),
                role=spec.role,
                responsibility=spec.responsibility,
                runnable=None,
            )

            peer_tools = [
                create_list_peers_tool(child, registry),
                create_peer_tool(child, registry, event_callback),
            ]

            instructions = f"""
            You are a specialist child agent.

            Role: {spec.role}
            Responsibility: {spec.responsibility}

            Instructions:
            {spec.instructions}

            You are a leaf agent.
            You MUST NOT create or spawn other agents.

            You can collaborate with your existing team members
            using the tools provided:

            1. Use list_peers to discover other agents.
            2. Use contact_peer to send a real A2A message.
            3. Contact only agents relevant to your responsibility.
            4. Avoid repeatedly contacting the same peer.
            5. Do not create further agents or delegate to another team.
            6. Use peer responses as supporting information in your work.
            """

            child.runnable = create_deep_agent(
                model=self.llm,
                tools=peer_tools,
                system_prompt=instructions,
            )

            children.append(child)

        return children


if __name__ == "__main__":

    factory = AgentFactory()

    request = (
        "Compare Python and JavaScript for building "
        "modern AI-powered applications."
    )

    registry = AgentRegistry()

    team = factory.create_team(request, registry)

    print(f"\nCreated {len(team)} temporary agents:\n")

    for child in team:
        print("ID:", child.agent_id)
        print("Role:", child.role)
        print("Responsibility:", child.responsibility)
        print("-" * 40)