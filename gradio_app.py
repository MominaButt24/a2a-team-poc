
import asyncio
import gradio as gr

from agents.factory import AgentFactory
from team.runtime import TeamRuntime
from team.task_execution_engine import TaskExecutionEngine
from a2a_comms.communication import send_message_to_agent

from storage.agent_repository import AgentRepository
from storage.conversation_repository import ConversationRepository


# --------------------------------------------------
# SHARED APPLICATION SERVICES
# --------------------------------------------------

OWNER_ID = "local-user"

factory = AgentFactory()
runtime = TeamRuntime()
engine = TaskExecutionEngine(factory=factory, runtime=runtime)

agent_repo = AgentRepository()
conversation_repo = ConversationRepository()


# --------------------------------------------------
# DATABASE HELPERS
# --------------------------------------------------

def get_saved_agents():
    return agent_repo.list_agents(owner_id=OWNER_ID)


def get_chat_history(conversation_id):
    if not conversation_id:
        return []

    messages = conversation_repo.get_messages(
        conversation_id=conversation_id,
        owner_id=OWNER_ID
    )

    history = []

    for message in messages:
        role = message["role"]

        if role in ("user", "assistant"):
            history.append({
                "role": role,
                "content": message["content"]
            })

    return history

def get_or_create_agent_conversation(agent_id):
    conversations = conversation_repo.list_conversations(
        owner_id=OWNER_ID,
        agent_id=agent_id
    )

    if conversations:
        return conversations[0]

    return conversation_repo.create_conversation(
        title="Agent Conversation",
        agent_id=agent_id,
        owner_id=OWNER_ID
    )


# --------------------------------------------------
# OPEN A SAVED SPECIALIST
# --------------------------------------------------

async def open_agent(agent_id):
    try:
        agent = agent_repo.get_agent(
            agent_id=agent_id,
            owner_id=OWNER_ID
        )

        if not agent:
            return (
                None, [], None,
                "Agent not found."
            )

        # Start the A2A server only when needed.
        if agent_id not in runtime.servers:
            await runtime.start_saved_agent(
                factory=factory,
                agent_id=agent_id,
                owner_id=OWNER_ID
            )

        conversation = get_or_create_agent_conversation(agent_id)

        history = get_chat_history(conversation["conversation_id"])

        details = (
            f"### {agent['name']}\n"
            f"**Role:** {agent['role']}\n\n"
            f"**Responsibility:** {agent['responsibility']}\n\n"
            f"**Runtime:** Online"
        )

        return (
            agent_id,
            history,
            conversation["conversation_id"],
            details
        )

    except Exception as exc:
        return (
            agent_id,
            [],
            None,
            f"Could not open agent: {exc}"
        )


# --------------------------------------------------
# DIRECT SPECIALIST CHAT
# --------------------------------------------------

async def send_agent_message(message, agent_id, conversation_id):
    if not message.strip():
        return gr.update(), "", "Please enter a message."

    if not agent_id or not conversation_id:
        return gr.update(), message, "Open an agent first."

    try:
        conversation_repo.add_message(
            conversation_id=conversation_id,
            role="user",
            content=message,
            owner_id=OWNER_ID
        )

        agent = runtime.registry.get_agent(agent_id)

        if not agent:
            raise RuntimeError("Agent is not registered in the runtime.")

        response = await send_message_to_agent(
            agent_url=agent["endpoint"],
            message_text=message
        )

        conversation_repo.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response,
            owner_id=OWNER_ID
        )

        history = get_chat_history(conversation_id)

        return history, "", "Message completed."

    except Exception as exc:
        return (
            get_chat_history(conversation_id),
            "",
            f"Error: {exc}"
        )


# --------------------------------------------------
# MAIN AGENT CHAT
# --------------------------------------------------

async def send_main_message(message, history, conversation_id):
    if not message.strip():
        return history, conversation_id, "", "Please enter a task."

    try:
        result = await engine.execute_task(
            user_request=message,
            conversation_id=conversation_id,
            owner_id=OWNER_ID
        )

        new_conversation = result.get("conversation")

        if new_conversation:
            conversation_id = new_conversation["conversation_id"]

        history = get_chat_history(conversation_id)

        if result.get("error"):
            status = f"Task failed: {result['error']}"
        else:
            status = f"Task {result.get('task', {}).get('status', 'completed')}."

        return history, conversation_id, "", status

    except Exception as exc:
        return history, conversation_id, "", f"Error: {exc}"


