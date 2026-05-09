"""
Log Query UI — separate FastAPI app for viewing job traces.

Serves on port 8080. Queries AgentLog + ToolLog from Postgres and renders
a dark-themed HTML table.
"""

import os

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse

app = FastAPI(title="Weave — Log Viewer", version="0.1.0")

# ── Database connection (direct asyncpg, no dependency on app package) ───────

DATABASE_URL = (
    f"postgresql+asyncpg://"
    f"{os.environ.get('POSTGRES_USER', 'megaai')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', 'megaai')}@"
    f"{os.environ.get('POSTGRES_HOST', 'db')}:"
    f"{os.environ.get('POSTGRES_PORT', '5432')}/"
    f"{os.environ.get('POSTGRES_DB', 'megaai')}"
)

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# ── HTML templates (inline — no external deps) ───────────────────────────────

_BASE_STYLE = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #0d1117;
    color: #c9d1d9;
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 13px;
    padding: 24px;
}
h1 {
    font-size: 20px;
    color: #58a6ff;
    margin-bottom: 16px;
    font-weight: 600;
}
h2 {
    font-size: 15px;
    color: #8b949e;
    margin-bottom: 12px;
}
a { color: #58a6ff; text-decoration: none; }
a:hover { text-decoration: underline; }
form {
    margin-bottom: 24px;
    display: flex;
    gap: 8px;
    align-items: center;
}
input[type="text"] {
    background: #161b22;
    border: 1px solid #30363d;
    color: #c9d1d9;
    padding: 8px 12px;
    font-family: inherit;
    font-size: 13px;
    border-radius: 6px;
    width: 400px;
}
input[type="text"]:focus {
    outline: none;
    border-color: #58a6ff;
}
button {
    background: #238636;
    color: #fff;
    border: none;
    padding: 8px 16px;
    font-family: inherit;
    font-size: 13px;
    border-radius: 6px;
    cursor: pointer;
}
button:hover { background: #2ea043; }
table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 12px;
}
th {
    text-align: left;
    padding: 8px 12px;
    background: #161b22;
    color: #8b949e;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid #30363d;
}
td {
    padding: 6px 12px;
    border-bottom: 1px solid #21262d;
    vertical-align: top;
    max-width: 400px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
tr:hover td { background: #161b22; }
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
}
.badge-agent { background: #1f3a5f; color: #58a6ff; }
.badge-tool  { background: #3b2e08; color: #d29922; }
.badge-warn  { background: #5a1e02; color: #f85149; }
.no-data {
    color: #484f58;
    padding: 24px;
    text-align: center;
}
.meta {
    color: #8b949e;
    margin-bottom: 8px;
    font-size: 12px;
}
"""

_INDEX_HTML = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Weave — Log Viewer</title>
    <style>{_BASE_STYLE}</style>
</head>
<body>
    <h1>🔍 Weave Log Viewer</h1>
    <form action="/trace" method="get">
        <input type="text" name="job_id" placeholder="Enter job_id (UUID)" required>
        <button type="submit">Trace</button>
    </form>
    <p class="meta">Enter a job ID to view its agent and tool execution trace.</p>
</body>
</html>
"""


def _trace_html(job_id: str, events: list[dict], error: str | None = None) -> str:
    if error:
        return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Weave — Trace Error</title>
    <style>{_BASE_STYLE}</style>
</head>
<body>
    <h1>🔍 Weave Log Viewer</h1>
    <p><a href="/">← Back</a></p>
    <div class="no-data">⚠️ {error}</div>
</body>
</html>
"""

    if not events:
        rows = '<tr><td colspan="6" class="no-data">No events found for this job.</td></tr>'
    else:
        row_parts = []
        for ev in events:
            ts = ev.get("timestamp", "—")
            agent = ev.get("agent_id", "—")
            etype = ev.get("event_type", "—")
            latency = ev.get("latency_ms", "—")
            tokens = ev.get("token_count", "—")
            violation = ev.get("policy_violation", "")

            # Badge for event type
            if etype.startswith("tool_call"):
                badge_cls = "badge-tool"
            elif violation:
                badge_cls = "badge-warn"
            else:
                badge_cls = "badge-agent"

            violation_cell = f'<span class="badge badge-warn">{violation}</span>' if violation else "—"

            row_parts.append(
                f"<tr>"
                f"<td>{ts}</td>"
                f"<td>{agent}</td>"
                f'<td><span class="badge {badge_cls}">{etype}</span></td>'
                f"<td>{latency}</td>"
                f"<td>{tokens}</td>"
                f"<td>{violation_cell}</td>"
                f"</tr>"
            )
        rows = "\n".join(row_parts)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Weave — Trace {job_id[:8]}...</title>
    <style>{_BASE_STYLE}</style>
</head>
<body>
    <h1>🔍 Weave Log Viewer</h1>
    <p><a href="/">← Back</a></p>
    <h2>Job: {job_id}</h2>
    <p class="meta">{len(events)} event(s)</p>
    <table>
        <thead>
            <tr>
                <th>Timestamp</th>
                <th>Agent ID</th>
                <th>Event Type</th>
                <th>Latency (ms)</th>
                <th>Token Count</th>
                <th>Policy Violation</th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
</body>
</html>
"""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Render the job_id input form."""
    return HTMLResponse(content=_INDEX_HTML)


@app.get("/trace", response_class=HTMLResponse)
async def trace(job_id: str = Query(..., description="Job UUID")):
    """Query AgentLog + ToolLog and render an HTML trace table."""
    from sqlalchemy import text

    try:
        async with SessionLocal() as session:
            # Query agent_logs
            agent_rows = await session.execute(
                text(
                    "SELECT timestamp, agent_id, event_type, latency_ms, token_count, policy_violation "
                    "FROM agent_logs WHERE job_id = :jid ORDER BY timestamp"
                ),
                {"jid": job_id},
            )
            agent_events = [
                {
                    "timestamp": str(r.timestamp),
                    "agent_id": r.agent_id,
                    "event_type": r.event_type,
                    "latency_ms": r.latency_ms,
                    "token_count": r.token_count,
                    "policy_violation": r.policy_violation,
                }
                for r in agent_rows
            ]

            # Query tool_logs
            tool_rows = await session.execute(
                text(
                    "SELECT timestamp, agent_id, tool_name, status, latency_ms "
                    "FROM tool_logs WHERE job_id = :jid ORDER BY timestamp"
                ),
                {"jid": job_id},
            )
            tool_events = [
                {
                    "timestamp": str(r.timestamp),
                    "agent_id": r.agent_id,
                    "event_type": f"tool_call:{r.tool_name}",
                    "latency_ms": r.latency_ms,
                    "token_count": "—",
                    "policy_violation": "",
                }
                for r in tool_rows
            ]

        # Merge and sort
        all_events = agent_events + tool_events
        all_events.sort(key=lambda e: e["timestamp"])

        return HTMLResponse(content=_trace_html(job_id, all_events))

    except Exception as exc:
        return HTMLResponse(
            content=_trace_html(job_id, [], error=f"Database error: {exc}"),
            status_code=500,
        )
