# Weave

> Multi-agent LLM orchestration system with self-improving evaluation loop.

Weave decomposes complex queries across specialised AI agents (decomposition, RAG, critique, synthesis), orchestrates them via LangGraph with dynamic routing, streams results over SSE, and continuously improves its own prompts through a 6-dimensional evaluation harness and meta-agent feedback loop.

---

## Setup (5 minutes)

```bash
git clone <repo>
cp .env.example .env   # add your OPENROUTER_API_KEY
docker compose up
```

That's it. All 4 services start automatically:
- **API** — `localhost:8000` (FastAPI + Swagger at `/docs`)
- **Worker** — Celery background tasks (eval runs, meta-agent)
- **Database** — PostgreSQL 15
- **Log UI** — `localhost:8080` (trace viewer)

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | **Yes** | — | Your OpenRouter API key |
| `OPENROUTER_MODEL` | No | `meta-llama/llama-3.1-8b-instruct:free` | Primary LLM model |
| `OPENROUTER_FALLBACK_MODEL` | No | `mistralai/mistral-7b-instruct:free` | Fallback model if primary fails |
| `POSTGRES_USER` | No | `megaai` | Postgres username |
| `POSTGRES_PASSWORD` | No | `megaai` | Postgres password |
| `POSTGRES_DB` | No | `megaai` | Postgres database name |
| `POSTGRES_HOST` | No | `db` | Postgres host (Docker service name) |
| `POSTGRES_PORT` | No | `5432` | Postgres port |
| `REDIS_URL` | No | `redis://redis:6379/0` | Redis URL for Celery broker |
| `MAX_CONTEXT_TOKENS` | No | `4000` | Max token budget per query |
| `LOG_LEVEL` | No | `INFO` | Logging level |

---

## Architecture

```
                          ┌─────────────────────────────────────────┐
                          │              FastAPI (8000)              │
                          │   POST /query  → SSE stream             │
                          │   GET  /jobs/{id}/trace                 │
                          │   GET  /eval/latest                     │
                          │   POST /eval/run                        │
                          │   POST /prompt-rewrites/{id}/review     │
                          │   POST /eval/re-run-failed              │
                          └────────────────┬────────────────────────┘
                                           │
                                           ▼
                          ┌─────────────────────────────────────────┐
                          │         LangGraph Orchestrator           │
                          │   (StateGraph with dynamic routing)      │
                          └─────┬──────┬──────┬──────┬──────┬───────┘
                                │      │      │      │      │
                     ┌──────────┘      │      │      │      └──────────┐
                     ▼                 ▼      │      ▼                 ▼
              ┌─────────────┐  ┌──────────┐   │  ┌──────────┐  ┌─────────────┐
              │Decomposition│  │   RAG    │   │  │ Critique │  │ Compression │
              │   Agent     │  │  Agent   │   │  │  Agent   │  │   Agent     │
              │ budget:1200 │  │budget:2000│  │  │budget:1500│  │ budget:800  │
              └──────┬──────┘  └────┬─────┘   │  └────┬─────┘  └─────────────┘
                     │              │         │       │
                     │              ▼         │       │
                     │         ┌─────────┐    │       │
                     │         │  FAISS  │    │       │
                     │         │  Index  │    │       │
                     │         └─────────┘    │       │
                     │                        ▼       │
                     │                 ┌──────────┐   │
                     │                 │Synthesis │   │
                     │                 │  Agent   │   │
                     │                 │budget:1500│  │
                     │                 └──────────┘   │
                     │                                │
                     └────────────┬───────────────────┘
                                  ▼
                          ┌──────────────┐       ┌────────────────┐
                          │SharedContext │──────▶│   PostgreSQL   │
                          │ (in-memory)  │       │  (Jobs, Logs,  │
                          └──────────────┘       │  EvalRuns,     │
                                                 │  Rewrites)     │
                                                 └────────────────┘
```

### Tools

Each agent can invoke tools via the tool framework (`app/tools/`):
- **web_search** — Simulated web search with retry + timeout
- **sql_lookup** — Database query execution
- **code_sandbox** — Python code execution (NOT sandboxed — see limitations)
- **self_reflection** — Agent self-evaluation

---

## Agents

| Agent | What it does | Reads from SharedContext | Writes to SharedContext | Token Budget |
|---|---|---|---|---|
| **Decomposition** | Breaks query into a SubTask dependency graph | `query` | `sub_tasks` | 1200 |
| **RAG** | Multi-hop retrieval from FAISS index (15 AI-topic docs, 2-hop, min 4 chunks) | `query`, `sub_tasks` | `agent_outputs["rag"]` with citations | 2000 |
| **Critique** | Per-claim confidence scoring and span-level flagging of other agent outputs | `agent_outputs` | `contradictions`, `agent_outputs["critique"]` with flagged spans | 1500 |
| **Synthesis** | Resolves contradictions, builds provenance map, produces final answer | `agent_outputs`, `contradictions`, `sub_tasks` | `provenance_map`, `agent_outputs["synthesis"]` | 1500 |
| **Compression** | Triggered on NeedCompressionError — summarises context to free budget | `agent_outputs` | Compressed `agent_outputs` content | 800 |

