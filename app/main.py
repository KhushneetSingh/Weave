import asyncio
import json
import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
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
    description="Multi-agent LLM orchestration system with self-improving eval loop",
    version="0.4.0",
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


# ── Standardised error response ──────────────────────────────────────────────

class WeaveError(Exception):
    """Application-level error with a structured error_code."""

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = 400,
        job_id: str | None = None,
    ) -> None:
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.job_id = job_id
        super().__init__(message)


@app.exception_handler(WeaveError)
async def weave_error_handler(_request: Request, exc: WeaveError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "job_id": exc.job_id,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": "HTTP_ERROR",
            "message": str(exc.detail),
            "job_id": None,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
            "job_id": None,
        },
    )


# ── Request schemas ───────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    max_budget: int = 4000


class EvalRunRequest(BaseModel):
    case_ids: list[str] | None = None


class PromptReviewRequest(BaseModel):
    decision: str  # "approve" | "reject"
    reviewer_note: str = ""


class ReRunFailedRequest(BaseModel):
    use_approved_prompts: bool = True


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


# ── GET /jobs/{job_id}/trace ─────────────────────────────────────────────────

@app.get("/jobs/{job_id}/trace", tags=["orchestration"])
async def job_trace(job_id: str):
    """
    Reconstruct an ordered trace of all events (AgentLog + ToolLog)
    for a given job.
    """
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.agent_log import AgentLog
    from app.models.job import Job
    from app.models.tool_log import ToolLog

    async with AsyncSessionLocal() as session:
        # Fetch job
        result = await session.execute(
            select(Job).where(Job.id == uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()

    if not job:
        raise WeaveError(
            error_code="JOB_NOT_FOUND",
            message="No job with that ID",
            status_code=404,
            job_id=job_id,
        )

    async with AsyncSessionLocal() as session:
        # Fetch agent logs
        agent_result = await session.execute(
            select(AgentLog)
            .where(AgentLog.job_id == uuid.UUID(job_id))
            .order_by(AgentLog.timestamp)
        )
        agent_logs = agent_result.scalars().all()

        # Fetch tool logs
        tool_result = await session.execute(
            select(ToolLog)
            .where(ToolLog.job_id == uuid.UUID(job_id))
            .order_by(ToolLog.timestamp)
        )
        tool_logs = tool_result.scalars().all()

    # Merge and sort by timestamp
    events: list[dict] = []

    for al in agent_logs:
        events.append({
            "timestamp": al.timestamp.isoformat() if al.timestamp else None,
            "event_type": al.event_type,
            "agent_id": al.agent_id,
            "details": {
                "latency_ms": al.latency_ms,
                "token_count": al.token_count,
                "policy_violation": al.policy_violation,
                "payload": al.payload,
            },
        })

    for tl in tool_logs:
        events.append({
            "timestamp": tl.timestamp.isoformat() if tl.timestamp else None,
            "event_type": f"tool_call:{tl.tool_name}",
            "agent_id": tl.agent_id,
            "details": {
                "tool_name": tl.tool_name,
                "status": tl.status,
                "latency_ms": tl.latency_ms,
                "retry_count": tl.retry_count,
                "accepted": tl.accepted,
                "input": tl.input,
                "output": tl.output,
            },
        })

    # Sort all events by timestamp
    events.sort(key=lambda e: e["timestamp"] or "")

    return {
        "job_id": str(job.id),
        "query": job.query,
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "total_latency_ms": float(job.total_latency_ms),
        "total_tokens": job.total_tokens,
        "events": events,
    }


# ── GET /eval/latest ─────────────────────────────────────────────────────────

@app.get("/eval/latest", tags=["eval"])
async def eval_latest():
    """Return the latest eval run summary grouped by category + dimension."""
    from sqlalchemy import desc, select

    from app.database import AsyncSessionLocal
    from app.models.eval_run import EvalRun

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EvalRun).order_by(desc(EvalRun.timestamp)).limit(2)
        )
        runs = result.scalars().all()

    if not runs or not runs[0].scores:
        raise WeaveError(
            error_code="EVAL_NOT_FOUND",
            message="No eval runs found.",
            status_code=404,
        )

    latest = runs[0]
    previous = runs[1] if len(runs) > 1 else None

    dimensions = [
        "answer_correctness", "citation_accuracy",
        "contradiction_resolution", "tool_efficiency",
        "budget_compliance", "critique_agreement",
    ]

    # ── by_category ──────────────────────────────────────────────────
    by_type: dict[str, list[dict]] = {}
    for entry in latest.scores:
        ct = entry.get("case_type", "unknown")
        by_type.setdefault(ct, []).append(entry)

    by_category: dict = {}
    for case_type, entries in by_type.items():
        type_scores = [_compute_total(e) for e in entries]
        avg_score = round(sum(type_scores) / len(type_scores), 3) if type_scores else 0.0

        cases = []
        for e in entries:
            dim_map = {}
            for dim in dimensions:
                dim_data = e.get(dim, {})
                dim_map[dim] = dim_data.get("score", 0.0) if isinstance(dim_data, dict) else 0.0
            cases.append({
                "id": e.get("case_id", ""),
                "total_score": round(_compute_total(e), 3),
                "dimensions": dim_map,
            })
        by_category[case_type] = {"avg_score": avg_score, "cases": cases}

    # ── by_dimension ─────────────────────────────────────────────────
    by_dimension: dict = {}
    for dim in dimensions:
        dim_scores = []
        for entry in latest.scores:
            dim_data = entry.get(dim, {})
            score = dim_data.get("score", 0.0) if isinstance(dim_data, dict) else 0.0
            dim_scores.append(score)
        by_dimension[dim] = {
            "avg": round(sum(dim_scores) / len(dim_scores), 3) if dim_scores else 0.0,
            "min": round(min(dim_scores), 3) if dim_scores else 0.0,
            "max": round(max(dim_scores), 3) if dim_scores else 0.0,
        }

    # ── delta_vs_previous ────────────────────────────────────────────
    delta_vs_previous = None
    if previous and previous.scores:
        # Overall delta
        current_total = sum(_compute_total(e) for e in latest.scores) / len(latest.scores)
        prev_total = sum(_compute_total(e) for e in previous.scores) / len(previous.scores)
        overall_delta = round(current_total - prev_total, 3)

        dim_delta: dict = {}
        for dim in dimensions:
            cur_vals = [
                e.get(dim, {}).get("score", 0.0) if isinstance(e.get(dim, {}), dict) else 0.0
                for e in latest.scores
            ]
            prev_vals = [
                e.get(dim, {}).get("score", 0.0) if isinstance(e.get(dim, {}), dict) else 0.0
                for e in previous.scores
            ]
            cur_avg = sum(cur_vals) / len(cur_vals) if cur_vals else 0.0
            prev_avg = sum(prev_vals) / len(prev_vals) if prev_vals else 0.0
            dim_delta[dim] = round(cur_avg - prev_avg, 3)

        delta_vs_previous = {"overall": overall_delta, "by_dimension": dim_delta}

    return {
        "run_id": str(latest.id),
        "timestamp": latest.timestamp.isoformat() if latest.timestamp else None,
        "total_cases": len(latest.scores),
        "by_category": by_category,
        "by_dimension": by_dimension,
        "delta_vs_previous": delta_vs_previous,
    }


