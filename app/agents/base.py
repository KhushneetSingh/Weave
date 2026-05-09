"""
BaseAgent — abstract base class for every agent in the orchestration pipeline.

Handles budget checking, LLM calling, token accounting, structured logging,
and writing results to SharedContext.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from abc import ABC, abstractmethod
from typing import Any

from app.core.budget_manager import ContextBudgetManager
from app.core.llm import chat
from app.core.logger import log_event
from app.schemas.context import AgentOutput, SharedContext


class NeedCompressionError(Exception):
    """Raised when an agent cannot fit within the remaining token budget."""

    def __init__(self, agent_id: str, requested: int, remaining: int) -> None:
        self.agent_id = agent_id
        self.requested = requested
        self.remaining = remaining
        super().__init__(
            f"Agent '{agent_id}' needs {requested} tokens but only {remaining} remain. "
            "Compression required."
        )


class BaseAgent(ABC):
    """
    Abstract base for pipeline agents.

    Subclasses set ``agent_id``, ``max_budget``, ``system_prompt`` and
    implement ``_build_messages`` and ``_parse_output``.
    """

    agent_id: str = "base"
    max_budget: int = 1000
    system_prompt: str = "You are a helpful assistant."

    async def run(
        self,
        context: SharedContext,
        budget_manager: ContextBudgetManager,
        event_queue: asyncio.Queue | None = None,
    ) -> AgentOutput:
        """
        Execute the agent.

        1. Check budget → raise NeedCompressionError if insufficient
        2. Build messages from context
        3. Call LLM (with optional token streaming)
        4. Account tokens
        5. Parse structured output
        6. Write to context
        7. Log event
        """
        start = time.perf_counter()

        # 1. Budget gate
        if not budget_manager.check_budget(self.agent_id, self.max_budget):
            raise NeedCompressionError(
                agent_id=self.agent_id,
                requested=self.max_budget,
                remaining=budget_manager.remaining(),
            )

        # Emit agent_start event
        if event_queue:
            await event_queue.put({
                "type": "agent_start",
                "agent_id": self.agent_id,
                "budget_remaining": budget_manager.remaining(),
            })

        # 2. Build messages
        messages = self._build_messages(context)

        # 3. Call LLM
        content, token_count = await chat(
            messages=messages,
            event_queue=event_queue,
            agent_id=self.agent_id,
        )

        # 4. Account tokens
        budget_manager.add_tokens(self.agent_id, token_count)

        # Emit budget_update
        if event_queue:
            await event_queue.put({
                "type": "budget_update",
                "agent_id": self.agent_id,
                "used": budget_manager.used,
                "remaining": budget_manager.remaining(),
            })

        # 5. Parse structured output
        parsed = self._parse_llm_json(content)
        agent_output = self._parse_output(parsed, context)
        agent_output.token_count = token_count

        elapsed_ms = (time.perf_counter() - start) * 1000
        agent_output.latency_ms = elapsed_ms

        # 6. Write to context
        context.agent_outputs[self.agent_id] = agent_output

        # 7. Log
        log_event(
            agent_id=self.agent_id,
            event_type="agent_run",
            job_id=context.job_id,
            input={"query": context.query},
            output=parsed,
            latency_ms=elapsed_ms,
            token_count=token_count,
        )

        return agent_output

    # ── Abstract hooks ───────────────────────────────────────────────────────

    @abstractmethod
    def _build_messages(self, context: SharedContext) -> list[dict]:
        """Build the OpenAI-style messages list from shared context."""
        ...

    @abstractmethod
    def _parse_output(self, parsed: dict, context: SharedContext) -> AgentOutput:
        """Convert the parsed LLM JSON into an AgentOutput and update context."""
        ...

    # ── JSON extraction helper ───────────────────────────────────────────────

    @staticmethod
    def _parse_llm_json(content: str) -> dict:
        """
        Extract JSON from LLM response.

        Tries direct parse first, then looks for ```json fences,
        then falls back to finding the first { ... } block.
        """
        content = content.strip()

        # Direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Strip markdown fences
        fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Find first JSON object
        brace_match = re.search(r"\{.*\}", content, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback — return raw content wrapped
        return {"raw": content}