# --------------------------------------------------
# GRADIO WORKSPACE
# --------------------------------------------------

saved_agents = get_saved_agents()

with gr.Blocks(title="Grokbot Agent Workspace") as demo:

    gr.Markdown(
        "# Grokbot Agent Workspace\n"
        "Your persistent AI agent team."
    )

    with gr.Tabs():

        # ==========================================
        # MAIN CHAT
        # ==========================================

        with gr.Tab("Main Chat"):

            gr.Markdown(
                "Talk to the Main Agent. It will plan your task "
                "and delegate work to specialist agents."
            )

            main_chat = gr.Chatbot(
                label="Main Agent Conversation",
                height=450
            )

            main_message = gr.Textbox(
                label="Your task",
                placeholder="e.g. Research a topic and prepare an email...",
                lines=2
            )

            main_send = gr.Button("Send", variant="primary")

            main_status = gr.Markdown()

            main_conversation_id = gr.State(value=None)

        # ==========================================
        # MY AGENTS
        # ==========================================

        with gr.Tab("My Agents"):

            gr.Markdown("## Your Saved Specialist Agents")

            with gr.Row():

                # LEFT: AGENT CARDS

                with gr.Column(scale=1):

                    gr.Markdown("### My Agents")

                    agent_buttons = []

                    if saved_agents:

                        for agent in saved_agents:

                            with gr.Group():

                                gr.Markdown(
                                    f"**{agent['name']}**\n\n"
                                    f"Role: {agent['role']}\n\n"
                                    f"{agent['responsibility']}"
                                )

                                open_button = gr.Button(
                                    "Open Chat",
                                    variant="secondary"
                                )

                                agent_buttons.append(
                                    (open_button, agent["agent_id"])
                                )

                    else:
                        gr.Markdown(
                            "No saved agents found yet. "
                            "Run a task through Main Chat to create specialists."
                        )

                # RIGHT: DIRECT AGENT CHAT

                with gr.Column(scale=2):

                    agent_details = gr.Markdown(
                        "Select an agent card to open its conversation."
                    )

                    agent_chat = gr.Chatbot(
                        label="Specialist Conversation",
                        height=400
                    )

                    agent_message = gr.Textbox(
                        label="Message",
                        placeholder="Ask this specialist something...",
                        lines=2
                    )

                    agent_send = gr.Button(
                        "Send Message",
                        variant="primary"
                    )

                    agent_status = gr.Markdown()

                    selected_agent_id = gr.State(value=None)
                    agent_conversation_id = gr.State(value=None)

    # ==========================================
    # EVENT CONNECTIONS
    # ==========================================

    main_send.click(
        fn=send_main_message,
        inputs=[
            main_message,
            main_chat,
            main_conversation_id
        ],
        outputs=[
            main_chat,
            main_conversation_id,
            main_message,
            main_status
        ]
    )

    main_message.submit(
        fn=send_main_message,
        inputs=[
            main_message,
            main_chat,
            main_conversation_id
        ],
        outputs=[
            main_chat,
            main_conversation_id,
            main_message,
            main_status
        ]
    )

    # Connect each saved-agent card to the same chat panel.
    # for button, agent_id in agent_buttons:

    #     button.click(
    #         fn=lambda aid=agent_id: open_agent(aid),
    #         inputs=[],
    #         outputs=[
    #             selected_agent_id,
    #             agent_chat,
    #             agent_conversation_id,
    #             agent_details
    #         ]
    #     )
    for button, agent_id in agent_buttons:

        agent_id_state = gr.State(value=agent_id)

        button.click(
            fn=open_agent,
            inputs=[agent_id_state],
            outputs=[
                selected_agent_id,
                agent_chat,
                agent_conversation_id,
                agent_details
            ]
        )

    agent_send.click(
        fn=send_agent_message,
        inputs=[
            agent_message,
            selected_agent_id,
            agent_conversation_id
        ],
        outputs=[
            agent_chat,
            agent_message,
            agent_status
        ]
    )

    agent_message.submit(
        fn=send_agent_message,
        inputs=[
            agent_message,
            selected_agent_id,
            agent_conversation_id
        ],
        outputs=[
            agent_chat,
            agent_message,
            agent_status
        ]
    )


# --------------------------------------------------
# LAUNCH
# --------------------------------------------------

if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860
    )