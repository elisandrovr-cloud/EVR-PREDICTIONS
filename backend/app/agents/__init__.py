"""EVR MLB AI ULTRA — multi-agent intelligence layer.

Eight specialized agents coordinated by a Supervisor. Each agent owns one
domain, runs on the monitoring cycle, and can also answer questions routed to it
by the Supervisor from the chat.

Note: `app/application/agents.py` is a different, older feature — the parlay
"committee" of four betting personas that debate a parlay. This package is the
platform-wide agent system.
"""
from app.agents.base import AgentInsight, AgentReport, BaseAgent  # noqa: F401
from app.agents.supervisor import SUPERVISOR, Supervisor  # noqa: F401

__all__ = ["AgentInsight", "AgentReport", "BaseAgent", "Supervisor", "SUPERVISOR"]
