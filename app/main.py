import asyncio
import json
import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Weave",
    description="Multi-agent LLM orchestration system — Phase 2",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request schema ────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str
    max_budget: int = 4000


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Liveness probe — returns 200 when the API process is running."""
    return {"status": "ok", "version": app.version}


# ── SSE helper ────────────────────────────────────────────────────────────────
def _sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, default=str)}\n\n"


# ── POST /query  ──────────────────────────────────────────────────────────────
@app.post("/query", tags=["orchestration"])
async def query_endpoint(body: QueryRequest):
    """
    Launch the multi-agent pipeline and stream results via SSE.

    Event types:
        job_created, agent_start, token, tool_call, tool_result,
        routing, budget_update, done, error
    """
    job_id = str(uuid.uuid4())
    start_time = time.perf_counter()

    # ── Create job in DB ──────────────────────────────────────────────
    try:
        from app.database import AsyncSessionLocal
        from app.models.job import Job, JobStatus

        async with AsyncSessionLocal() as session:
            job = Job(id=job_id, query=body.query, status=JobStatus.RUNNING)
            session.add(job)
            await session.commit()
    except Exception as exc:
        logger.error("Failed to create job in DB: %s", exc)

    # ── Event generator ───────────────────────────────────────────────
    async def event_generator():
        event_queue: asyncio.Queue = asyncio.Queue()

        yield _sse_event({"type": "job_created", "job_id": job_id})

        # Run pipeline in background task
        pipeline_task = asyncio.create_task(
            _run_pipeline(body.query, job_id, body.max_budget, event_queue)
        )

        # Stream events from queue until pipeline completes
        while True:
            # Check if pipeline is done
            if pipeline_task.done():
                # Drain remaining events
                while not event_queue.empty():
                    event = event_queue.get_nowait()
                    yield _sse_event(event)
                break

            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                yield _sse_event(event)
            except asyncio.TimeoutError:
                continue

        # Handle pipeline result
        total_ms = (time.perf_counter() - start_time) * 1000
        try:
            ctx = pipeline_task.result()
            total_tokens = sum(
                o.token_count for o in ctx.agent_outputs.values()
            )
            # Update job in DB
            await _update_job_status(job_id, "completed", total_tokens, int(total_ms))

            yield _sse_event({
                "type": "done",
                "job_id": job_id,
                "total_tokens": total_tokens,
                "latency_ms": round(total_ms, 2),
            })
        except Exception as exc:
            await _update_job_status(job_id, "failed", 0, int(total_ms))
            yield _sse_event({
                "type": "error",
                "error_code": type(exc).__name__,
                "message": str(exc),
                "job_id": job_id,
            })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _run_pipeline(query, job_id, max_budget, event_queue):
    """Run the orchestrator pipeline — called as a background task."""
    from app.core.orchestrator import run_pipeline
    return await run_pipeline(
        query=query,
        job_id=job_id,
        max_budget=max_budget,
        event_queue=event_queue,
    )


async def _update_job_status(
    job_id: str, status: str, total_tokens: int, total_latency_ms: int
) -> None:
    """Update job row in Postgres."""
    try:
        from datetime import datetime, timezone

        from sqlalchemy import update

        from app.database import AsyncSessionLocal
        from app.models.job import Job, JobStatus

        status_enum = JobStatus(status)
        async with AsyncSessionLocal() as session:
            stmt = (
                update(Job)
                .where(Job.id == job_id)
                .values(
                    status=status_enum,
                    total_tokens=total_tokens,
                    total_latency_ms=total_latency_ms,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(stmt)
            await session.commit()
    except Exception as exc:
        logger.error("Failed to update job status: %s", exc)
