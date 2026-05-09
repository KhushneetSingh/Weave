"""
DecompositionAgent — breaks a user query into a SubTask dependency graph.
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.context import AgentOutput, SharedContext, SubTask


_SYSTEM_PROMPT = """\
You are a task decomposition specialist. Given a user query, break it down into
a list of concrete sub-tasks that, when completed in order, fully answer the query.

Each sub-task has:
- id: a short unique slug (e.g. "t1", "t2")
- description: what this sub-task does
- task_type: one of "research", "analysis", "synthesis", "verification"
- dependencies: list of sub-task IDs that must complete before this one

Return ONLY a JSON object like:
{
  "sub_tasks": [
    {"id": "t1", "description": "...", "task_type": "research", "dependencies": []},
    {"id": "t2", "description": "...", "task_type": "analysis", "dependencies": ["t1"]}
  ]
}
"""


class DecompositionAgent(BaseAgent):
    """Decomposes a query into a SubTask list with dependency graph."""

    agent_id: str = "decomposition"
    max_budget: int = 1200
    system_prompt: str = _SYSTEM_PROMPT

    def _build_messages(self, context: SharedContext) -> list[dict]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Decompose this query into sub-tasks:\n\n{context.query}"},
        ]

    def _parse_output(self, parsed: dict, context: SharedContext) -> AgentOutput:
        raw_tasks = parsed.get("sub_tasks", [])
        sub_tasks: list[SubTask] = []
        for t in raw_tasks:
            sub_tasks.append(
                SubTask(
                    id=t.get("id", f"t{len(sub_tasks) + 1}"),
                    description=t.get("description", ""),
                    task_type=t.get("task_type", "research"),
                    dependencies=t.get("dependencies", []),
                    status="pending",
                )
            )

        # If parsing failed or returned empty, create a single default task
        if not sub_tasks:
            sub_tasks = [
                SubTask(
                    id="t1",
                    description=f"Research and answer: {context.query}",
                    task_type="research",
                    dependencies=[],
                ),
            ]

        # Write to context
        context.sub_tasks = sub_tasks

        return AgentOutput(
            agent_id=self.agent_id,
            content=f"Decomposed query into {len(sub_tasks)} sub-tasks.",
            confidence=0.9,
        )
