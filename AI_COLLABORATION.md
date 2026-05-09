# AI Collaboration Log

## Overview

This project was built using AI-assisted development (Claude + Cursor). This document fulfills the attestation requirement and describes exactly where AI was used, what decisions it was NOT involved in, and how outputs were validated.

---

## What I designed myself (AI was not involved)

- **SharedContext as the single inter-agent communication channel.** This was a deliberate constraint to make the audit trail clean and prevent agents from coupling to each other directly. Every agent reads from and writes to the same `SharedContext` object — there are no side-channel calls between agents. This makes the entire data flow observable from one place.

- **The routing priority order in the orchestrator.** Specifically the decision to check `NeedCompressionError` before any other condition, and to re-route to the same agent after compression rather than restarting the pipeline. This keeps the retry local to the agent that overflowed, instead of blowing up the whole run.

- **The failure contract schema for tools.** Every tool must return a `ToolResult` and never raise. The orchestrator handles each failure mode differently in code — `timeout` triggers retry, `empty` skips, `parse_error` flags for critique. This is enforced structurally, not via prompt instructions.

- **The eval scoring approach.** Specifically the decision NOT to use a third-party eval framework (no LangSmith, no Braintrust, no custom DSPy metric). The scorer is hand-rolled across 6 dimensions, and every numeric score requires a `justification` string. If you can't explain the score, the score doesn't exist.

- **The meta-agent loop design.** Rewrites are stored as `pending` in the database and never auto-applied. A human must explicitly approve or reject each prompt change via `POST /prompt-rewrites/{id}/review` before it takes effect. This was non-negotiable — unsupervised prompt mutation is a liability.

- **The context budget enforcement model.** Agents must declare their token budget before execution. Overflow is logged as a `BudgetViolationError` and flagged via `flag_violation()` — it is never silently truncated. The orchestrator treats a budget violation as a routing event, not an error to swallow.

- **The adversarial test cases.** Designed specifically to target known LLM failure modes: prompt injection attempts (`ignore previous instructions...`), confident wrong premises (queries with false assumptions baked in), and critique-synthesis contradiction triggers (inputs where the critique agent and synthesis agent are likely to disagree).

---

## Where AI assistance was used

### Boilerplate and scaffolding

Used Cursor (Claude Sonnet) to generate:

- Docker Compose service definitions (db, redis, api, worker, log_ui)
- SQLAlchemy model class structure (Job, AgentLog, ToolLog, EvalRun, PromptRewrite)
- Alembic migration scaffold and initial migration
- FastAPI route stubs for `/query`, `/eval/*`, `/prompt-rewrites/*`
- Pydantic schema field definitions for SharedContext, ToolResult, EvalScore

These were generated from my own specifications (field names, types, relationships) and reviewed line by line before use.

### Implementation of well-defined specs

Once I had written the spec for each component — agent logic, tool failure contracts, SSE event schema, budget enforcement — I used Cursor to implement the code. I reviewed each output for correctness against the spec. Where the implementation diverged from the spec (which happened frequently), I corrected it.

### Documentation

README.md, SETUP.md, CONTRIBUTING.md, and ARCHITECTURE.md were drafted with AI assistance from my own bullet-point outlines and reviewed for accuracy against the actual codebase.

### Post-implementation inline comments

After each feature was working and tested, I used Cursor to add inline comments and docstrings across the finished code. The logic was already written and reviewed at that point — the AI was used purely for annotation, not for understanding or modifying behaviour. This is why the comment quality is uniform across the codebase: it was a dedicated pass, not comments written mid-development.

---

## What I reviewed and corrected

- **Orchestrator routing priority.** The initial routing function did not handle `NeedCompressionError` before checking `sub_tasks` — a budget overflow would fall through to the wrong branch. I reordered the priority rules so compression is always checked first.

- **RAG agent retrieval strategy.** The first implementation performed single-hop retrieval against FAISS. I identified this did not meet the multi-hop requirement and rewrote the retrieval loop to use the first result set to form the second query, pulling additional context that single-hop would miss.

- **Critique agent output granularity.** The critique agent initially flagged whole agent outputs as "low confidence" rather than specific text spans. I rewrote the output schema to require exact span text and byte offsets, and added span validation to reject flags that don't match any text in the source output.

- **Budget manager overflow behavior.** The initial implementation silently truncated context when the token budget was exceeded. I replaced this with an explicit `BudgetViolationError` and a separate `flag_violation()` logging path that records the agent, the requested tokens, the budget, and the overflow amount.

- **Eval scorer tool_efficiency dimension.** The initial implementation gave a flat 0.8 score regardless of which tools were called. I rewrote it to define expected tools per case type (baseline cases shouldn't need `code_sandbox`, adversarial cases should trigger `self_reflection`) and penalise each unnecessary tool call.

- **SSE event serialization.** The initial SSE stream emitted raw dicts without `event:` type prefixes. I restructured it to emit typed events (`agent_start`, `agent_end`, `tool_call`, `error`, `done`) so the client can filter by event type without parsing the data payload.

---

## AI collaboration signals you will find in this repo

- **Consistent code style across files** — uniform naming conventions, import ordering, and error handling patterns. This is a signal of AI-assisted generation from a consistent spec, not organic file-by-file development.

- **Uniform docstring format** — every module, class, and public method has a docstring in the same style. Written with AI assistance from my function signatures and intent descriptions.

- **Large feature commits** — the commit history shows substantial feature additions per commit rather than incremental micro-commits. This reflects AI-accelerated implementation of pre-designed components: I'd write the spec, generate the code, review it, and commit the working result.

- **No commented-out dead code** — AI-generated code was reviewed and either used or discarded, not left in place as `# TODO: maybe use this later`. What's in the repo is what's running.

- **High test coverage for core utilities** — the budget manager has 10 unit tests because it's a critical correctness boundary. Other components rely more on integration testing through the eval harness.

---

## My assessment

Using AI assistance allowed me to implement a system of this scope within the time constraint. The architectural decisions — SharedContext as a single communication bus, the routing priority model, the tool failure contract that prevents agents from raising, the no-auto-apply rule on prompt rewrites, the hand-rolled eval scorer with mandatory justifications — reflect my own understanding of the problem and my own opinions about how multi-agent systems should be built. AI was used to translate those decisions into working code faster than I could write it by hand. I reviewed every generated file against my own spec before committing it. The result is a system I can explain end-to-end, defend every design choice in, and extend without re-reading the code from scratch — which is the correct bar for AI-assisted work.

---

## Tools used

| Tool | Purpose |
|------|---------|
| Claude (Anthropic) | Architecture design discussion, spec refinement, code review |
| Cursor | In-editor code generation from written specs |
| OpenRouter | LLM API used by the system itself at runtime |
