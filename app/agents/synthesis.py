"""
SynthesisAgent — produces the final answer by resolving contradictions
and building a provenance map.
"""

from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.schemas.context import AgentOutput, SharedContext

_SYSTEM_PROMPT = """\
You are a synthesis specialist. You are given:
1. Outputs from multiple agents (possibly conflicting)
2. A list of contradictions flagged by the critique agent
3. Sub-tasks that were decomposed from the original query

Your job:
1. Resolve each contradiction by choosing the more supported claim, and explain why.
2. Produce a comprehensive final answer that incorporates the best information.
3. For each sentence in your answer, indicate which agent provided the source.

Return ONLY a JSON object:
{
  "answer": "your comprehensive final answer",
  "provenance_map": {
    "Sentence from the answer": "source_agent_id"
  },
  "resolved_contradictions": [
    {
      "agent_a": "...",
      "agent_b": "...",
      "claim_a": "...",
      "claim_b": "...",
      "resolution": "explanation of which claim is correct and why"
    }
  ]
}
"""


class SynthesisAgent(BaseAgent):
    """Produces final answer, resolves contradictions, builds provenance map."""

    agent_id: str = "synthesis"
    max_budget: int = 1500
    system_prompt: str = _SYSTEM_PROMPT

    def _build_messages(self, context: SharedContext) -> list[dict]:
        output_parts: list[str] = []
        for agent_id, output in context.agent_outputs.items():
            output_parts.append(f"[Agent: {agent_id}]\n{output.content}")
        outputs_text = "\n\n---\n\n".join(output_parts) if output_parts else "None"

        contradiction_parts: list[str] = []
        for c in context.contradictions:
            contradiction_parts.append(
                f"- {c.agent_a} says: \"{c.claim_a}\" vs {c.agent_b} says: \"{c.claim_b}\" "
                f"({c.conflict_description})"
            )
        contradictions_text = "\n".join(contradiction_parts) if contradiction_parts else "None"

        task_parts: list[str] = []
        for t in context.sub_tasks:
            task_parts.append(f"- [{t.id}] {t.description} (status: {t.status})")
        tasks_text = "\n".join(task_parts) if task_parts else "None"

        user_msg = (
            f"Original query: {context.query}\n\n"
            f"Sub-tasks:\n{tasks_text}\n\n"
            f"Agent outputs:\n{outputs_text}\n\n"
            f"Contradictions to resolve:\n{contradictions_text}"
        )

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_msg},
        ]

    def _parse_output(self, parsed: dict, context: SharedContext) -> AgentOutput:
        answer = parsed.get("answer", parsed.get("raw", "Unable to synthesize answer."))
        provenance_map = parsed.get("provenance_map", {})
        resolved = parsed.get("resolved_contradictions", [])

        context.provenance_map = provenance_map

        for rc in resolved:
            for c in context.contradictions:
                if (
                    c.agent_a == rc.get("agent_a")
                    and c.agent_b == rc.get("agent_b")
                    and not c.resolved
                ):
                    c.resolved = True
                    c.resolution = rc.get("resolution", "Resolved by synthesis agent")
                    break

        return AgentOutput(
            agent_id=self.agent_id,
            content=answer,
            confidence=0.9,
        )
