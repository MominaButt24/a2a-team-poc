import uvicorn

from starlette.applications import Starlette

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    TaskState,
)


class DeepAgentExecutor(AgentExecutor):
    """Connects one Deep Agent to the A2A protocol."""

    def __init__(self, child):
        self.child = child

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:

        task = context.current_task

        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )

        try:
            await updater.update_status(
                state=TaskState.TASK_STATE_WORKING,
                message=new_text_message(
                    f"{self.child.role} is working..."
                ),
            )

            query = get_message_text(context.message)
            print(f"[{self.child.role}] Received request: {query}")
            result = await self.child.runnable.ainvoke({
                "messages": [
                    {"role": "user", "content": query}
                ]
            })
            print(f"[{self.child.role}] Finished processing request")
            messages = result.get("messages", [])
            response = messages[-1].content if messages else str(result)

            if not isinstance(response, str):
                response = str(response)

            await updater.add_artifact(
                parts=[
                    new_text_part(
                        text=response,
                        media_type="text/plain",
                    )
                ]
            )

            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message("Task completed."),
            )

        except Exception as exc:
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(
                    f"Agent execution failed: {exc}"
                ),
            )
            raise

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        raise NotImplementedError("Cancellation is not implemented yet.")


def create_agent_app(child, host: str, port: int):
    """Create an independent A2A application for a child agent."""

    endpoint = f"http://{host}:{port}/"

    skill = AgentSkill(
        id=child.agent_id,
        name=child.role,
        description=child.responsibility,
        tags=["deep-agent", "specialist"],
        examples=[f"Ask this agent about {child.role}."],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    )

    card = AgentCard(
        name=child.role,
        description=child.responsibility,
        version="1.0.0",
        supported_interfaces=[
            AgentInterface(
                url=endpoint,
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            )
        ],
        capabilities=AgentCapabilities(
            streaming=False,
        ),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[skill],
    )

    executor = DeepAgentExecutor(child)

    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )

    routes = [
        *create_agent_card_routes(card),
        *create_jsonrpc_routes(handler, "/"),
    ]

    return Starlette(routes=routes)



def create_child_server(child, host: str, port: int):
    """Create a non-blocking Uvicorn server for a child agent."""

    app = create_agent_app(child, host, port)

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
    )

    return uvicorn.Server(config)


def serve_child(child, host: str, port: int):
    app = create_agent_app(child, host, port)

    print(f"Starting {child.role} at http://{host}:{port}")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    from agents.factory import AgentFactory
    from config.settings import settings

    factory = AgentFactory()

    request = (
        "Compare Python and JavaScript for building "
        "modern AI-powered applications."
    )

    children = factory.create_team(request)

    child = children[0]

    serve_child(
        child,
        settings.a2a_host,
        settings.a2a_port_start,
    )

