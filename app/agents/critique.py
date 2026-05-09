"""
CritiqueAgent — reviews other agent outputs with per-claim confidence
scoring and span-level flagging.
"""

from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.schemas.context import (
    AgentOutput,
    Contradiction,
    FlaggedSpan,
    SharedContext,
)

_SYSTEM_PROMPT = """\
You are a critical reviewer. You are given outputs from multiple AI agents.
For each agent output, evaluate individual claims:

1. Assign a confidence score (0.0-1.0) to each claim.
2. Flag specific spans of text that are problematic, with:
   - span: the exact problematic text
   - reason: why it is problematic
   - suggested: a suggested correction
3. If two agents make conflicting claims, note the contradiction.

Return ONLY a JSON object:
{
  "reviews": [
    {
      "agent_id": "rag",
      "claim": "specific claim being evaluated",
      "confidence": 0.85,
      "flagged_spans": [
        {"span": "exact text", "reason": "why it's wrong", "suggested": "correction"}
      ]
    }
  ]
}
"""


class CritiqueAgent(BaseAgent):
    """Reviews all agent outputs with per-claim confidence and span flagging."""

    agent_id: str = "critique"
    max_budget: int = 1500
    system_prompt: str = _SYSTEM_PROMPT

    def _build_messages(self, context: SharedContext) -> list[dict]:
        # Format all agent outputs for review
        parts: list[str] = []
        for agent_id, output in context.agent_outputs.items():
            if agent_id == self.agent_id:
                continue  # Don't self-review
            parts.append(f"[Agent: {agent_id}]\n{output.content}")

        combined = "\n\n---\n\n".join(parts) if parts else "No agent outputs to review."

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Review these agent outputs:\n\n{combined}"},
        ]

    def _parse_output(self, parsed: dict, context: SharedContext) -> AgentOutput:
        reviews = parsed.get("reviews", [])

        # Build contradictions from flagged spans
        contradictions: list[Contradiction] = []
        all_flagged: list[FlaggedSpan] = []

        for review in reviews:
            agent_id = review.get("agent_id", "unknown")
            flagged_spans = review.get("flagged_spans", [])

            for span_data in flagged_spans:
                flagged = FlaggedSpan(
                    span=span_data.get("span", ""),
                    reason=span_data.get("reason", ""),
                    suggested=span_data.get("suggested", ""),
                    confidence=review.get("confidence", 0.5),
                )
                all_flagged.append(flagged)

                # Create contradiction entries for flagged spans
                contradictions.append(
                    Contradiction(
                        agent_a=agent_id,
                        agent_b=self.agent_id,
                        claim_a=span_data.get("span", ""),
                        claim_b=span_data.get("suggested", ""),
                        conflict_description=span_data.get("reason", "Flagged by critique agent"),
                    )
                )

        # Write contradictions to context
        context.contradictions.extend(contradictions)

        return AgentOutput(
            agent_id=self.agent_id,
            content=json.dumps({"reviews": reviews}),
            confidence=0.9,
            flagged_spans=all_flagged,
        )
