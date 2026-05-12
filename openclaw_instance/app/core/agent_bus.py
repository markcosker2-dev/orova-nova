"""
OROVA Nova — Agent-to-Agent Message Bus
Enables agents to delegate tasks to each other with structured data.
"""
import os
import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from queue import Queue

logger = logging.getLogger(__name__)


class AgentMessage:
    """Structured message between agents."""

    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        task: str,
        data: Dict[str, Any] = None,
        priority: str = "normal"
    ):
        self.id = f"msg_{int(time.time()*1000)}"
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.task = task
        self.data = data or {}
        self.priority = priority
        self.created_at = datetime.utcnow().isoformat()
        self.status = "pending"
        self.result = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "from": self.from_agent,
            "to": self.to_agent,
            "task": self.task,
            "data": self.data,
            "priority": self.priority,
            "created_at": self.created_at,
            "status": self.status,
            "result": self.result
        }


class AgentBus:
    """
    Message bus for inter-agent communication.
    Agents delegate tasks to each other via structured messages.
    """

    # Agent capabilities — what each agent can handle
    CAPABILITIES = {
        "HAWK": ["find_leads", "research_lead", "enrich_contact", "score_lead"],
        "SAGE": ["monitor_ads", "adjust_budget", "pause_campaign", "generate_ad_copy"],
        "Quill": ["write_email", "write_ad_copy", "write_content", "create_sequence"],
        "Oracle": ["analyze_pipeline", "generate_report", "calculate_roi", "compare_competitors"],
        "Nova": ["approve_action", "route_task", "escalate", "onboard_client"],
        "Viper": ["stealth_search", "bulk_scrape", "extract_data"],
        "Closer": ["generate_proposal", "send_proposal", "follow_up"],
        "Sentinel": ["check_health", "monitor_system", "alert"],
        "NightShift": ["handle_incoming_lead", "handle_email_reply", "handle_missed_call", "auto_qualify"],
        "Revenue": ["add_deal", "update_stage", "get_forecast", "pipeline_report", "monthly_report"]
    }

    def __init__(self):
        self.inbox: Dict[str, List[AgentMessage]] = {agent: [] for agent in self.CAPABILITIES}
        self.completed: List[AgentMessage] = []

    def send(self, message: AgentMessage) -> bool:
        """Send a message to an agent's inbox."""
        if message.to_agent not in self.inbox:
            logger.error(f"[BUS] Unknown agent: {message.to_agent}")
            return False

        self.inbox[message.to_agent].append(message)

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        self.inbox[message.to_agent].sort(
            key=lambda m: priority_order.get(m.priority, 2)
        )

        logger.info(f"[BUS] {message.from_agent} -> {message.to_agent}: {message.task}")
        return True

    def delegate(
        self,
        from_agent: str,
        to_agent: str,
        task: str,
        data: Dict = None,
        priority: str = "normal"
    ) -> AgentMessage:
        """Convenience method to create and send a message."""
        msg = AgentMessage(from_agent, to_agent, task, data, priority)
        self.send(msg)
        return msg

    def get_next(self, agent: str) -> Optional[AgentMessage]:
        """Get the next pending message for an agent."""
        if agent not in self.inbox:
            return None

        for msg in self.inbox[agent]:
            if msg.status == "pending":
                return msg
        return None

    def complete(self, message_id: str, result: Any):
        """Mark a message as completed with result."""
        for agent_msgs in self.inbox.values():
            for msg in agent_msgs:
                if msg.id == message_id:
                    msg.status = "completed"
                    msg.result = result
                    self.completed.append(msg)
                    agent_msgs.remove(msg)
                    logger.info(f"[BUS] Completed: {message_id}")
                    return True
        return False

    def get_inbox_summary(self) -> Dict:
        """Get inbox size per agent."""
        return {
            agent: len([m for m in msgs if m.status == "pending"])
            for agent, msgs in self.inbox.items()
        }

    def can_handle(self, agent: str, task: str) -> bool:
        """Check if an agent can handle a specific task."""
        return task in self.CAPABILITIES.get(agent, [])

    def find_agent_for_task(self, task: str) -> Optional[str]:
        """Find which agent can handle a task."""
        for agent, capabilities in self.CAPABILITIES.items():
            if task in capabilities:
                return agent
        return None


# Global instance
agent_bus = AgentBus()
