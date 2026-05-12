"""
OROVA Subagent System — Hermes Parallel Execution
Spawns isolated subagents for parallel workstreams with RPC communication.
"""
import asyncio
import logging
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SubAgentState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskResult:
    agent_name: str
    status: SubAgentState
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0
    tool_calls: int = 0


class SubAgent:
    """Isolated subagent with own context/memory and RPC tool access."""

    def __init__(
        self,
        name: str,
        instructions: str,
        workdir: Path = None,
        tool_registry: Dict[str, Callable] = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.instructions = instructions
        self.workdir = workdir or Path.cwd()
        self.tool_registry = tool_registry or {}
        self.context: List[Dict] = []
        self.state = SubAgentState.IDLE
        self._turn_count = 0
        self._tool_call_count = 0
        self._created_at = datetime.now()
        self._task_history: List[Dict] = []

    async def run(self, task: str) -> Dict:
        """Run a task in this subagent with isolated context."""
        start_time = asyncio.get_event_loop().time()
        self.state = SubAgentState.RUNNING
        self._turn_count += 1

        context_entry = {
            "turn": self._turn_count,
            "task": task,
            "timestamp": datetime.now().isoformat(),
            "messages": [],
        }

        try:
            context_entry["messages"].append({
                "role": "system",
                "content": self.instructions,
            })
            context_entry["messages"].append({
                "role": "user",
                "content": task,
            })

            result = await self._execute_task(task, context_entry)

            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            context_entry["result"] = result
            context_entry["duration_ms"] = duration_ms
            self._task_history.append(context_entry)
            self.context.append(context_entry)

            self.state = SubAgentState.COMPLETED
            return {
                "status": "success",
                "agent_id": self.id,
                "agent_name": self.name,
                "result": result,
                "turns": self._turn_count,
                "tool_calls": self._tool_call_count,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            self.state = SubAgentState.FAILED
            logger.error(f"SubAgent {self.name} failed: {e}")

            context_entry["error"] = str(e)
            self._task_history.append(context_entry)

            return {
                "status": "error",
                "agent_id": self.id,
                "agent_name": self.name,
                "error": str(e),
                "duration_ms": duration_ms,
            }

    async def _execute_task(self, task: str, context: Dict) -> Any:
        """Execute the task - override this for custom execution logic."""
        await asyncio.sleep(0.01)
        return f"Processed: {task[:50]}..."

    def call_tool(self, tool_name: str, **kwargs) -> Any:
        """RPC call to main agent tools — collapses multi-step to single turn."""
        if tool_name not in self.tool_registry:
            raise ValueError(f"Tool '{tool_name}' not registered")

        self._tool_call_count += 1
        tool_func = self.tool_registry[tool_name]

        logger.debug(f"SubAgent {self.name} calling tool: {tool_name}")
        result = tool_func(**kwargs)

        if asyncio.iscoroutine(result):
            # [FIX-3] Never call asyncio.run() inside a running loop
            try:
                loop = asyncio.get_running_loop()
                # We're inside a running loop — schedule as a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return loop.run_in_executor(pool, asyncio.run, result).__await__()
            except RuntimeError:
                # No running loop — safe to use asyncio.run
                return asyncio.run(result)
        return result

    def register_tool(self, name: str, func: Callable) -> None:
        """Register a tool for RPC calls."""
        self.tool_registry[name] = func

    def get_context_summary(self) -> Dict:
        """Get a summary of the agent's context/history."""
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state.value,
            "turn_count": self._turn_count,
            "tool_calls": self._tool_call_count,
            "workdir": str(self.workdir),
            "created_at": self._created_at.isoformat(),
            "tasks_completed": len(self._task_history),
        }

    def clear_context(self) -> None:
        """Clear the agent's message context."""
        self.context.clear()
        self._task_history.clear()

    def __repr__(self) -> str:
        return f"SubAgent(id={self.id}, name={self.name}, state={self.state.value})"


class SubAgentPool:
    """Pool for managing multiple subagents with parallel execution."""

    def __init__(self, max_agents: int = 5, task_timeout: int = 60):
        self.max_agents = max_agents
        self.task_timeout = task_timeout  # [FIX-8] Timeout per task in seconds
        self.active: List[SubAgent] = []
        self.completed: deque = deque(maxlen=50)  # [FIX-9] Bounded, auto-prunes oldest
        self.failed: deque = deque(maxlen=50)  # [FIX-9] Bounded, auto-prunes oldest
        self._tool_registry: Dict[str, Callable] = {}
        self._id_counter = 0

    def register_tool(self, name: str, func: Callable) -> None:
        """Register a tool available to all subagents via RPC."""
        self._tool_registry[name] = func
        for agent in self.active:
            agent.register_tool(name, func)

    async def spawn(
        self,
        name: str = None,
        instructions: str = "",
        workdir: Path = None,
    ) -> SubAgent:
        """Spawn a new subagent if under max capacity."""
        if len(self.active) >= self.max_agents:
            raise RuntimeError(
                f"Agent pool full ({self.max_agents}). Wait for running agents to complete."
            )

        self._id_counter += 1
        agent_name = name or f"subagent-{self._id_counter}"

        agent = SubAgent(
            name=agent_name,
            instructions=instructions,
            workdir=workdir,
            tool_registry=dict(self._tool_registry),
        )

        self.active.append(agent)
        logger.info(f"Spawned {agent_name} (total active: {len(self.active)})")
        return agent

    async def run_parallel(self, tasks: List[Dict]) -> List[TaskResult]:
        """Run multiple tasks in parallel across available agents."""
        if not tasks:
            return []

        results = []
        semaphore = asyncio.Semaphore(self.max_agents)

        async def run_task_with_limit(task: Dict) -> TaskResult:
            async with semaphore:
                agent_name = task.get("agent_name", f"task-{len(results)}")
                instructions = task.get("instructions", "")
                task_content = task.get("task", "")

                start = asyncio.get_event_loop().time()

                try:
                    agent = await self.spawn(name=agent_name, instructions=instructions)
                    # [FIX-8] Wrap with timeout to prevent hangs
                    result = await asyncio.wait_for(
                        agent.run(task_content),
                        timeout=self.task_timeout
                    )
                    duration = (asyncio.get_event_loop().time() - start) * 1000

                    results.append(TaskResult(
                        agent_name=agent_name,
                        status=SubAgentState.COMPLETED if result.get("status") == "success" else SubAgentState.FAILED,
                        result=result.get("result"),
                        error=result.get("error"),
                        duration_ms=duration,
                        tool_calls=agent._tool_call_count,
                    ))
                except Exception as e:
                    duration = (asyncio.get_event_loop().time() - start) * 1000
                    results.append(TaskResult(
                        agent_name=agent_name,
                        status=SubAgentState.FAILED,
                        error=str(e),
                        duration_ms=duration,
                    ))

        await asyncio.gather(*[run_task_with_limit(t) for t in tasks])
        return results

    def delegate_to_subagent(
        self,
        task: str,
        complexity_threshold: int = 3,
    ) -> SubAgent:
        """Auto-delegate complex tasks to a new subagent."""
        estimated_complexity = self._estimate_complexity(task)

        if estimated_complexity >= complexity_threshold:
            agent_name = f"delegate-{self._id_counter + 1}"
            instructions = f"Handle this complex task: {task[:200]}"
            # [FIX-3] Use loop-aware spawn instead of asyncio.run()
            try:
                loop = asyncio.get_running_loop()
                future = asyncio.ensure_future(self.spawn(name=agent_name, instructions=instructions))
                return future  # Caller must await
            except RuntimeError:
                return asyncio.run(self.spawn(name=agent_name, instructions=instructions))

        return None

    def _estimate_complexity(self, task: str) -> int:
        """Estimate task complexity based on keywords and structure."""
        complexity = 1
        complex_keywords = [
            "analyze", "compare", "research", "generate", "create",
            "multiple", "all", "entire", "comprehensive", "pipeline",
        ]
        for kw in complex_keywords:
            if kw.lower() in task.lower():
                complexity += 1
        return complexity

    def cleanup_completed(self) -> int:
        """Move completed agents to archive and return count."""
        completed = [a for a in self.active if a.state == SubAgentState.COMPLETED]
        failed = [a for a in self.active if a.state == SubAgentState.FAILED]
        self.completed.extend(completed)
        self.failed.extend(failed)
        self.active = [a for a in self.active if a.state == SubAgentState.RUNNING]
        return len(completed) + len(failed)

    def get_pool_status(self) -> Dict:
        """Get current pool status."""
        return {
            "active": len(self.active),
            "max": self.max_agents,
            "available_slots": self.max_agents - len(self.active),
            "completed_total": len(self.completed),
            "failed_total": len(self.failed),
            "registered_tools": list(self._tool_registry.keys()),
            "agents": [a.get_context_summary() for a in self.active],
        }

    def shutdown(self) -> None:
        """Shutdown the pool and cleanup."""
        for agent in self.active:
            agent.state = SubAgentState.IDLE
        self.active.clear()
        logger.info("SubAgentPool shutdown complete")


class LLMSubAgent(SubAgent):
    """SubAgent with LLM-powered execution for natural language tasks."""

    def __init__(
        self,
        name: str,
        instructions: str,
        workdir: Path = None,
        tool_registry: Dict[str, Callable] = None,
        llm_client: Any = None,
        model: str = "gpt-4",
    ):
        super().__init__(name, instructions, workdir, tool_registry)
        self.llm_client = llm_client
        self.model = model

    async def _execute_task(self, task: str, context: Dict) -> Any:
        """Execute task using LLM."""
        if not self.llm_client:
            await asyncio.sleep(0.05)
            return f"LLM response to: {task[:50]}..."

        messages = [
            {"role": "system", "content": self.instructions},
            {"role": "user", "content": task},
        ]

        response = await self.llm_client.chat.completions.create(
            model=self.model,
            messages=messages,
        )

        return response.choices[0].message.content


async def create_parallel_pipeline(
    tasks: List[str],
    max_concurrent: int = 5,
    tool_registry: Dict[str, Callable] = None,
) -> List[Dict]:
    """Helper function to run multiple tasks in parallel."""
    pool = SubAgentPool(max_agents=max_concurrent)

    if tool_registry:
        for name, func in tool_registry.items():
            pool.register_tool(name, func)

    task_dicts = [{"task": t, "agent_name": f"pipeline-{i}"} for i, t in enumerate(tasks)]
    results = await pool.run_parallel(task_dicts)

    return [
        {
            "agent": r.agent_name,
            "status": r.status.value,
            "result": r.result,
            "error": r.error,
            "duration_ms": r.duration_ms,
        }
        for r in results
    ]