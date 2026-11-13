
import asyncio
import html

import gradio as gr

from agents.factory import AgentFactory
from team.runtime import TeamRuntime
from a2a_comms.communication import send_message_to_agent


def render_dashboard(agents, events, phase):
    """Render agents and actual A2A communication events."""

    cards = ""

    for agent in agents:
        role = html.escape(agent["role"])
        responsibility = html.escape(agent["responsibility"])
        agent_id = html.escape(agent["agent_id"][:8])
        status = html.escape(agent["status"])

        cards += f"""
        <div class="agent-card">
            <div class="agent-heading">
                <strong>{role}</strong>
                <span class="status">{status}</span>
            </div>
            <p>{responsibility}</p>
            <small>ID: {agent_id}</small>
        </div>
        """

    connections = ""

    for event in events:
        if event["type"] not in ("message_sent", "message_received"):
            continue

        sender = html.escape(event["from_role"])
        receiver = html.escape(event["to_role"])
        message = html.escape(event.get("message", "")[:350])

        label = (
            "A2A REQUEST"
            if event["type"] == "message_sent"
            else "A2A RESPONSE"
        )

        connections += f"""
        <div class="connection">
            <div class="connection-label">{label}</div>
            <div class="connection-flow">
                <strong>{sender}</strong>
                <span class="arrow">⟶</span>
                <strong>{receiver}</strong>
            </div>
            <div class="message">{message}</div>
        </div>
        """

    if not connections:
        connections = "<p>Waiting for actual A2A peer messages...</p>"

    return f"""
    <style>
        .agent-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
        }}
        .agent-card {{
            border: 1px solid var(--border-color-primary);
            border-radius: 12px;
            padding: 14px;
            background: var(--background-fill-secondary);
        }}
        .agent-heading {{
            display: flex;
            justify-content: space-between;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .status {{
            font-size: 12px;
            padding: 3px 8px;
            border-radius: 8px;
            background: var(--background-fill-primary);
        }}
        .agent-card p, .message {{
            font-size: 13px;
            opacity: .85;
        }}
        .connection {{
            border: 1px solid var(--border-color-primary);
            border-radius: 10px;
            padding: 12px;
            margin: 10px 0;
        }}
        .connection-label {{
            font-size: 11px;
            opacity: .7;
            margin-bottom: 8px;
        }}
        .connection-flow {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .arrow {{
            font-size: 26px;
            animation: moveArrow 1s ease-in-out infinite alternate;
        }}
        @keyframes moveArrow {{
            from {{ transform: translateX(0); }}
            to {{ transform: translateX(9px); }}
        }}
        .message {{
            margin-top: 8px;
            overflow-wrap: anywhere;
        }}
    </style>

    <h3>{html.escape(phase)}</h3>
    <div class="agent-grid">{cards}</div>

    <h3 style="margin-top:24px">A2A Communication Flow</h3>
    {connections}
    """


