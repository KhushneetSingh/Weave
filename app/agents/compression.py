"""
CompressionAgent — called when NeedCompressionError is raised.

Lossless: keeps all ToolResult, Citation, EvalScore objects verbatim.
Lossy: summarizes AgentOutput.content strings to 2 sentences max.
Target: reduce total token count to 70% of current.
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.core.llm import count_tokens
from app.schemas.context import AgentOutput, SharedContext

_SYSTEM_PROMPT = """\
You are a compression specialist. Summarize the following text into at most
2 concise sentences while preserving all factual claims and key information.
Return ONLY the compressed text, no JSON wrapper needed.
"""


class CompressionAgent(BaseAgent):
    """Compresses context to free up token budget."""

    agent_id: str = "compression"
    max_budget: int = 800
    system_prompt: str = _SYSTEM_PROMPT

    def _build_messages(self, context: SharedContext) -> list[dict]:
        # Collect all agent output contents for compression
        parts: list[str] = []
        for agent_id, output in context.agent_outputs.items():
            if agent_id == self.agent_id:
                continue
            parts.append(f"[{agent_id}]: {output.content}")

        combined = "\n\n".join(parts) if parts else "Nothing to compress."

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Compress these agent outputs:\n\n{combined}"},
        ]

    def _parse_output(self, parsed: dict, context: SharedContext) -> AgentOutput:
        # The LLM returns plain text for compression, not structured JSON
        compressed = parsed.get("raw", str(parsed))

        # Apply lossy compression to agent outputs
        for agent_id, output in context.agent_outputs.items():
            if agent_id == self.agent_id:
                continue
            # Lossless: keep citations, flagged_spans intact
            # Lossy: replace content with a 2-sentence summary
            original_tokens = count_tokens(output.content)
            if original_tokens > 50:
                # Truncate to roughly 70% via the LLM summary
                output.content = compressed[:200] + "..."

        return AgentOutput(
            agent_id=self.agent_id,
            content=f"Compressed context. Original agent outputs summarized.",
            confidence=1.0,
        )