# ── POST /eval/run ────────────────────────────────────────────────────────────

@app.post("/eval/run", tags=["eval"])
async def eval_run(body: EvalRunRequest = EvalRunRequest()):
    """
    Start an evaluation run as a Celery background task.
    Returns immediately with a run_id.
    """
    from app.worker.tasks import run_eval_task

    run_type = "targeted" if body.case_ids else "full"
    case_count = len(body.case_ids) if body.case_ids else 15

    task = run_eval_task.delay(
        run_type=run_type,
        case_ids=body.case_ids,
    )

    return {
        "run_id": task.id,
        "status": "started",
        "case_count": case_count,
    }


# ── POST /prompt-rewrites/{rewrite_id}/review ─────────────────────────────────

@app.post("/prompt-rewrites/{rewrite_id}/review", tags=["eval"])
async def review_prompt_rewrite(rewrite_id: str, body: PromptReviewRequest):
    """
    Approve or reject a pending prompt rewrite.

    If approved:
      - Updates PromptRewriteModel.status to "approved"
      - Patches the target agent's system_prompt in memory
      - Triggers re-eval on previously failed cases via Celery
    """
    from datetime import datetime, timezone

    from sqlalchemy import select, update

    from app.database import AsyncSessionLocal
    from app.models.prompt_rewrite import PromptRewrite as PromptRewriteModel

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PromptRewriteModel).where(
                PromptRewriteModel.id == uuid.UUID(rewrite_id)
            )
        )
        rewrite = result.scalar_one_or_none()

    if not rewrite:
        raise WeaveError(
            error_code="REWRITE_NOT_FOUND",
            message=f"Prompt rewrite {rewrite_id} not found.",
            status_code=404,
            job_id=None,
        )

    if rewrite.status != "pending":
        raise WeaveError(
            error_code="REWRITE_ALREADY_REVIEWED",
            message=f"Prompt rewrite {rewrite_id} has already been {rewrite.status}.",
            status_code=409,
            job_id=None,
        )

    if body.decision not in ("approve", "reject"):
        raise WeaveError(
            error_code="INVALID_INPUT",
            message="Decision must be 'approve' or 'reject'.",
            status_code=422,
            job_id=None,
        )

    now = datetime.now(timezone.utc)
    re_eval_triggered = False

    if body.decision == "approve":
        # 1. Update DB status
        async with AsyncSessionLocal() as session:
            stmt = (
                update(PromptRewriteModel)
                .where(PromptRewriteModel.id == uuid.UUID(rewrite_id))
                .values(
                    status="approved",
                    reviewer_note=body.reviewer_note,
                    approved_at=now,
                )
            )
            await session.execute(stmt)
            await session.commit()

        # 2. Patch agent's system_prompt in memory
        _patch_agent_prompt(rewrite.target_agent, rewrite.new_prompt)

        # 3. Trigger re-eval on failed cases
        from app.worker.tasks import run_eval_task

        run_eval_task.delay(run_type="full")
        re_eval_triggered = True

        logger.info(
            "Prompt rewrite %s approved for agent=%s. Re-eval triggered.",
            rewrite_id, rewrite.target_agent,
        )

    elif body.decision == "reject":
        async with AsyncSessionLocal() as session:
            stmt = (
                update(PromptRewriteModel)
                .where(PromptRewriteModel.id == uuid.UUID(rewrite_id))
                .values(
                    status="rejected",
                    reviewer_note=body.reviewer_note,
                )
            )
            await session.execute(stmt)
            await session.commit()

        logger.info("Prompt rewrite %s rejected.", rewrite_id)

    return {
        "rewrite_id": rewrite_id,
        "decision": body.decision,
        "timestamp": now.isoformat(),
        "re_eval_triggered": re_eval_triggered,
    }


