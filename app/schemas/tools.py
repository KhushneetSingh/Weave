"""Schemas for tool calls and results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """
    Represents a tool invocation request emitted by an agent.
    Maps directly to the OpenAI function-calling / tool-use format.
    """

    tool_name: str = Field(..., description="Registered name of the tool to invoke.")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value arguments to pass to the tool.",
    )
    # Optional call ID — mirrors OpenAI's tool_call_id for multi-turn tracking
    call_id: str | None = None


class ToolResult(BaseModel):
    """
    The output returned by a tool after execution.
    Agents receive this to continue reasoning.
    """

    call_id: str | None = None
    tool_name: str
    output: Any = None
    success: bool = True
    error_message: str | None = None
    # Wall-clock latency in seconds
    latency_seconds: float | None = None

    @property
    def as_message_content(self) -> str:
        """Format result as a string suitable for a 'tool' role message."""
        if self.success:
            return str(self.output)
        return f"[ERROR] {self.error_message}"
