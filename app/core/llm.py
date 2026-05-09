"""
LLM helper — calls OpenRouter via the openai async client.

Falls back to OPENROUTER_FALLBACK_MODEL on RateLimitError or APIError.
Optionally streams tokens to an asyncio.Queue for SSE.
Returns (content, token_count) tuple.
"""

from __future__ import annotations

import asyncio
from typing import Any

import tiktoken
from openai import APIError, RateLimitError

from app.config import settings

# Cache the tiktoken encoding at module level
_encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Return the token count for *text* using cl100k_base."""
    return len(_encoding.encode(text))


async def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.2,
    event_queue: asyncio.Queue | None = None,
    agent_id: str | None = None,
) -> tuple[str, int]:
    """
    Call OpenRouter and return ``(assistant_content, token_count)``.

    Parameters
    ----------
    messages : list[dict]
        OpenAI-style messages list.
    model : str | None
        Model to use.  Defaults to ``settings.openrouter_model``.
    temperature : float
        Sampling temperature.
    event_queue : asyncio.Queue | None
        When provided, streams each token chunk as a
        ``{"type": "token", "agent_id": ..., "content": ...}`` event.
    agent_id : str | None
        Used in token events when *event_queue* is given.

    Returns
    -------
    tuple[str, int]
        ``(content, token_count)``
    """
    primary_model = model or settings.openrouter_model
    fallback_model = settings.openrouter_fallback_model

    for attempt_model in (primary_model, fallback_model):
        try:
            content = await _call(
                messages=messages,
                model=attempt_model,
                temperature=temperature,
                event_queue=event_queue,
                agent_id=agent_id,
            )
            token_count = count_tokens(content)
            return content, token_count

        except (RateLimitError, APIError) as exc:
            if attempt_model == fallback_model:
                # Both models failed — re-raise
                raise
            # First attempt failed — fall through to fallback
            continue

    # Should never reach here, but satisfy the type checker
    raise APIError("All models failed")


async def _call(
    messages: list[dict],
    model: str,
    temperature: float,
    event_queue: asyncio.Queue | None,
    agent_id: str | None,
) -> str:
    """Execute a single OpenRouter chat completion (streaming or not)."""
    client = settings.openrouter_client()

    if event_queue is not None:
        # ── Streaming path ────────────────────────────────────────────
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        chunks: list[str] = []
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                chunks.append(delta.content)
                await event_queue.put(
                    {
                        "type": "token",
                        "agent_id": agent_id or "",
                        "content": delta.content,
                    }
                )
        return "".join(chunks)

    else:
        # ── Non-streaming path ────────────────────────────────────────
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=False,
        )
        return response.choices[0].message.content or ""
