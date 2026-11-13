class AgentRegistry:
    """In-memory directory of dynamically created A2A agents."""

    def __init__(self):
        self.agents = {}

    def register(self, child, endpoint):
        self.agents[child.agent_id] = {
            "agent_id": child.agent_id,
            "role": child.role,
            "responsibility": child.responsibility,
            "endpoint": endpoint,
            "status": "starting",
            "agent_card": None,
        }

    def update_status(self, agent_id, status):
        if agent_id in self.agents:
            self.agents[agent_id]["status"] = status

    def update_agent_card(self, agent_id, card):
        if agent_id in self.agents:
            self.agents[agent_id]["agent_card"] = card

    def get_agent(self, agent_id):
        return self.agents.get(agent_id)

    def get_all_agents(self):
        return list(self.agents.values())

    def get_peers(self, agent_id):
        """Return all registered agents except the requesting agent."""
        return [
            agent
            for key, agent in self.agents.items()
            if key != agent_id
        ]
