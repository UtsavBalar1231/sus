"""Tests for concurrency default values.

These defaults are optimized for high-performance crawling:
- global_concurrent_requests: 200 (up from 50)
- per_domain_concurrent_requests: 25 (up from 10)
- rate_limiter_burst_size: 50 (up from 10)
- delay_between_requests: 0.1 (down from 0.5)
"""

from sus.config import CrawlingRules, PipelineConfig


def test_global_concurrent_requests_default() -> None:
    """Verify global_concurrent_requests defaults to 200 for high-performance crawling."""
    rules = CrawlingRules()
    assert rules.global_concurrent_requests == 200, "Should default to 200 for high throughput"


def test_per_domain_concurrent_requests_default() -> None:
    """Verify per_domain_concurrent_requests defaults to 25 for faster per-domain crawling."""
    rules = CrawlingRules()
    assert rules.per_domain_concurrent_requests == 25, (
        "Should default to 25 for faster per-domain crawling"
    )


def test_rate_limiter_burst_size_default() -> None:
    """Verify rate_limiter_burst_size defaults to 50 for better burst handling."""
    rules = CrawlingRules()
    assert rules.rate_limiter_burst_size == 50, "Should default to 50 for better burst handling"


def test_delay_between_requests_default() -> None:
    """Verify delay_between_requests defaults to 0.1 for faster crawling."""
    rules = CrawlingRules()
    assert rules.delay_between_requests == 0.1, "Should default to 0.1s for faster crawling"


def test_pipeline_enabled_by_default() -> None:
    """Verify pipeline is enabled by default for better throughput."""
    pipeline = PipelineConfig()
    assert pipeline.enabled is True, "Pipeline should be enabled by default"
