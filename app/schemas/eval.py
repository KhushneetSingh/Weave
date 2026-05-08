"""Schemas for evaluation requests and responses."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.models.eval_run import EvalStatus


class EvalCriteria(BaseModel):
    """A single named criterion used by an evaluator."""

    name: str
    description: str
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class EvalRequest(BaseModel):
    """
    Payload submitted to an evaluator agent.
    Contains the original task, the agent's response, and any criteria to score against.
    """

    job_id: uuid.UUID
    evaluator_name: str
    task_description: str
    agent_response: str
    criteria: list[EvalCriteria] = Field(default_factory=list)
    # Additional context the evaluator may need
    context: dict[str, Any] = Field(default_factory=dict)


class EvalResponse(BaseModel):
    """
    Structured result returned by an evaluator.
    Maps 1-to-1 to an EvalRun DB row.
    """

    job_id: uuid.UUID
    evaluator_name: str
    status: EvalStatus
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = None
    # Per-criterion breakdown scores
    metrics: dict[str, float] = Field(default_factory=dict)
