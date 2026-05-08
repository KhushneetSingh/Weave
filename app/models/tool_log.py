"""ToolLog model — records individual tool invocations made by agents."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ToolLog(Base):
    """
    Each row captures one tool call: the inputs sent, the output received,
    latency, and whether it succeeded.
    """

    __tablename__ = "tool_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Link back to the agent turn that triggered this tool call
    agent_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # JSON-serialisable inputs passed to the tool
    inputs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Raw string output (may be JSON, plain text, error message, etc.)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Wall-clock latency in seconds
    latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent_log = relationship("AgentLog", lazy="raise", back_populates=None)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ToolLog id={self.id} tool={self.tool_name} success={self.success}>"
