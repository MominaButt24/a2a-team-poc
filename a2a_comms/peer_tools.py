from langchain_core.tools import tool

from a2a_comms.communication import send_message_to_agent


def create_peer_tool(child, registry, event_callback=None):
    """Create an A2A peer communication tool for one child."""

    async def emit_event(event):
        if event_callback:
            result = event_callback(event)
            if hasattr(result, "__await__"):
                await result

    @tool
    async def contact_peer(peer_id: str, message: str) -> str:
        """Contact another registered child agent through A2A.

        Args:
            peer_id: The ID of the peer agent to contact.
            message: The specific question or task to send.
        """

        peer = registry.get_agent(peer_id)

        if peer is None:
            raise ValueError(f"Unknown peer agent ID: {peer_id}")

        if peer_id == child.agent_id:
            raise ValueError("An agent cannot contact itself.")

        # if peer["status"] != "online":
        #     raise RuntimeError(
        #         f"Peer {peer['role']} is not online."
        #     )

        await emit_event({
            "type": "message_sent",
            "from": child.agent_id,
            "from_role": child.role,
            "to": peer_id,
            "to_role": peer["role"],
            "message": message,
        })

        response = await send_message_to_agent(
            agent_url=peer["endpoint"],
            message_text=message,
        )

        await emit_event({
            "type": "message_received",
            "from": peer_id,
            "from_role": peer["role"],
            "to": child.agent_id,
            "to_role": child.role,
            "message": response,
        })

        return response

    return contact_peer


from langchain_core.tools import tool


def create_list_peers_tool(child, registry):
    """Allow a child to discover its registered peers."""

    @tool
    def list_peers() -> str:
        """List the other available child agents and their IDs."""

        peers = registry.get_peers(child.agent_id)

        if not peers:
            return "No other agents are registered."

        return "\n".join(
            f"Agent ID: {peer['agent_id']}\n"
            f"Role: {peer['role']}\n"
            f"Responsibility: {peer['responsibility']}\n"
            f"Status: {peer['status']}"
            for peer in peers
        )

    return list_peers

