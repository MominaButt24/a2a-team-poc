
import asyncio

from agents.factory import AgentFactory
from storage.task_repository import TaskRepository
from storage.conversation_repository import ConversationRepository
from a2a_comms.communication import send_message_to_agent


class TaskExecutionEngine:
    """
    Connects persistent tasks, conversations, saved specialists,
    and real A2A communication.
    """

    def __init__(self, factory=None, runtime=None):

        self.factory = factory or AgentFactory()
        self.runtime = runtime

        self.task_repo = TaskRepository()
        self.conversation_repo = ConversationRepository()

    async def execute_task(
        self,
        user_request,
        title=None,
        conversation_id=None,
        owner_id="local-user",
        event_callback=None,
    ):

        if self.runtime is None:
            raise ValueError("TeamRuntime is required.")

        title = title or user_request[:80]

        # -----------------------------------
        # 1. Create or reuse conversation
        # -----------------------------------

        if conversation_id:

            conversation = self.conversation_repo.get_conversation(
                conversation_id,
                owner_id,
            )

            if conversation is None:
                raise ValueError("Conversation not found.")

        else:

            conversation = (
                self.conversation_repo.create_conversation(
                    title=title,
                    owner_id=owner_id,
                )
            )

            conversation_id = conversation["conversation_id"]

        # -----------------------------------
        # 2. Create persistent task
        # -----------------------------------

        task = self.task_repo.create_task(
            title=title,
            description=user_request,
            owner_id=owner_id,
            conversation_id=conversation_id,
        )

        task_id = task["task_id"]

        self.conversation_repo.add_message(
            conversation_id=conversation_id,
            role="user",
            content=user_request,
            metadata={"task_id": task_id},
            owner_id=owner_id,
        )

        try:

            self.task_repo.update_task(
                task_id,
                owner_id=owner_id,
                status="running",
            )

            # -----------------------------------
            # 3. Main Agent plans the specialist team
            # -----------------------------------

            print("\n[MAIN AGENT] Planning specialist team...")

            plan = self.factory.plan_team(user_request)

            print(
                f"[MAIN AGENT] Planned "
                f"{len(plan.agents)} specialist(s)."
            )

            # -----------------------------------
            # 4. Reuse or create permanent agents
            # -----------------------------------

            specialists = self._resolve_specialists(
                plan.agents,
                owner_id,
            )

            print("\n[MAIN AGENT] Selected specialists:")

            for specialist in specialists:
                print(
                    f"- {specialist['name']} "
                    f"({specialist['agent_id']})"
                )

            # -----------------------------------
            # 5. Reconstruct agents not running yet
            # -----------------------------------

            children_to_start = []

            for specialist in specialists:

                agent_id = specialist["agent_id"]

                if agent_id not in self.runtime.servers:

                    child = self.factory.load_saved_agent(
                        agent_id=agent_id,
                        registry=self.runtime.registry,
                        owner_id=owner_id,
                        event_callback=event_callback,
                    )

                    children_to_start.append(child)

            # Start all selected agents.
            if children_to_start:

                print("\n[MAIN AGENT] Starting specialist runtimes...")

                await self.runtime.start_agents(
                    children_to_start
                )

            # -----------------------------------
            # 6. Assign specialists to task
            # -----------------------------------

            for specialist in specialists:

                self.task_repo.assign_agent(
                    task_id,
                    specialist["agent_id"],
                    owner_id,
                )

            # -----------------------------------
            # 7. Delegate through A2A
            # -----------------------------------

            print("\n[MAIN AGENT] Delegating work...")

            results = await asyncio.gather(
                *[
                    self._execute_specialist(
                        task_id=task_id,
                        specialist=specialist,
                        user_request=user_request,
                        owner_id=owner_id,
                    )
                    for specialist in specialists
                ]
            )

            # Save every specialist response in the conversation.
            for result in results:

                if result["response"]:

                    self.conversation_repo.add_message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=result["response"],
                        metadata={
                            "task_id": task_id,
                            "agent_id": result["agent_id"],
                            "agent_role": result["role"],
                        },
                        owner_id=owner_id,
                    )

            failures = [
                result for result in results
                if result["error"]
            ]

            # -----------------------------------
            # 8. Handle specialist failures
            # -----------------------------------

            if failures:

                error_message = "\n".join(
                    f"{item['role']}: {item['error']}"
                    for item in failures
                )

                self.task_repo.update_task(
                    task_id,
                    owner_id=owner_id,
                    status="failed",
                    error=error_message,
                )

                return self._build_response(
                    task_id,
                    conversation_id,
                    owner_id,
                    results,
                    error=error_message,
                )

            # -----------------------------------
            # 9. Main Agent synthesizes results
            # -----------------------------------

            print("\n[MAIN AGENT] Synthesizing specialist findings...")

            evidence = "\n\n".join(
                f"Specialist: {item['role']}\n"
                f"Findings:\n{item['response']}"
                for item in results
            )

            parent_response = await self.factory.llm.ainvoke(
                f"""
                You are the Main Agent coordinating a team
                of specialist agents.

                Original user request:
                {user_request}

                Specialist findings:
                {evidence}

                Produce one coherent and useful final response.

                Do not invent missing information.
                Identify disagreements or limitations where relevant.
                """
            )

            final_result = self._extract_content(
                parent_response
            )

            # -----------------------------------
            # 10. Persist final response
            # -----------------------------------

            self.conversation_repo.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=final_result,
                metadata={
                    "task_id": task_id,
                    "type": "final_result",
                },
                owner_id=owner_id,
            )

            self.task_repo.update_task(
                task_id,
                owner_id=owner_id,
                status="completed",
                result=final_result,
            )

            print("\n[MAIN AGENT] Task completed successfully.")

            return self._build_response(
                task_id,
                conversation_id,
                owner_id,
                results,
                result=final_result,
            )

        except Exception as exc:

            error_message = str(exc)

            print(f"\n[TASK ERROR] {error_message}")

            current_task = self.task_repo.get_task(
                task_id,
                owner_id,
            )

            if current_task and current_task["status"] not in {
                "completed",
                "failed",
                "cancelled",
            }:

                self.task_repo.update_task(
                    task_id,
                    owner_id=owner_id,
                    status="failed",
                    error=error_message,
                )

            return self._build_response(
                task_id,
                conversation_id,
                owner_id,
                [],
                error=error_message,
            )

    # ==========================================
    # SPECIALIST RESOLUTION
    # ==========================================

    def _resolve_specialists(self, specs, owner_id):

        saved_agents = self.factory.repository.list_agents(
            owner_id
        )

        # Reuse an existing active agent with the same role.
        agents_by_role = {
            agent["role"].strip().casefold(): agent
            for agent in saved_agents
        }

        selected = []

        for spec in specs:

            role_key = spec.role.strip().casefold()

            existing = agents_by_role.get(role_key)

            if existing:

                print(f"[REUSE] Existing agent: {spec.role}")

                selected.append(existing)

            else:

                print(f"[CREATE] New permanent agent: {spec.role}")

                saved = self.factory.save_agent(
                    spec=spec,
                    name=spec.role,
                    owner_id=owner_id,
                )

                agents_by_role[role_key] = saved
                selected.append(saved)

        return selected

    # ==========================================
    # SPECIALIST A2A EXECUTION
    # ==========================================

    async def _execute_specialist(
        self,
        task_id,
        specialist,
        user_request,
        owner_id,
    ):

        agent_id = specialist["agent_id"]
        role = specialist["role"]

        self.task_repo.update_agent_status(
            task_id,
            agent_id,
            "working",
            owner_id,
        )

        agent = self.runtime.registry.get_agent(agent_id)

        if agent is None:
            raise RuntimeError(
                f"Agent {role} is not registered."
            )

        delegated_request = f"""
        Original user request:
        {user_request}

        Your responsibility:
        {specialist['responsibility']}

        Complete your specialist work.

        You may collaborate with relevant registered peers
        using your A2A communication tools.

        Return your findings clearly and accurately.
        """

        try:

            response = await send_message_to_agent(
                agent_url=agent["endpoint"],
                message_text=delegated_request,
            )

            self.task_repo.update_agent_status(
                task_id,
                agent_id,
                "completed",
                owner_id,
            )

            return {
                "agent_id": agent_id,
                "role": role,
                "response": response,
                "error": None,
            }

        except Exception as exc:

            self.task_repo.update_agent_status(
                task_id,
                agent_id,
                "failed",
                owner_id,
            )

            return {
                "agent_id": agent_id,
                "role": role,
                "response": None,
                "error": str(exc),
            }

    # ==========================================
    # RESPONSE HELPERS
    # ==========================================

    def _build_response(
        self,
        task_id,
        conversation_id,
        owner_id,
        specialists,
        result=None,
        error=None,
    ):

        return {
            "task": self.task_repo.get_task(
                task_id,
                owner_id,
            ),
            "conversation": self.conversation_repo.get_conversation(
                conversation_id,
                owner_id,
            ),
            "specialists": specialists,
            "result": result,
            "error": error,
        }

    @staticmethod
    def _extract_content(response):

        content = (
            response.content
            if hasattr(response, "content")
            else str(response)
        )

        if isinstance(content, str):
            return content

        if isinstance(content, list):

            return "\n".join(
                item.get("text", str(item))
                if isinstance(item, dict)
                else str(item)
                for item in content
            )

        return str(content)
