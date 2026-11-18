
import asyncio

from agents.factory import AgentFactory
from team.runtime import TeamRuntime
from team.task_execution_engine import TaskExecutionEngine


def log_event(event):

    if event["type"] == "message_sent":

        print(
            f"\n[A2A] {event['from_role']} "
            f"-> {event['to_role']}"
        )

    elif event["type"] == "message_received":

        print(
            f"\n[A2A RESPONSE] {event['from_role']} "
            f"-> {event['to_role']}"
        )


async def main():

    factory = AgentFactory()
    runtime = TeamRuntime()

    engine = TaskExecutionEngine(
        factory=factory,
        runtime=runtime,
    )

    user_request = (
        "Research the advantages and disadvantages of "
        "using Python for AI application development. "
        "Explain its ecosystem, important libraries, "
        "performance, and deployment considerations."
    )

    try:

        print("\n========== TASK EXECUTION ==========")

        response = await engine.execute_task(
            user_request=user_request,
            title="Python AI Development Research",
            event_callback=log_event,
        )

        print("\n========== TASK RESULT ==========")

        print("Task ID:", response["task"]["task_id"])
        print("Status:", response["task"]["status"])

        print("\n========== FINAL RESPONSE ==========")

        if response["result"]:
            print(response["result"])

        if response["error"]:
            print("\nExecution error:", response["error"])

        print("\n========== SPECIALIST RESULTS ==========")

        for specialist in response["specialists"]:

            print("\nRole:", specialist["role"])
            print("Agent ID:", specialist["agent_id"])
            print("Error:", specialist["error"])

    finally:

        await runtime.stop_team()


if __name__ == "__main__":
    asyncio.run(main())
