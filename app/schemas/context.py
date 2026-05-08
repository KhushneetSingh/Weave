"""Schemas for the shared agent context / conversation window."""

from __future__ import annotations

import enum
import uuid
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """A single message in an agent's conversation history."""

    role: MessageRole
    content: str
    # Optional name (used for tool-result messages)
    name: str | None = None
    # Token count — populated after estimation / API response
    token_count: int = 0

    model_config = {"use_enum_values": True}


class AgentContext(BaseModel):
    """
    The complete context window passed to an agent on each turn.

    Tracks the running token total so BudgetManager can gate each call.
    """

    job_id: uuid.UUID
    agent_name: str
    messages: list[Message] = Field(default_factory=list)
    # Soft limit — enforced by BudgetManager before each LLM call
    token_budget: int = 4000
    # Running total updated by BudgetManager after each successful call
    tokens_used: int = 0
    # Arbitrary key-value metadata agents can attach (e.g. task description)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.token_budget - self.tokens_used)

    def add_message(self, message: Message) -> None:
        """Append a message and update the running token total."""
        self.messages.append(message)
        self.tokens_used += message.token_count

    def to_openai_messages(self) -> list[dict[str, str]]:
        """Serialise messages to the format expected by the OpenAI-compatible API."""
        result = []
        for msg in self.messages:
            entry: dict[str, str] = {"role": msg.role, "content": msg.content}
            if msg.name:
                entry["name"] = msg.name
            result.append(entry)
        return result