# ── POST /eval/re-run-failed ─────────────────────────────────────────────────

@app.post("/eval/re-run-failed", tags=["eval"])
async def eval_rerun_failed(body: ReRunFailedRequest = ReRunFailedRequest()):
    """
    Re-run evaluation on previously failed cases.
    Optionally uses approved prompt rewrites.
    """
    from sqlalchemy import desc, select

    from app.database import AsyncSessionLocal
    from app.eval.harness import EvalHarness
    from app.models.eval_run import EvalRun

    # Find the latest run
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EvalRun).order_by(desc(EvalRun.timestamp)).limit(1)
        )
        latest = result.scalar_one_or_none()

    if not latest:
        raise WeaveError(
            error_code="EVAL_NOT_FOUND",
            message="No previous eval runs found.",
            status_code=404,
        )

    # If use_approved_prompts, apply any approved rewrites first
    if body.use_approved_prompts:
        await _apply_approved_rewrites()

    # Run failed cases via Celery
    from app.worker.tasks import run_eval_task

    task = run_eval_task.delay(
        run_type="targeted",
        previous_run_id=str(latest.id),
    )

    # Count failed cases
    harness = EvalHarness()
    failed_count = 0
    if latest.scores:
        for entry in latest.scores:
            total = harness._compute_total(entry)
            if total < 0.6:
                failed_count += 1

    return {
        "new_run_id": task.id,
        "cases_rerun": failed_count,
        "performance_delta": latest.delta or {},
    }


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


def _compute_total(score_entry: dict) -> float:
    """Compute unweighted mean of all 6 dimensions from a dict."""
    dims = [
        "answer_correctness", "citation_accuracy",
        "contradiction_resolution", "tool_efficiency",
        "budget_compliance", "critique_agreement",
    ]
    values = []
    for d in dims:
        dim_data = score_entry.get(d, {})
        score = dim_data.get("score", 0.0) if isinstance(dim_data, dict) else 0.0
        values.append(score)
    return sum(values) / len(values) if values else 0.0


def _patch_agent_prompt(agent_id: str, new_prompt: str) -> None:
    """Patch an agent's system_prompt in memory (class-level attribute)."""
    from app.agents.compression import CompressionAgent
    from app.agents.critique import CritiqueAgent
    from app.agents.decomposition import DecompositionAgent
    from app.agents.rag import RAGAgent
    from app.agents.synthesis import SynthesisAgent

    agent_map = {
        "decomposition": DecompositionAgent,
        "rag": RAGAgent,
        "critique": CritiqueAgent,
        "synthesis": SynthesisAgent,
        "compression": CompressionAgent,
    }
    cls = agent_map.get(agent_id)
    if cls:
        cls.system_prompt = new_prompt
        logger.info("Patched system_prompt for agent=%s in memory.", agent_id)
    else:
        logger.warning("Unknown agent_id=%s — cannot patch prompt.", agent_id)


async def _apply_approved_rewrites() -> None:
    """Load all approved rewrites from DB and patch agent prompts."""
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.prompt_rewrite import PromptRewrite as PromptRewriteModel

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PromptRewriteModel).where(PromptRewriteModel.status == "approved")
        )
        rewrites = result.scalars().all()

    for rw in rewrites:
        _patch_agent_prompt(rw.target_agent, rw.new_prompt)

    if rewrites:
        logger.info("Applied %d approved prompt rewrite(s).", len(rewrites))
