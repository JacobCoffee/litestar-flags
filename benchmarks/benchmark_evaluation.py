"""Benchmarks for flag evaluation performance.

These benchmarks measure the core flag evaluation logic including:
- Simple boolean flag evaluation
- Flag evaluation with targeting rules
- Flag evaluation with variants (A/B testing)
- Batch evaluation of multiple flags

Performance Targets:
- Simple boolean evaluation: <1ms
- Flag with rules: <5ms
- Flag with variants: <2ms
- Batch 100 flags: <100ms
- Batch 1000 flags: <1000ms
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from litestar_flags import EvaluationContext, MemoryStorageBackend
    from litestar_flags.engine import EvaluationEngine
    from litestar_flags.models.flag import FeatureFlag


# -----------------------------------------------------------------------------
# Simple Boolean Flag Evaluation
# -----------------------------------------------------------------------------


class TestSimpleBooleanEvaluation:
    """Benchmarks for simple boolean flag evaluation.

    Target: <1ms for simple boolean evaluation.
    This is the baseline for all other benchmarks.
    """

    @pytest.mark.benchmark(group="evaluation-simple")
    def test_simple_boolean_flag_evaluation(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        engine: EvaluationEngine,
        simple_boolean_flag: FeatureFlag,
        simple_context: EvaluationContext,
    ) -> None:
        """Benchmark simple boolean flag evaluation.

        Target: <1ms per evaluation.
        """

        async def setup_and_evaluate():
            await storage.create_flag(simple_boolean_flag)
            return await engine.evaluate(simple_boolean_flag, simple_context, storage)

        async def evaluate():
            return await engine.evaluate(simple_boolean_flag, simple_context, storage)

        # Setup
        asyncio.get_event_loop().run_until_complete(setup_and_evaluate())

        # Benchmark
        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate()))

        assert result is not None
        assert result.value is True

    @pytest.mark.benchmark(group="evaluation-simple")
    def test_simple_boolean_via_client(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        simple_boolean_flag: FeatureFlag,
        simple_context: EvaluationContext,
    ) -> None:
        """Benchmark simple boolean evaluation via the client.

        Tests the full client stack including error handling.
        Target: <1ms per evaluation.
        """
        from litestar_flags import FeatureFlagClient

        async def setup_and_get_client():
            await storage.create_flag(simple_boolean_flag)
            return FeatureFlagClient(storage=storage)

        client = asyncio.get_event_loop().run_until_complete(setup_and_get_client())

        async def evaluate():
            return await client.get_boolean_value(
                simple_boolean_flag.key,
                default=False,
                context=simple_context,
            )

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate()))

        assert result is True


# -----------------------------------------------------------------------------
# Flag with Rules Evaluation
# -----------------------------------------------------------------------------


class TestRulesEvaluation:
    """Benchmarks for flag evaluation with targeting rules."""

    @pytest.mark.benchmark(group="evaluation-rules")
    def test_single_rule_matching(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        engine: EvaluationEngine,
        flag_with_single_rule: FeatureFlag,
        complex_context: EvaluationContext,
    ) -> None:
        """Benchmark flag with single rule that matches.

        Target: <2ms per evaluation.
        """

        async def setup():
            await storage.create_flag(flag_with_single_rule)

        asyncio.get_event_loop().run_until_complete(setup())

        async def evaluate():
            return await engine.evaluate(flag_with_single_rule, complex_context, storage)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate()))

        assert result is not None
        assert result.value is True

    @pytest.mark.benchmark(group="evaluation-rules")
    def test_single_rule_not_matching(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        engine: EvaluationEngine,
        flag_with_single_rule: FeatureFlag,
        simple_context: EvaluationContext,
    ) -> None:
        """Benchmark flag with single rule that doesn't match.

        Tests the case where we fall through to default.
        Target: <2ms per evaluation.
        """

        async def setup():
            await storage.create_flag(flag_with_single_rule)

        asyncio.get_event_loop().run_until_complete(setup())

        async def evaluate():
            return await engine.evaluate(flag_with_single_rule, simple_context, storage)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate()))

        assert result is not None
        assert result.value is False  # Default

    @pytest.mark.benchmark(group="evaluation-rules")
    def test_multiple_rules_evaluation(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        engine: EvaluationEngine,
        flag_with_multiple_rules: FeatureFlag,
        complex_context: EvaluationContext,
    ) -> None:
        """Benchmark flag with multiple rules.

        Tests evaluation with 5 rules of varying complexity.
        Target: <5ms per evaluation.
        """

        async def setup():
            await storage.create_flag(flag_with_multiple_rules)

        asyncio.get_event_loop().run_until_complete(setup())

        async def evaluate():
            return await engine.evaluate(flag_with_multiple_rules, complex_context, storage)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate()))

        assert result is not None

    @pytest.mark.benchmark(group="evaluation-rules")
    def test_multiple_rules_worst_case(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        engine: EvaluationEngine,
        flag_with_multiple_rules: FeatureFlag,
    ) -> None:
        """Benchmark multiple rules with no match (worst case).

        Tests evaluation when all rules are checked and none match.
        Target: <5ms per evaluation.
        """
        from litestar_flags import EvaluationContext

        # Context that won't match any rules
        no_match_context = EvaluationContext(
            targeting_key="no-match-user",
            attributes={
                "plan": "free",
                "country": "BR",
                "beta_tester": False,
                "email": "user@example.com",
            },
        )

        async def setup():
            await storage.create_flag(flag_with_multiple_rules)

        asyncio.get_event_loop().run_until_complete(setup())

        async def evaluate():
            return await engine.evaluate(flag_with_multiple_rules, no_match_context, storage)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate()))

        assert result is not None


# -----------------------------------------------------------------------------
# Variant Evaluation (A/B Testing)
# -----------------------------------------------------------------------------


class TestVariantEvaluation:
    """Benchmarks for A/B test variant evaluation."""

    @pytest.mark.benchmark(group="evaluation-variants")
    def test_two_variant_selection(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        engine: EvaluationEngine,
        flag_with_variants: FeatureFlag,
        simple_context: EvaluationContext,
    ) -> None:
        """Benchmark A/B test with 2 variants (50/50 split).

        Target: <2ms per evaluation.
        """

        async def setup():
            await storage.create_flag(flag_with_variants)

        asyncio.get_event_loop().run_until_complete(setup())

        async def evaluate():
            return await engine.evaluate(flag_with_variants, simple_context, storage)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate()))

        assert result is not None
        assert result.variant in ["control", "treatment"]

    @pytest.mark.benchmark(group="evaluation-variants")
    def test_multi_variant_selection(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        engine: EvaluationEngine,
        flag_with_multi_variants: FeatureFlag,
        simple_context: EvaluationContext,
    ) -> None:
        """Benchmark multivariate test with 4 variants.

        Target: <2ms per evaluation.
        """

        async def setup():
            await storage.create_flag(flag_with_multi_variants)

        asyncio.get_event_loop().run_until_complete(setup())

        async def evaluate():
            return await engine.evaluate(flag_with_multi_variants, simple_context, storage)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate()))

        assert result is not None
        assert result.variant in ["control", "variant-a", "variant-b", "variant-c"]


# -----------------------------------------------------------------------------
# Batch Evaluation
# -----------------------------------------------------------------------------


class TestBatchEvaluation:
    """Benchmarks for batch flag evaluation."""

    @pytest.mark.benchmark(group="evaluation-batch")
    def test_batch_100_flags(
        self,
        benchmark,
        storage_100: MemoryStorageBackend,
        simple_context: EvaluationContext,
    ) -> None:
        """Benchmark batch evaluation of 100 flags.

        Target: <100ms total for 100 flags (<1ms per flag).
        """
        from litestar_flags import FeatureFlagClient

        client = FeatureFlagClient(storage=storage_100)

        async def evaluate_all():
            return await client.get_all_flags(context=simple_context)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate_all()))

        assert len(result) == 100

    @pytest.mark.benchmark(group="evaluation-batch")
    def test_batch_1000_flags(
        self,
        benchmark,
        storage_1000: MemoryStorageBackend,
        simple_context: EvaluationContext,
    ) -> None:
        """Benchmark batch evaluation of 1000 flags.

        Target: <1000ms total for 1000 flags (<1ms per flag).
        """
        from litestar_flags import FeatureFlagClient

        client = FeatureFlagClient(storage=storage_1000)

        async def evaluate_all():
            return await client.get_all_flags(context=simple_context)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate_all()))

        assert len(result) == 1000

    @pytest.mark.benchmark(group="evaluation-batch")
    def test_selective_batch_evaluation(
        self,
        benchmark,
        storage_1000: MemoryStorageBackend,
        simple_context: EvaluationContext,
    ) -> None:
        """Benchmark selective batch evaluation of 50 flags from 1000.

        Tests fetching a subset of flags by key.
        Target: <50ms total.
        """
        from litestar_flags import FeatureFlagClient

        client = FeatureFlagClient(storage=storage_1000)
        keys = [f"flag-{i:05d}" for i in range(0, 1000, 20)]  # 50 flags

        async def evaluate_subset():
            return await client.get_flags(keys, context=simple_context)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate_subset()))

        assert len(result) == 50


# -----------------------------------------------------------------------------
# Throughput Tests
# -----------------------------------------------------------------------------


class TestThroughput:
    """Benchmarks for evaluation throughput."""

    @pytest.mark.benchmark(group="throughput")
    def test_sequential_evaluations(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        simple_boolean_flag: FeatureFlag,
        contexts_100: list[EvaluationContext],
    ) -> None:
        """Benchmark 100 sequential evaluations of the same flag.

        Tests throughput for the same flag with different contexts.
        Target: <100ms total.
        """
        from litestar_flags import FeatureFlagClient

        async def setup():
            await storage.create_flag(simple_boolean_flag)
            return FeatureFlagClient(storage=storage)

        client = asyncio.get_event_loop().run_until_complete(setup())

        async def evaluate_all():
            results = []
            for ctx in contexts_100:
                result = await client.get_boolean_value(
                    simple_boolean_flag.key,
                    default=False,
                    context=ctx,
                )
                results.append(result)
            return results

        results = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate_all()))

        assert len(results) == 100

    @pytest.mark.benchmark(group="throughput")
    def test_is_enabled_throughput(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        simple_boolean_flag: FeatureFlag,
        contexts_100: list[EvaluationContext],
    ) -> None:
        """Benchmark is_enabled() convenience method throughput.

        Tests the commonly used is_enabled shorthand.
        Target: <100ms for 100 calls.
        """
        from litestar_flags import FeatureFlagClient

        async def setup():
            await storage.create_flag(simple_boolean_flag)
            return FeatureFlagClient(storage=storage)

        client = asyncio.get_event_loop().run_until_complete(setup())

        async def check_all():
            results = []
            for ctx in contexts_100:
                result = await client.is_enabled(simple_boolean_flag.key, context=ctx)
                results.append(result)
            return results

        results = benchmark(lambda: asyncio.get_event_loop().run_until_complete(check_all()))

        assert len(results) == 100
        assert all(r is True for r in results)


# -----------------------------------------------------------------------------
# Edge Cases
# -----------------------------------------------------------------------------


class TestEdgeCases:
    """Benchmarks for edge case scenarios."""

    @pytest.mark.benchmark(group="edge-cases")
    def test_flag_not_found(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        simple_context: EvaluationContext,
    ) -> None:
        """Benchmark evaluation of non-existent flag.

        Tests the error path performance.
        Target: <1ms per evaluation.
        """
        from litestar_flags import FeatureFlagClient

        client = FeatureFlagClient(storage=storage)

        async def evaluate():
            return await client.get_boolean_value(
                "non-existent-flag",
                default=False,
                context=simple_context,
            )

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate()))

        assert result is False

    @pytest.mark.benchmark(group="edge-cases")
    def test_empty_context(
        self,
        benchmark,
        storage: MemoryStorageBackend,
        engine: EvaluationEngine,
        simple_boolean_flag: FeatureFlag,
    ) -> None:
        """Benchmark evaluation with empty context.

        Tests evaluation with minimal context data.
        Target: <1ms per evaluation.
        """
        from litestar_flags import EvaluationContext

        empty_context = EvaluationContext()

        async def setup():
            await storage.create_flag(simple_boolean_flag)

        asyncio.get_event_loop().run_until_complete(setup())

        async def evaluate():
            return await engine.evaluate(simple_boolean_flag, empty_context, storage)

        result = benchmark(lambda: asyncio.get_event_loop().run_until_complete(evaluate()))

        assert result is not None
