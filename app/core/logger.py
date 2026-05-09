"""
Structured logging — JSON output via structlog.

Every log event includes: timestamp, agent_id, event_type, job_id,
input_hash (sha256), output_hash (sha256), latency_ms, token_count,
policy_violation.

Also writes to AgentLog DB table asynchronously (fire-and-forget).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

import structlog

from app.config import settings

# ── structlog configuration ──────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(settings.log_level.upper())
    ),
    cache_logger_on_first_use=True,
)

_log = structlog.get_logger("weave.core")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sha256(obj: Any) -> str:
    """Return the sha256 hex digest of a JSON-serialised object."""
    raw = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


async def _persist_agent_log(
    agent_id: str,
    event_type: str,
    job_id: str,
    input_hash: str,
    output_hash: str,
    latency_ms: float,
    token_count: int,
    violation: str | None,
    payload: dict | None,
) -> None:
    """Fire-and-forget write to the AgentLog table."""
    try:
        from app.database import AsyncSessionLocal
        from app.models.agent_log import AgentLog

        async with AsyncSessionLocal() as session:
            log_row = AgentLog(
                job_id=job_id,
                agent_id=agent_id,
                event_type=event_type,
                input_hash=input_hash,
                output_hash=output_hash,
                latency_ms=int(latency_ms),
                token_count=token_count,
                policy_violation=violation,
                payload=payload,
            )
            session.add(log_row)
            await session.commit()
    except Exception as exc:
        _log.error("failed_to_persist_agent_log", error=str(exc), agent_id=agent_id)


# ── Public API ───────────────────────────────────────────────────────────────

def log_event(
    agent_id: str,
    event_type: str,
    job_id: str,
    input: Any,
    output: Any,
    latency_ms: float,
    token_count: int,
    violation: str | None = None,
) -> None:
    """
    Emit a structured log event and persist to DB (fire-and-forget).

    Parameters
    ----------
    agent_id : str
        Identifier of the agent that produced the event.
    event_type : str
        Category of event (e.g. ``agent_run``, ``tool_call``).
    job_id : str
        UUID of the parent job.
    input / output : Any
        Arbitrary payloads — hashed for the log line, stored in DB payload.
    latency_ms : float
        Wall-clock milliseconds for the operation.
    token_count : int
        Tokens consumed.
    violation : str | None
        Description of any policy violation, if applicable.
    """
    input_hash = _sha256(input)
    output_hash = _sha256(output)

    _log.info(
        event_type,
        agent_id=agent_id,
        job_id=str(job_id),
        input_hash=input_hash,
        output_hash=output_hash,
        latency_ms=latency_ms,
        token_count=token_count,
        policy_violation=violation,
    )

    # Fire-and-forget DB persistence
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            _persist_agent_log(
                agent_id=agent_id,
                event_type=event_type,
                job_id=job_id,
                input_hash=input_hash,
                output_hash=output_hash,
                latency_ms=latency_ms,
                token_count=token_count,
                violation=violation,
                payload={"input": input, "output": output},
            )
        )
    except RuntimeError:
        # No event loop running — skip async persistence (e.g. during tests)
        pass
