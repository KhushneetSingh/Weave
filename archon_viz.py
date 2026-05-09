"""
archon_viz.py — Weave Architecture Visualizer (terminal only)

Requirements:
    pip install rich networkx

Run:
    python archon_viz.py
"""

import networkx as nx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich import box

# ─── Graph data ────────────────────────────────────────────────────────────────

NODES = {
    "client":          ("Client",        "external"),
    "api":             ("FastAPI",       "api"),
    "orchestrator":    ("Orchestrator",  "core"),
    "decomposition":   ("Decomposition", "agent"),
    "rag":             ("RAG",           "agent"),
    "critique":        ("Critique",      "agent"),
    "synthesis":       ("Synthesis",     "agent"),
    "meta":            ("Meta-agent",    "agent"),
    "compression":     ("Compression",   "agent"),
    "web_search":      ("web_search",    "tool"),
    "code_sandbox":    ("code_sandbox",  "tool"),
    "sql_lookup":      ("sql_lookup",    "tool"),
    "self_reflection": ("self_reflect",  "tool"),
    "postgres":        ("PostgreSQL",    "storage"),
    "faiss":           ("FAISS",         "storage"),
    "redis":           ("Redis",         "storage"),
    "openrouter":      ("OpenRouter",    "llm"),
    "celery":          ("Celery",        "api"),
}

EDGES = [
    ("client", "api"), ("api", "orchestrator"), ("api", "celery"),
    ("api", "postgres"), ("api", "redis"),
    ("orchestrator", "decomposition"), ("orchestrator", "rag"),
    ("orchestrator", "critique"), ("orchestrator", "synthesis"),
    ("orchestrator", "meta"), ("orchestrator", "compression"),
    ("decomposition", "web_search"), ("decomposition", "sql_lookup"), ("decomposition", "openrouter"),
    ("rag", "web_search"), ("rag", "faiss"), ("rag", "openrouter"),
    ("critique", "self_reflection"), ("critique", "openrouter"),
    ("synthesis", "self_reflection"), ("synthesis", "openrouter"),
    ("meta", "openrouter"), ("sql_lookup", "postgres"),
    ("celery", "postgres"), ("celery", "redis"),
]

GROUP_COLORS = {
    "external": "bright_blue",
    "api":      "cyan",
    "core":     "bright_yellow",
    "agent":    "medium_purple1",
    "tool":     "green3",
    "storage":  "grey70",
    "llm":      "orange1",
}

console = Console()


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _styled_label(node_id: str) -> str:
    """Return a Rich-markup label for a node, colored by its group."""
    label, group = NODES[node_id]
    color = GROUP_COLORS.get(group, "white")
    return f"[{color}]{label}[/{color}] [dim]({group})[/dim]"


# ─── 1. Header ────────────────────────────────────────────────────────────────

def render_header() -> None:
    header_text = Text.from_markup(
        "[bold bright_yellow]W E A V E[/bold bright_yellow]\n"
        "[dim]Multi-agent orchestration system with budget-aware routing,\n"
        "tool-level failure contracts, and provenance tracking.[/dim]"
    )
    console.print()
    console.print(
        Panel(
            header_text,
            border_style="bright_yellow",
            box=box.DOUBLE_EDGE,
            padding=(1, 4),
            subtitle="[dim italic]archon_viz · terminal architecture viewer[/dim italic]",
        )
    )
    console.print()


# ─── 2. Graph (BFS tree) ──────────────────────────────────────────────────────

def render_graph() -> None:
    console.rule("[bold]Node Connections (BFS from client)[/bold]", style="bright_yellow")
    console.print()

    G = nx.DiGraph()
    G.add_nodes_from(NODES.keys())
    G.add_edges_from(EDGES)

    tree = Tree(_styled_label("client"))
    visited: set[str] = {"client"}

    # BFS queue: each item is (node_id, parent_tree_branch)
    queue: list[tuple[str, Tree]] = []

    # Seed queue with direct successors of "client"
    for neighbor in G.successors("client"):
        queue.append((neighbor, tree))

    while queue:
        node, parent_branch = queue.pop(0)

        if node in visited:
            parent_branch.add(f"{_styled_label(node)} [dim](already shown)[/dim]")
            continue

        visited.add(node)
        branch = parent_branch.add(_styled_label(node))

        for neighbor in G.successors(node):
            queue.append((neighbor, branch))

    console.print(tree)
    console.print()


# ─── 3. Agent table ───────────────────────────────────────────────────────────

