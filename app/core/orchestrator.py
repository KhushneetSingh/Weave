"""
LangGraph orchestrator — StateGraph with dynamic routing.

Nodes: decomposition, rag, critique, synthesis, compression.
Routing function decides the next agent based on SharedContext state.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.base import NeedCompressionError
from app.agents.compression import CompressionAgent
from app.agents.critique import CritiqueAgent
from app.agents.decomposition import DecompositionAgent
from app.agents.rag import RAGAgent
from app.agents.synthesis import SynthesisAgent
from app.core.budget_manager import ContextBudgetManager
from app.schemas.context import RoutingDecision, SharedContext


# ── Graph state ──────────────────────────────────────────────────────────────

class GraphState(TypedDict):
    context: dict  # SharedContext serialized as dict
    budget_manager: Any
    event_queue: Any
    compression_pending: bool


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_context(state: GraphState) -> SharedContext:
    return SharedContext(**state["context"])


def _save_context(state: GraphState, ctx: SharedContext) -> GraphState:
    state["context"] = ctx.model_dump()
    return state


async def _emit_routing(
    event_queue: asyncio.Queue | None,
    from_agent: str | None,
    to_agent: str,
    justification: str,
) -> None:
    if event_queue:
        await event_queue.put({
            "type": "routing",
            "from": from_agent or "START",
            "to": to_agent,
            "justification": justification,
        })


def _log_routing(
    ctx: SharedContext,
    from_agent: str | None,
    to_agent: str,
    justification: str,
) -> None:
    ctx.routing_log.append(
        RoutingDecision(
            from_agent=from_agent,
            to_agent=to_agent,
            justification=justification,
            timestamp=datetime.now(timezone.utc),
        )
    )


# ── Node factories ──────────────────────────────────────────────────────────

async def _run_agent(agent, state: GraphState) -> GraphState:
    ctx = _to_context(state)
    bm = state["budget_manager"]
    eq = state["event_queue"]

    try:
        await agent.run(ctx, bm, eq)
        state = _save_context(state, ctx)
        state["compression_pending"] = False
    except NeedCompressionError:
        state["compression_pending"] = True
        state = _save_context(state, ctx)

    return state


async def decomposition_node(state: GraphState) -> GraphState:
    return await _run_agent(DecompositionAgent(), state)


async def rag_node(state: GraphState) -> GraphState:
    return await _run_agent(RAGAgent(), state)


async def critique_node(state: GraphState) -> GraphState:
    return await _run_agent(CritiqueAgent(), state)


async def synthesis_node(state: GraphState) -> GraphState:
    return await _run_agent(SynthesisAgent(), state)


async def compression_node(state: GraphState) -> GraphState:
    state["compression_pending"] = False
    return await _run_agent(CompressionAgent(), state)


# ── Routing ──────────────────────────────────────────────────────────────────

AGENT_NODES = {
    "decomposition",
    "rag",
    "critique",
    "synthesis",
    "compression",
}


def route(state: GraphState) -> str:
    """Dynamic routing — the ONLY place agent order is decided."""
    ctx_data = state["context"]
    sub_tasks = ctx_data.get("sub_tasks", [])
    agent_outputs = ctx_data.get("agent_outputs", {})
    compression_pending = state.get("compression_pending", False)

    if compression_pending:
        dest = "compression"
        justification = "Budget exceeded — compression needed before resuming."
    elif not sub_tasks:
        dest = "decomposition"
        justification = "No sub-tasks yet — need decomposition."
    elif "rag" not in agent_outputs:
        dest = "rag"
        justification = "Sub-tasks exist but no RAG output — run retrieval."
    elif "critique" not in agent_outputs:
        dest = "critique"
        justification = "RAG done, no critique yet — run critique."
    elif "synthesis" not in agent_outputs:
        dest = "synthesis"
        justification = "Critique done, no synthesis — run synthesis."
    else:
        dest = END
        justification = "All agents complete."

    # Log routing decision into context
    ctx = _to_context(state)
    last_agent = None
    if ctx.routing_log:
        last_agent = ctx.routing_log[-1].to_agent

    if dest != END:
        _log_routing(ctx, last_agent, dest, justification)
        state["context"] = ctx.model_dump()

        # Emit routing event (fire-and-forget via sync check)
        eq = state.get("event_queue")
        if eq:
            try:
                eq.put_nowait({
                    "type": "routing",
                    "from": last_agent or "START",
                    "to": dest,
                    "justification": justification,
                })
            except Exception:
                pass

    return dest


# ── Build graph ──────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Construct and compile the orchestration graph."""
    graph = StateGraph(GraphState)

    # Add nodes
    graph.add_node("decomposition", decomposition_node)
    graph.add_node("rag", rag_node)
    graph.add_node("critique", critique_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("compression", compression_node)

    # Entry point → router
    graph.set_conditional_entry_point(route)

    # After each node → route again
    for node_name in AGENT_NODES:
        graph.add_conditional_edges(node_name, route)

    return graph.compile()


# ── Public runner ────────────────────────────────────────────────────────────

async def run_pipeline(
    query: str,
    job_id: str,
    max_budget: int = 4000,
    event_queue: asyncio.Queue | None = None,
) -> SharedContext:
    """Run the full orchestration pipeline and return the final SharedContext."""
    ctx = SharedContext(job_id=job_id, query=query)
    bm = ContextBudgetManager(max_tokens=max_budget)

    initial_state: GraphState = {
        "context": ctx.model_dump(),
        "budget_manager": bm,
        "event_queue": event_queue,
        "compression_pending": False,
    }

    compiled = build_graph()
    final_state = await compiled.ainvoke(initial_state)

    return SharedContext(**final_state["context"])
