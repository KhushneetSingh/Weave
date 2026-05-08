"""AgentLog model — per-agent turn record within a job."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgentLog(Base):
    """
    Records a single reasoning/action turn taken by an agent.
    Each agent turn belongs to one Job.
    """

    __tablename__ = "agent_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Prompt sent to the LLM
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Raw LLM completion text
    completion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Model actually used for this turn
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Token counts returned by the API
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Optional structured metadata (tool calls, chain-of-thought, etc.)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships (lazy so async sessions stay explicit)
    job = relationship("Job", lazy="raise", back_populates=None)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AgentLog id={self.id} agent={self.agent_name} tokens={self.total_tokens}>"
        )