async def run_team(user_request):
    factory = AgentFactory()
    runtime = TeamRuntime()

    event_queue = asyncio.Queue()
    events = []

    def on_a2a_event(event):
        event_queue.put_nowait(event)

    def dashboard(phase):
        return render_dashboard(
            runtime.registry.get_all_agents(),
            events,
            phase,
        )

    try:
        # 1. Parent dynamically plans and creates the team.
        children = factory.create_team(
            user_request=user_request,
            registry=runtime.registry,
            event_callback=on_a2a_event,
        )

        yield dashboard(
            f"Parent created {len(children)} specialist agents"
        ), "", ""

        # 2. Start each child's A2A server and register its Agent Card.
        await runtime.start_team(children)

        yield dashboard("All child agents are online"), "", ""

        # 3. Execute child tasks concurrently.
        async def execute_child(child):
            agent = runtime.registry.get_agent(child.agent_id)

            runtime.registry.update_status(child.agent_id, "working")
            event_queue.put_nowait({
                "type": "task_started",
                "role": child.role,
            })

            task = f"""
            Original user request:
            {user_request}

            Your assigned responsibility:
            {child.responsibility}

            Complete your specialist analysis.
            Collaborate with relevant peers using list_peers
            and contact_peer when useful.
            """

            try:
                result = await send_message_to_agent(
                    agent_url=agent["endpoint"],
                    message_text=task,
                )

                runtime.registry.update_status(
                    child.agent_id, "completed"
                )
                event_queue.put_nowait({
                    "type": "task_completed",
                    "role": child.role,
                })

                return {
                    "role": child.role,
                    "result": result,
                    "success": True,
                }

            except Exception as exc:
                runtime.registry.update_status(
                    child.agent_id, "failed"
                )
                event_queue.put_nowait({
                    "type": "task_failed",
                    "role": child.role,
                    "message": str(exc),
                })

                return {
                    "role": child.role,
                    "result": str(exc),
                    "success": False,
                }

        tasks = [
            asyncio.create_task(execute_child(child))
            for child in children
        ]

        # 4. Keep refreshing the dashboard while agents work.
        while not all(task.done() for task in tasks):
            try:
                event = await asyncio.wait_for(
                    event_queue.get(), timeout=0.4
                )
                events.append(event)
            except asyncio.TimeoutError:
                pass

            yield dashboard("Child agents are collaborating..."), "", ""

        # Drain events that arrived just before tasks completed.
        while not event_queue.empty():
            events.append(event_queue.get_nowait())

        results = await asyncio.gather(*tasks)

        logs = "\n\n".join(
            f"{item['role']}: "
            f"{'Completed' if item['success'] else 'Failed'}"
            for item in results
        )

        successful = [item for item in results if item["success"]]

        if not successful:
            yield dashboard("All child tasks failed"), logs, (
                "Parent aggregation skipped because no child returned "
                "successful findings. Check the event log and terminal."
            )
            return

        yield dashboard("Parent is aggregating child findings"), logs, ""

        # 5. Parent synthesizes successful child findings.
        evidence = "\n\n".join(
            f"Agent: {item['role']}\nFindings:\n{item['result']}"
            for item in successful
        )

        parent_response = await factory.llm.ainvoke(
            f"""
            You are the parent coordinator.

            Original request:
            {user_request}

            Successful child findings:
            {evidence}

            Synthesize these findings into one coherent response.
            Identify disagreements and missing information.
            Do not invent facts.
            """
        )

        yield (
            dashboard("Team completed — parent aggregation finished"),
            logs,
            parent_response.content,
        )

    except Exception as exc:
        yield dashboard("Team execution failed"), str(exc), str(exc)

    finally:
        await runtime.stop_team()


with gr.Blocks(title="A2A Multi-Agent Team Dashboard") as demo:

    gr.Markdown("# A2A Multi-Agent Team")
    gr.Markdown(
        "Watch the parent create specialist agents, "
        "children collaborate through A2A, and the parent aggregate results."
    )

    request = gr.Textbox(
        label="Your task",
        lines=4,
        value=(
            "Compare Python and JavaScript for building modern "
            "AI-powered applications. Analyze their ecosystems, "
            "AI libraries, performance, deployment, and practical "
            "trade-offs. Collaborate with relevant team members."
        ),
    )

    run_button = gr.Button("Create Team & Run", variant="primary")

    dashboard_view = gr.HTML(
        value="<p>Submit a task to start the agent team.</p>"
    )

    with gr.Accordion("Task Status", open=True):
        task_logs = gr.Textbox(
            label="Child task results",
            lines=6,
            interactive=False,
        )

    with gr.Accordion("Parent Final Response", open=True):
        final_response = gr.Markdown()

    run_button.click(
        fn=run_team,
        inputs=request,
        outputs=[dashboard_view, task_logs, final_response],
    )


if __name__ == "__main__":
    demo.queue().launch(
        server_name="127.0.0.1",
        server_port=7860,
    )
