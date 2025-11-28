"""Tests for concurrency default values."""

from sus.config import CrawlingRules, PipelineConfig


def test_global_concurrent_requests_default() -> None:
    """Verify global_concurrent_requests defaults to 50."""
    rules = CrawlingRules()
    assert rules.global_concurrent_requests == 50, "Should default to 50 for high throughput"


def test_per_domain_concurrent_requests_default() -> None:
    """Verify per_domain_concurrent_requests defaults to 10."""
    rules = CrawlingRules()
    assert rules.per_domain_concurrent_requests == 10, (
        "Should default to 10 for HTTP/2 multiplexing"
    )


def test_rate_limiter_burst_size_default() -> None:
    """Verify rate_limiter_burst_size defaults to 10."""
    rules = CrawlingRules()
    assert rules.rate_limiter_burst_size == 10, "Should default to 10 for better burst handling"


def test_pipeline_enabled_by_default() -> None:
    """Verify pipeline is enabled by default for better throughput."""
    pipeline = PipelineConfig()
    assert pipeline.enabled is True, "Pipeline should be enabled by default"
