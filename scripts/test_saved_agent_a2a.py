import asyncio
from pathlib import Path
from agents.factory import AgentFactory, AgentSpec
from team.runtime import TeamRuntime
from a2a_comms.communication import send_message_to_agent


async def main():
    factory = AgentFactory()
    runtime = TeamRuntime()

    # 1. Create and permanently save a test specialist.
    spec = AgentSpec(
        role="Python Specialist",
        responsibility="Explain Python programming concepts clearly.",
        instructions=(
            "You are a Python programming specialist. "
            "Answer clearly and keep explanations beginner-friendly."
        ),
    )

    saved_agent = factory.save_agent(
        spec=spec,
        name="A2A Integration Test Agent",
    )

    agent_id = saved_agent["agent_id"]

    print("\n1. SAVED AGENT CREATED")
    print("Name:", saved_agent["name"])
    print("Permanent ID:", agent_id)

    try:
        # 2. Reconstruct the saved agent and start its real A2A server.
        print("\n2. STARTING REAL A2A SERVER")

        agent = await runtime.start_saved_agent(
            factory=factory,
            agent_id=agent_id,
        )

        print("Agent status:", agent["status"])
        print("Agent endpoint:", agent["endpoint"])

        # 3. Send a real message through the A2A client.
        print("\n3. SENDING A2A MESSAGE")

        response = await send_message_to_agent(
            agent_url=agent["endpoint"],
            message_text=(
                "Explain what an API is in simple terms. "
                "Use a short example."
            ),
        )

        # 4. Display the actual response.
        print("\n4. AGENT RESPONSE")
        print("=" * 50)
        print(response)
        print("=" * 50)

        if not response.strip():
            raise RuntimeError("The agent returned an empty response.")

        print("\nREAL A2A COMMUNICATION TEST PASSED!")

    finally:
        # 5. Stop the runtime without deleting the saved definition.
        print("\n5. STOPPING A2A SERVER")
        await runtime.stop_team()

        print("Saved agent definition remains in the database.")


if __name__ == "__main__":
    asyncio.run(main())
