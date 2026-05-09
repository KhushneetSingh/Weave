"""
SelfReflectionTool — reads agent outputs and uses LLM to find contradictions.
"""

from __future__ import annotations

import json

from app.core.llm import chat
from app.schemas.tools import ToolResult
from app.tools.base import BaseTool

_REFLECTION_PROMPT = """\
You are a contradiction detector. You are given outputs from multiple AI agents.
Your task is to find contradictions — cases where two agents make conflicting claims.

For each contradiction found, return a JSON object with:
- agent_a: ID of the first agent
- agent_b: ID of the second agent
- claim_a: the claim from agent_a
- claim_b: the conflicting claim from agent_b
- conflict_description: a brief description of why these conflict

Return a JSON object with a single key "contradictions" containing a list.
If no contradictions are found, return {"contradictions": []}.
Return ONLY valid JSON, no markdown fences or explanation.
"""


class SelfReflectionTool(BaseTool):
    """Detect contradictions between agent outputs via LLM analysis."""

    name: str = "self_reflection"
    timeout_seconds: float = 15.0

    async def _execute(self, input: dict) -> ToolResult:
        agent_outputs: dict = input.get("agent_outputs", {})
        if not agent_outputs:
            return self.on_empty()

        # Format agent outputs for the LLM
        formatted_parts: list[str] = []
        for agent_id, output in agent_outputs.items():
            content = output.get("content", "") if isinstance(output, dict) else str(output)
            formatted_parts.append(f"[Agent: {agent_id}]\n{content}")

        combined = "\n\n---\n\n".join(formatted_parts)

        messages = [
            {"role": "system", "content": _REFLECTION_PROMPT},
            {"role": "user", "content": f"Analyze these agent outputs for contradictions:\n\n{combined}"},
        ]

        try:
            response, _ = await chat(messages, temperature=0.1)
            # Parse the JSON response
            parsed = json.loads(response)
            contradictions = parsed.get("contradictions", [])
            return ToolResult(
                tool_name=self.name,
                status="success",
                data={"contradictions": contradictions},
            )
        except json.JSONDecodeError as exc:
            return self.on_malformed(f"LLM returned invalid JSON: {exc}")
        except Exception as exc:
            return self.on_malformed(f"Reflection failed: {exc}")
