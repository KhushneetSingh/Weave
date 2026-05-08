"""
Tests for BudgetManager.

Run with:
    pytest tests/test_budget_manager.py -v
"""

import uuid

import pytest

from app.core.budget_manager import BudgetExceededError, BudgetManager
from app.schemas.context import AgentContext, Message, MessageRole


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_context(budget: int = 1000, used: int = 0) -> AgentContext:
    ctx = AgentContext(
        job_id=uuid.uuid4(),
        agent_name="test-agent",
        token_budget=budget,
        tokens_used=used,
    )
    return ctx


# ── estimate_tokens ───────────────────────────────────────────────────────────

class TestEstimateTokens:
    def test_empty_string_returns_zero(self):
        manager = BudgetManager()
        assert manager.estimate_tokens("") == 0

    def test_positive_result_for_nonempty_string(self):
        manager = BudgetManager()
        result = manager.estimate_tokens("Hello, world!")
        assert result >= 1

    def test_longer_text_gives_larger_estimate(self):
        manager = BudgetManager()
        short = manager.estimate_tokens("hi")
        long_ = manager.estimate_tokens("hi " * 100)
        assert long_ > short

    def test_approximation_within_reasonable_range(self):
        manager = BudgetManager()
        # 400 chars ~ 100 tokens at 4 chars/token
        result = manager.estimate_tokens("a" * 400)
        assert 80 <= result <= 130


# ── check_budget ──────────────────────────────────────────────────────────────

class TestCheckBudget:
    def test_passes_when_tokens_available(self):
        manager = BudgetManager(max_tokens=1000, reserve_tokens=50)
        ctx = make_context(budget=1000, used=0)
        # Should not raise
        manager.check_budget(ctx, estimated_tokens=900)

    def test_raises_when_exceeds_budget(self):
        manager = BudgetManager(max_tokens=1000, reserve_tokens=50)
        ctx = make_context(budget=1000, used=0)
        with pytest.raises(BudgetExceededError) as exc_info:
            manager.check_budget(ctx, estimated_tokens=1000)
        assert exc_info.value.requested == 1000

    def test_raises_when_already_near_limit(self):
        manager = BudgetManager(max_tokens=1000, reserve_tokens=50)
        ctx = make_context(budget=1000, used=960)
        with pytest.raises(BudgetExceededError):
            manager.check_budget(ctx, estimated_tokens=100)

    def test_reserve_tokens_respected(self):
        """Even if tokens_used == 0, the reserve must be kept back."""
        manager = BudgetManager(max_tokens=1000, reserve_tokens=100)
        ctx = make_context(budget=1000, used=0)
        with pytest.raises(BudgetExceededError):
            manager.check_budget(ctx, estimated_tokens=950)

    def test_exact_boundary_allowed(self):
        """Requesting exactly (budget - reserve - used) tokens should pass."""
        manager = BudgetManager(max_tokens=1000, reserve_tokens=50)
        ctx = make_context(budget=1000, used=0)
        # 1000 - 50 - 0 = 950 available
        manager.check_budget(ctx, estimated_tokens=950)  # should not raise


# ── record_usage ──────────────────────────────────────────────────────────────

class TestRecordUsage:
    def test_updates_context_tokens_used(self):
        manager = BudgetManager()
        ctx = make_context(budget=1000, used=0)
        total = manager.record_usage(ctx, prompt_tokens=200, completion_tokens=100)
        assert total == 300
        assert ctx.tokens_used == 300

    def test_accumulates_across_calls(self):
        manager = BudgetManager()
        ctx = make_context(budget=2000, used=0)
        manager.record_usage(ctx, prompt_tokens=100, completion_tokens=50)
        manager.record_usage(ctx, prompt_tokens=200, completion_tokens=80)
        assert ctx.tokens_used == 430

    def test_returns_running_total(self):
        manager = BudgetManager()
        ctx = make_context(budget=1000, used=500)
        returned = manager.record_usage(ctx, prompt_tokens=50, completion_tokens=50)
        assert returned == 600
        assert ctx.tokens_used == 600


# ── should_use_fallback ───────────────────────────────────────────────────────

class TestShouldUseFallback:
    def test_false_below_threshold(self):
        manager = BudgetManager()
        ctx = make_context(budget=1000, used=800)  # 80% — below default 90%
        assert manager.should_use_fallback(ctx, threshold=0.9) is False

    def test_true_at_threshold(self):
        manager = BudgetManager()
        ctx = make_context(budget=1000, used=900)  # exactly 90%
        assert manager.should_use_fallback(ctx, threshold=0.9) is True

    def test_true_above_threshold(self):
        manager = BudgetManager()
        ctx = make_context(budget=1000, used=999)
        assert manager.should_use_fallback(ctx, threshold=0.9) is True

    def test_custom_threshold(self):
        manager = BudgetManager()
        ctx = make_context(budget=1000, used=600)  # 60%
        assert manager.should_use_fallback(ctx, threshold=0.5) is True
        assert manager.should_use_fallback(ctx, threshold=0.7) is False


# ── usage_summary ─────────────────────────────────────────────────────────────

class TestUsageSummary:
    def test_returns_expected_keys(self):
        manager = BudgetManager()
        ctx = make_context(budget=1000, used=250)
        summary = manager.usage_summary(ctx)
        for key in (
            "job_id",
            "agent_name",
            "token_budget",
            "tokens_used",
            "tokens_remaining",
            "utilisation_pct",
            "fallback_triggered",
        ):
            assert key in summary, f"Missing key: {key}"

    def test_utilisation_pct_calculation(self):
        manager = BudgetManager()
        ctx = make_context(budget=1000, used=250)
        summary = manager.usage_summary(ctx)
        assert summary["utilisation_pct"] == pytest.approx(25.0, rel=1e-2)

    def test_tokens_remaining_consistent(self):
        manager = BudgetManager()
        ctx = make_context(budget=1000, used=300)
        summary = manager.usage_summary(ctx)
        assert summary["tokens_remaining"] == 700


# ── BudgetExceededError ───────────────────────────────────────────────────────

class TestBudgetExceededError:
    def test_attributes_set_correctly(self):
        err = BudgetExceededError(requested=500, remaining=100)
        assert err.requested == 500
        assert err.remaining == 100

    def test_is_exception(self):
        err = BudgetExceededError(requested=1, remaining=0)
        assert isinstance(err, Exception)

    def test_message_contains_numbers(self):
        err = BudgetExceededError(requested=999, remaining=3)
        assert "999" in str(err)
        assert "3" in str(err)
