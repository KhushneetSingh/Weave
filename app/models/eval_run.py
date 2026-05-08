"""EvalRun model — stores evaluation results for a job or agent output."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

import enum


class EvalStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


class EvalRun(Base):
    """
    Captures the result of running an evaluation suite against a job's outputs.
    Supports multiple eval runs per job (e.g. different evaluators or iterations).
    """

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluator_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[EvalStatus] = mapped_column(
        Enum(EvalStatus, name="eval_status"),
        nullable=False,
        default=EvalStatus.SKIP,
    )
    # Numeric score in [0.0, 1.0] — optional; depends on evaluator
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Human-readable rationale or error detail from the evaluator
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Arbitrary per-evaluator metrics (e.g. {"faithfulness": 0.9, "relevance": 0.8})
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job = relationship("Job", lazy="raise", back_populates=None)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<EvalRun id={self.id} evaluator={self.evaluator_name} "
            f"status={self.status} score={self.score}>"
        )
