"""
BaseTool — abstract base class for all tools.

Provides timeout, retry, logging, and rejection support.
Every concrete tool implements ``_execute``.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any

from app.schemas.tools import ToolResult


class BaseTool(ABC):
    """
    Abstract base for every tool in the system.

    Wraps ``_execute`` with timeout, retry, and logging.
    """

    name: str = "base"
    timeout_seconds: float = 10.0
    max_retries: int = 2

    # ── Public call ──────────────────────────────────────────────────────────

    async def call(
        self,
        input: dict,
        job_id: str,
        agent_id: str,
    ) -> ToolResult:
        """
        Execute the tool with timeout + retry.

        Each attempt is logged to the ToolLog DB table (fire-and-forget).
        """
        last_result: ToolResult | None = None
        current_input = dict(input)

        for attempt in range(1, self.max_retries + 1):
            start = time.perf_counter()
            try:
                result = await asyncio.wait_for(
                    self._execute(current_input),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError:
                result = self.on_timeout()
            except Exception as exc:
                result = self.on_malformed(str(exc))

            elapsed_ms = (time.perf_counter() - start) * 1000
            result.latency_ms = elapsed_ms
            result.retry_count = attempt - 1
            result.input_used = current_input

            # Persist to ToolLog (fire-and-forget)
            self._log_attempt(
                job_id=job_id,
                agent_id=agent_id,
                result=result,
                attempt=attempt,
            )

            # If accepted, return immediately
            if result.status == "success":
                last_result = result
                break

            last_result = result
            # Allow agent to modify input on retry
            current_input = self._modify_input_on_retry(current_input, result)

        return last_result  # type: ignore[return-value]

    def reject(self, result: ToolResult) -> ToolResult:
        """Mark a result as rejected (accepted=False), triggering retry."""
        result.status = "error"
        return result

    # ── Abstract method ──────────────────────────────────────────────────────

    @abstractmethod
    async def _execute(self, input: dict) -> ToolResult:
        """Concrete tools implement this."""
        raise NotImplementedError

    # ── Fallback handlers ────────────────────────────────────────────────────

    def on_timeout(self) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            status="timeout",
            data={"reason": f"Tool '{self.name}' timed out after {self.timeout_seconds}s"},
        )

    def on_empty(self) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            status="empty",
            data={"reason": "No input provided or input was empty"},
        )

    def on_malformed(self, error: str) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            status="parse_error",
            data={"reason": f"Malformed input or execution error: {error}"},
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _modify_input_on_retry(self, input: dict, result: ToolResult) -> dict:
        """Hook for subclasses to modify input between retries."""
        return input

    def _log_attempt(
        self,
        job_id: str,
        agent_id: str,
        result: ToolResult,
        attempt: int,
    ) -> None:
        """Fire-and-forget write to ToolLog DB table."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._persist_tool_log(job_id, agent_id, result, attempt)
            )
        except RuntimeError:
            pass

    async def _persist_tool_log(
        self,
        job_id: str,
        agent_id: str,
        result: ToolResult,
        attempt: int,
    ) -> None:
        try:
            from app.database import AsyncSessionLocal
            from app.models.tool_log import ToolLog

            async with AsyncSessionLocal() as session:
                row = ToolLog(
                    job_id=job_id,
                    agent_id=agent_id,
                    tool_name=self.name,
                    status=result.status,
                    input=result.input_used,
                    output=result.data if isinstance(result.data, dict) else {"raw": result.data},
                    latency_ms=int(result.latency_ms),
                    retry_count=attempt - 1,
                    accepted=(result.status == "success"),
                )
                session.add(row)
                await session.commit()
        except Exception:
            pass  # fire-and-forget — never crash the tool pipeline