---

## Self-Improving Loop

### What it does
After each evaluation run, the **MetaAgent** reads failure data, identifies the worst-performing scoring dimension, maps it to the responsible agent, and uses the LLM to propose a system prompt rewrite. The rewrite is stored with status `"pending"` in the database.

### What it does NOT do
- **Auto-apply rewrites** — every rewrite requires explicit human approval
- **Guarantee improvement** — LLM-generated prompts are plausible but not guaranteed to help
- **Work without human review** — the loop is intentionally human-in-the-loop

### How to trigger
```bash
# 1. Run eval
curl -X POST http://localhost:8000/eval/run

# 2. Wait for completion, then check results
curl http://localhost:8000/eval/latest

# 3. The meta-agent will have created a prompt rewrite (if scores < 0.7)
#    Review and approve/reject it:
curl -X POST http://localhost:8000/prompt-rewrites/{rewrite_id}/review \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve", "reviewer_note": "Looks good"}'

# 4. Approving triggers a re-eval automatically
```

---

## Known Limitations

- **OpenRouter free models** (llama-3.1-8b) are much weaker than GPT-4 — citation quality suffers
- **FAISS in-memory**: restarts lose the index (fix: persist to disk or use pgvector)
- **Code sandbox is NOT truly isolated** (no container, no seccomp)
- **Eval scoring is heuristic** for ambiguous/adversarial cases — not ground truth
- **Meta-agent prompt improvement is LLM-generated**: plausible but not guaranteed to help
- **No auth on any endpoint**

---

## What I'd Build Next

- Replace FAISS with **pgvector** for persistence
- Add proper **code sandbox** (gVisor or Firecracker)
- Add **human-in-the-loop UI** for reviewing rewrites
- Add **token streaming from OpenRouter** (currently batched per agent)
- Add **prompt injection detection** layer before orchestrator

---

## API Reference

### `POST /query` — Run orchestration pipeline

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is RAG?", "max_budget": 4000}' \
  --no-buffer
```

Returns an SSE stream with event types: `job_created`, `agent_start`, `token`, `tool_call`, `tool_result`, `routing`, `budget_update`, `done`, `error`.

---

### `GET /jobs/{job_id}/trace` — Get ordered event trace

```bash
curl http://localhost:8000/jobs/<job_id>/trace
```

Response:
```json
{
  "job_id": "uuid",
  "query": "What is RAG?",
  "status": "completed",
  "total_latency_ms": 1234.5,
  "total_tokens": 850,
  "events": [
    {
      "timestamp": "2026-05-09T12:00:00+00:00",
      "event_type": "agent_run",
      "agent_id": "decomposition",
      "details": {"latency_ms": 200, "token_count": 150}
    }
  ]
}
```

---

### `POST /eval/run` — Start evaluation run

```bash
curl -X POST http://localhost:8000/eval/run \
  -H "Content-Type: application/json" \
  -d '{"case_ids": null}'
```

Response:
```json
{"run_id": "celery-task-id", "status": "started", "case_count": 15}
```

---

### `GET /eval/latest` — Get latest eval results

```bash
curl http://localhost:8000/eval/latest
```

Response:
```json
{
  "run_id": "uuid",
  "timestamp": "2026-05-09T12:00:00+00:00",
  "total_cases": 15,
  "by_category": {
    "baseline": {"avg_score": 0.75, "cases": [...]},
    "ambiguous": {"avg_score": 0.65, "cases": [...]},
    "adversarial": {"avg_score": 0.55, "cases": [...]}
  },
  "by_dimension": {
    "answer_correctness": {"avg": 0.7, "min": 0.4, "max": 1.0},
    "citation_accuracy": {"avg": 0.6, "min": 0.3, "max": 0.9}
  },
  "delta_vs_previous": {"overall": 0.05, "by_dimension": {...}}
}
```

---

### `POST /prompt-rewrites/{id}/review` — Approve/reject a rewrite

```bash
curl -X POST http://localhost:8000/prompt-rewrites/<rewrite_id>/review \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve", "reviewer_note": "LGTM"}'
```

Response:
```json
{
  "rewrite_id": "uuid",
  "decision": "approve",
  "timestamp": "2026-05-09T12:00:00+00:00",
  "re_eval_triggered": true
}
```

---

### `POST /eval/re-run-failed` — Re-run failed eval cases

```bash
curl -X POST http://localhost:8000/eval/re-run-failed \
  -H "Content-Type: application/json" \
  -d '{"use_approved_prompts": true}'
```

Response:
```json
{
  "new_run_id": "celery-task-id",
  "cases_rerun": 3,
  "performance_delta": {}
}
```

---

## Error Responses

All errors follow this schema:

```json
{
  "error_code": "JOB_NOT_FOUND",
  "message": "No job with that ID",
  "job_id": "uuid-or-null"
}
```

Error codes: `JOB_NOT_FOUND`, `EVAL_NOT_FOUND`, `REWRITE_NOT_FOUND`, `REWRITE_ALREADY_REVIEWED`, `BUDGET_EXCEEDED`, `LLM_UNAVAILABLE`, `TOOL_FAILED`, `INVALID_INPUT`.
