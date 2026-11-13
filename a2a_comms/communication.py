import asyncio
import httpx
from a2a.client import create_client, ClientConfig
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest


async def send_message_to_agent(
    agent_url: str,
    message_text: str,
) -> str:
    """Send a message to another agent through A2A."""

    # client = await create_client(
    #     agent=agent_url,
    #     client_config=ClientConfig(streaming=False),
    # )

    httpx_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=10.0,
            read=120.0,
            write=30.0,
            pool=10.0,
        )
    )

    client = await create_client(
        agent=agent_url,
        client_config=ClientConfig(
            streaming=False,
            httpx_client=httpx_client,
        ),
    )

    try:
        message = new_text_message(
            message_text,
            role=Role.ROLE_USER,
        )

        request = SendMessageRequest(message=message)

        response_text = []

        async for response in client.send_message(request):

            if response.HasField("task"):
                task = response.task

                print(f"Task status: {task.status.state}")

                for artifact in task.artifacts:
                    for part in artifact.parts:
                        if part.text:
                            response_text.append(part.text)

            elif response.HasField("message"):
                for part in response.message.parts:
                    if part.text:
                        response_text.append(part.text)

        return "\n".join(response_text)

    finally:
        await client.close()
        await httpx_client.aclose()


if __name__ == "__main__":
    async def main():
        result = await send_message_to_agent(
            agent_url="http://127.0.0.1:9001/",
            message_text=(
                "Explain the advantages of Python "
                "for developing AI applications."
            ),
        )

        print("\n===== AGENT RESPONSE =====")
        print(result)

    asyncio.run(main())
