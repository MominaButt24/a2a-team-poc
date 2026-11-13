import asyncio

from agents.factory import AgentFactory
from a2a_comms.communication import send_message_to_agent
from team.runtime import TeamRuntime


def log_communication(event):
    """Display real peer communication events in the terminal."""

    if event["type"] == "message_sent":
        print(
            f"\n[A2A MESSAGE] "
            f"{event['from_role']} → {event['to_role']}"
        )
        print(f"Message: {event['message']}")

    elif event["type"] == "message_received":
        print(
            f"\n[A2A RESPONSE] "
            f"{event['from_role']} → {event['to_role']}"
        )
        print(f"Response: {event['message']}")


async def main():
    factory = AgentFactory()
    runtime = TeamRuntime()

    user_request = (
        "Compare Python and JavaScript for building modern "
        "AI-powered applications. Analyze their ecosystems, "
        "AI libraries, performance, deployment, and practical "
        "trade-offs. Collaborate with relevant team members "
        "to validate your findings."
    )

    try:
        # 1. Dynamically plan and create the team.
        children = factory.create_team(
            user_request=user_request,
            registry=runtime.registry,
            event_callback=log_communication,
        )

        print(f"\nCreated {len(children)} child agents.")

        # 2. Start and register every child server.
        agents = await runtime.start_team(children)

        print("\n===== TEAM ONLINE =====")

        for agent in agents:
            print(
                f"{agent['role']} | "
                f"{agent['endpoint']} | "
                f"{agent['status']}"
            )

        # 3. Send tasks to all children concurrently.
        async def execute_child(child):
            agent = runtime.registry.get_agent(child.agent_id)

            task = f"""
            Original user request:
            {user_request}

            Your assigned responsibility:
            {child.responsibility}

            Complete your specialist analysis.
            Use list_peers and contact_peer when collaboration
            would improve your findings.
            Return your findings clearly.
            """

            runtime.registry.update_status(
                child.agent_id, "working"
            )

            try:
                result = await send_message_to_agent(
                    agent_url=agent["endpoint"],
                    message_text=task,
                )

                runtime.registry.update_status(
                    child.agent_id, "completed"
                )

                return {
                    "role": child.role,
                    "result": result,
                }

            except Exception as exc:
                runtime.registry.update_status(
                    child.agent_id, "failed"
                )

                return {
                    "role": child.role,
                    "result": f"Execution failed: {exc}",
                }

        results = await asyncio.gather(
            *(execute_child(child) for child in children)
        )

        # 4. Parent aggregates the child results.
        print("\n===== PARENT AGGREGATION =====")

        evidence = "\n\n".join(
            f"Agent: {item['role']}\n"
            f"Findings:\n{item['result']}"
            for item in results
        )

        parent_response = await factory.llm.ainvoke(
            f"""
            You are the parent coordinator.

            Original user request:
            {user_request}

            Findings from your child agents:
            {evidence}

            Synthesize their findings into one coherent,
            accurate response. Identify disagreements or
            missing information rather than inventing facts.
            """
        )

        print("\n===== FINAL PARENT RESPONSE =====")
        print(parent_response.content)

    finally:
        await runtime.stop_team()


if __name__ == "__main__":
    asyncio.run(main())
