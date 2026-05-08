"""
BudgetManager — token-budget enforcement for multi-agent LLM calls.

Responsibilities:
  1. Check whether a proposed call fits within the remaining token budget.
  2. Record actual token usage after a successful LLM response.
  3. Trigger a fallback model when the primary model is unavailable.
  4. Provide a rough token estimate from raw text (word-count heuristic)
     before the real API count is known.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.schemas.context import AgentContext

logger = logging.getLogger(__name__)

# Conservative chars-per-token ratio used for pre-call estimation.
# Real tokenisers vary; this keeps us safely under budget.
_CHARS_PER_TOKEN: float = 4.0


class BudgetExceededError(Exception):
    """Raised when a proposed LLM call would exceed the job's token budget."""

    def __init__(self, requested: int, remaining: int) -> None:
        self.requested = requested
        self.remaining = remaining
        super().__init__(
            f"Token budget exceeded: requested {requested}, only {remaining} remaining."
        )


@dataclass
class BudgetManager:
    """
    Stateless helper that operates on an :class:`AgentContext`.

    Usage::

        manager = BudgetManager(max_tokens=4000)
        manager.check_budget(context, estimated_tokens=200)   # raises if over
        # … make LLM call …
        manager.record_usage(context, prompt_tokens=180, completion_tokens=120)
    """

    max_tokens: int = 4000
    # Minimum tokens that must remain before a call is allowed.
    reserve_tokens: int = 50
    _fallback_triggered: bool = field(default=False, init=False, repr=False)

    # ── Public API ────────────────────────────────────────────────────────────

    def estimate_tokens(self, text: str) -> int:
        """
        Rough token estimate based on character count.

        Uses a 4 chars-per-token heuristic — sufficient for budget gating
        before the real API count is available.
        """
        if not text:
            return 0
        return max(1, int(len(text) / _CHARS_PER_TOKEN))

    def check_budget(self, context: AgentContext, estimated_tokens: int) -> None:
        """
        Assert the context has enough headroom for *estimated_tokens* more tokens.

        Raises :class:`BudgetExceededError` if the call would exceed the budget.
        """
        effective_limit = context.token_budget - self.reserve_tokens
        available = effective_limit - context.tokens_used
        if estimated_tokens > available:
            logger.warning(
                "Budget check failed for agent=%s job=%s: "
                "requested=%d available=%d budget=%d used=%d",
                context.agent_name,
                context.job_id,
                estimated_tokens,
                available,
                context.token_budget,
                context.tokens_used,
            )
            raise BudgetExceededError(requested=estimated_tokens, remaining=available)

        logger.debug(
            "Budget OK for agent=%s: requested=%d available=%d",
            context.agent_name,
            estimated_tokens,
            available,
        )

    def record_usage(
        self,
        context: AgentContext,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> int:
        """
        Update *context.tokens_used* with actual token counts from the API response.

        Returns the new running total.
        """
        total = prompt_tokens + completion_tokens
        context.tokens_used += total
        logger.info(
            "Tokens used — agent=%s job=%s prompt=%d completion=%d total_so_far=%d/%d",
            context.agent_name,
            context.job_id,
            prompt_tokens,
            completion_tokens,
            context.tokens_used,
            context.token_budget,
        )
        return context.tokens_used

    def should_use_fallback(self, context: AgentContext, threshold: float = 0.9) -> bool:
        """
        Return *True* when token usage exceeds *threshold* fraction of the budget.

        Callers can use this to swap to the cheaper/smaller fallback model
        before hitting the hard limit.
        """
        ratio = context.tokens_used / max(context.token_budget, 1)
        if ratio >= threshold:
            if not self._fallback_triggered:
                logger.warning(
                    "Fallback threshold reached (%.0f%%) for agent=%s job=%s",
                    ratio * 100,
                    context.agent_name,
                    context.job_id,
                )
                self._fallback_triggered = True
            return True
        return False

    def usage_summary(self, context: AgentContext) -> dict:
        """Return a JSON-serialisable summary of the current budget state."""
        return {
            "job_id": str(context.job_id),
            "agent_name": context.agent_name,
            "token_budget": context.token_budget,
            "tokens_used": context.tokens_used,
            "tokens_remaining": context.tokens_remaining,
            "utilisation_pct": round(
                context.tokens_used / max(context.token_budget, 1) * 100, 2
            ),
            "fallback_triggered": self._fallback_triggered,
        }
