"""Tests for concurrency default values."""

from sus.config import CrawlingRules


def test_global_concurrent_requests_default() -> None:
    """Verify global_concurrent_requests defaults to 25."""
    rules = CrawlingRules()
    assert rules.global_concurrent_requests == 25, "Should default to 25 for better throughput"


def test_per_domain_concurrent_requests_default() -> None:
    """Verify per_domain_concurrent_requests defaults to 5."""
    rules = CrawlingRules()
    assert rules.per_domain_concurrent_requests == 5, "Should default to 5 (up from 2)"


def test_rate_limiter_burst_size_default() -> None:
    """Verify rate_limiter_burst_size defaults to 10."""
    rules = CrawlingRules()
    assert rules.rate_limiter_burst_size == 10, "Should default to 10 for better burst handling"
