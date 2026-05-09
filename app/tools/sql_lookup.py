"""
SQLLookupTool — natural-language to SQL via LLM, executed against Postgres.

Tables: products(id, name, price, category), orders(id, product_id, quantity, created_at).
Only SELECT statements are allowed.
"""

from __future__ import annotations

import re

import asyncpg

from app.config import settings
from app.core.llm import chat
from app.schemas.tools import ToolResult
from app.tools.base import BaseTool

_NL_TO_SQL_PROMPT = """\
You are a SQL assistant. Convert the user's natural-language question into a
PostgreSQL SELECT query.

Available tables:
  products(id SERIAL PRIMARY KEY, name VARCHAR, price FLOAT, category VARCHAR)
  orders(id SERIAL PRIMARY KEY, product_id INT REFERENCES products(id), quantity INT, created_at TIMESTAMP)

Rules:
- ONLY produce SELECT statements — never INSERT, UPDATE, DELETE, DROP, etc.
- Return ONLY the raw SQL query, no explanation, no markdown fences.
- End the query with a semicolon.
"""


class SQLLookupTool(BaseTool):
    """Translate natural language to SQL and execute against Postgres."""

    name: str = "sql_lookup"
    timeout_seconds: float = 15.0

    async def _execute(self, input: dict) -> ToolResult:
        question: str = input.get("question", "").strip()
        if not question:
            return self.on_empty()

        # Step 1 — LLM converts NL → SQL
        messages = [
            {"role": "system", "content": _NL_TO_SQL_PROMPT},
            {"role": "user", "content": question},
        ]
        try:
            sql_text, _ = await chat(messages, temperature=0.0)
        except Exception as exc:
            return self.on_malformed(f"LLM SQL generation failed: {exc}")

        sql_text = sql_text.strip().rstrip(";").strip() + ";"

        # Validate: only SELECT allowed
        if not re.match(r"^\s*SELECT\b", sql_text, re.IGNORECASE):
            return self.on_malformed(f"Non-SELECT query generated: {sql_text[:120]}")

        # Extra safety: reject DDL / DML keywords
        forbidden = re.compile(
            r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
            re.IGNORECASE,
        )
        if forbidden.search(sql_text):
            return self.on_malformed(f"Forbidden SQL keyword detected in: {sql_text[:120]}")

        # Step 2 — Execute against Postgres via asyncpg
        dsn = (
            f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
            f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        )
        try:
            conn = await asyncpg.connect(dsn)
            try:
                rows = await conn.fetch(sql_text)
                result_rows = [dict(row) for row in rows]
                return ToolResult(
                    tool_name=self.name,
                    status="success",
                    data={
                        "rows": result_rows,
                        "query_used": sql_text,
                        "row_count": len(result_rows),
                    },
                )
            finally:
                await conn.close()
        except Exception as exc:
            return self.on_malformed(f"SQL execution error: {exc}")