def render_agents() -> None:
    console.rule("[bold]Agent Contracts[/bold]", style="medium_purple1")
    console.print()

    table = Table(
        box=box.ROUNDED,
        border_style="medium_purple1",
        header_style="bold medium_purple1",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Agent", style="bold", min_width=15)
    table.add_column("Max budget", justify="right")
    table.add_column("Reads")
    table.add_column("Writes")
    table.add_column("Output format")

    rows = [
        ("decomposition", "1 200 tok", "query",
         "sub_tasks[]", "JSON SubTask DAG"),
        ("rag", "2 000 tok", "sub_tasks, FAISS",
         "agent_outputs['rag'], citations[]", "JSON answer+citations"),
        ("critique", "1 500 tok", "all agent_outputs",
         "contradictions[], flagged_spans", "JSON span-level flags"),
        ("synthesis", "1 500 tok", "agent_outputs, contradictions",
         "provenance_map", "JSON answer+provenance"),
        ("compression", "800 tok", "full SharedContext",
         "compressed outputs (70 % target)", "lossless struct, lossy text"),
        ("meta", "1 000 tok", "EvalRun from DB",
         "PromptRewrite (pending)", "JSON diff+justification"),
    ]

    for agent, budget, reads, writes, fmt in rows:
        color = GROUP_COLORS["agent"]
        table.add_row(
            f"[{color}]{agent}[/{color}]",
            f"[bold]{budget}[/bold]",
            reads,
            writes,
            f"[dim]{fmt}[/dim]",
        )

    console.print(table)
    console.print()


# ─── 4. Tool failure contracts ─────────────────────────────────────────────────

def render_tools() -> None:
    console.rule("[bold]Tool Failure Contracts[/bold]", style="green3")
    console.print()

    table = Table(
        box=box.ROUNDED,
        border_style="green3",
        header_style="bold green3",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Tool", style="bold", min_width=16)
    table.add_column("Input")
    table.add_column("on success")
    table.add_column("on timeout")
    table.add_column("on empty")
    table.add_column("on malformed")
    table.add_column("retries", justify="center")

    rows = [
        ("web_search",      "{query}",   "[{url,snippet,score}]",
         "status=timeout", "status=empty", "status=parse_error", "×2"),
        ("code_sandbox",    "{code}",    "{stdout,stderr,exit}",
         "status=timeout", "exit=0,out=''", "status=error",      "×2"),
        ("sql_lookup",      "{question}", "{rows,query_used}",
         "status=timeout", "rows=[]",      "status=parse_error", "×2"),
        ("self_reflection", "{outputs}", "{contradictions:[]}",
         "status=timeout", "status=empty", "status=error",       "×2"),
    ]

    for tool, inp, success, timeout, empty, malformed, retries in rows:
        color = GROUP_COLORS["tool"]
        table.add_row(
            f"[{color}]{tool}[/{color}]",
            f"[dim]{inp}[/dim]",
            success,
            f"[yellow]{timeout}[/yellow]",
            f"[yellow]{empty}[/yellow]",
            f"[red]{malformed}[/red]",
            f"[bold]{retries}[/bold]",
        )

    console.print(table)
    console.print()


# ─── 5. Data flow ─────────────────────────────────────────────────────────────

def render_flow() -> None:
    console.rule("[bold]Query Lifecycle (data flow)[/bold]", style="cyan")
    console.print()

    root = Tree("[bold cyan]POST /query[/bold cyan]")

    # API step
    api = root.add("[cyan]API:[/cyan] create Job in Postgres, open SSE stream")

    # Orchestrator step
    orch = root.add("[bright_yellow]Orchestrator:[/bright_yellow] init SharedContext + BudgetManager")

    # Routing function
    routing = root.add("[bright_yellow]Routing fn[/bright_yellow] [dim](priority order)[/dim]")
    routing.add("[medium_purple1]NeedCompressionError[/medium_purple1] → [medium_purple1]compression[/medium_purple1]")
    routing.add("no sub_tasks → [medium_purple1]decomposition[/medium_purple1]")
    routing.add("no rag output → [medium_purple1]rag[/medium_purple1]")
    routing.add("no critique → [medium_purple1]critique[/medium_purple1]")
    routing.add("no synthesis → [medium_purple1]synthesis[/medium_purple1]")
    routing.add("[bold green3]synthesis done → END[/bold green3]")

    # Each agent
    agent = root.add("[medium_purple1]Each agent[/medium_purple1]")
    agent.add("check_budget() → [red]False[/red] → [medium_purple1]NeedCompressionError[/medium_purple1]")
    agent.add("assemble context from [bright_yellow]SharedContext[/bright_yellow]")
    agent.add("call [orange1]OpenRouter[/orange1]")
    agent.add("write result to [bright_yellow]SharedContext[/bright_yellow]")

    # Each tool call
    tool = root.add("[green3]Each tool call[/green3]")
    tool.add("[dim]asyncio.wait_for(timeout=10)[/dim]")
    tool.add("failure → [yellow]ToolResult(status=...)[/yellow]")
    tool.add("retry up to [bold]×2[/bold], each logged to DB")

    # SSE events
    sse = root.add("[cyan]SSE events →[/cyan] job_created, agent_start, token,")
    sse.add("[dim]tool_call, tool_result, routing,[/dim]")
    sse.add("[dim]budget_update, done, error[/dim]")

    console.print(root)
    console.print()


# ─── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    render_header()
    render_graph()
    render_agents()
    render_tools()
    render_flow()
