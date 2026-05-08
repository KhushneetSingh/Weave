"""PromptRewrite model — tracks prompt optimisation/rewriting history."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PromptRewrite(Base):
    """
    Stores before/after snapshots of prompts when the system rewrites or
    compresses them to fit within the token budget.
    """

    __tablename__ = "prompt_rewrites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Which agent / step triggered the rewrite
    agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Strategy used: e.g. "truncate", "summarise", "compress"
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)

    original_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    original_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rewritten_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Compression ratio: rewritten_tokens / original_tokens
    compression_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job = relationship("Job", lazy="raise", back_populates=None)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PromptRewrite id={self.id} strategy={self.strategy} "
            f"ratio={self.compression_ratio:.2f}>"
        )
