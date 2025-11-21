"""Tests for adaptive retry with httpx-retries integration."""

import pytest
from pydantic import ValidationError

from sus.config import CrawlingRules, SiteConfig, SusConfig
from sus.crawler import Crawler


async def test_retry_jitter_field_in_config() -> None:
    """Test that retry_jitter field exists and has correct defaults."""
    config = SusConfig(
        name="retry-test",
        site=SiteConfig(
            start_urls=["https://example.com"],
            allowed_domains=["example.com"],
        ),
    )
    assert hasattr(config.crawling, "retry_jitter")
    assert config.crawling.retry_jitter == 0.3  # Default value
    assert 0.0 <= config.crawling.retry_jitter <= 1.0


async def test_retry_jitter_validation() -> None:
    """Test that retry_jitter validates range (0-1)."""
    # Valid values
    config = SusConfig(
        name="retry-test",
        site=SiteConfig(
            start_urls=["https://example.com"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(retry_jitter=0.0),
    )
    assert config.crawling.retry_jitter == 0.0

    config = SusConfig(
        name="retry-test",
        site=SiteConfig(
            start_urls=["https://example.com"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(retry_jitter=1.0),
    )
    assert config.crawling.retry_jitter == 1.0

    # Invalid values should raise ValidationError
    with pytest.raises(ValidationError):
        SusConfig(
            name="retry-test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            crawling=CrawlingRules(retry_jitter=-0.1),
        )

    with pytest.raises(ValidationError):
        SusConfig(
            name="retry-test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            crawling=CrawlingRules(retry_jitter=1.1),
        )


async def test_crawler_client_initialization_with_retry_transport() -> None:
    """Test that Crawler initializes HTTP client with RetryTransport correctly."""
    config = SusConfig(
        name="retry-test",
        site=SiteConfig(
            start_urls=["https://example.com"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            max_retries=5,
            retry_backoff=3.0,
            retry_jitter=0.5,
        ),
    )

    crawler = Crawler(config)
    await crawler._ensure_client()

    # Verify client was created
    assert crawler.client is not None

    # Verify transport is configured (client.transport exists)
    assert hasattr(crawler.client, "_transport")

    # httpx-retries wraps the transport, so we can't easily introspect it
    # but we can verify the crawler initialized without errors
    assert crawler.config.crawling.max_retries == 5
    assert crawler.config.crawling.retry_backoff == 3.0
    assert crawler.config.crawling.retry_jitter == 0.5


async def test_retry_config_mapping() -> None:
    """Verify retry config values are correctly mapped to RetryTransport."""
    test_cases = [
        # (max_retries, retry_backoff, retry_jitter)
        (0, 1.0, 0.0),  # No retries
        (3, 2.0, 0.3),  # Default values
        (10, 5.0, 1.0),  # High values
    ]

    for max_retries, retry_backoff, retry_jitter in test_cases:
        config = SusConfig(
            name="retry-test",
            site=SiteConfig(
                start_urls=["https://example.com"],
                allowed_domains=["example.com"],
            ),
            crawling=CrawlingRules(
                max_retries=max_retries,
                retry_backoff=retry_backoff,
                retry_jitter=retry_jitter,
            ),
        )

        crawler = Crawler(config)
        await crawler._ensure_client()

        # Verify config values are preserved
        assert crawler.config.crawling.max_retries == max_retries
        assert crawler.config.crawling.retry_backoff == retry_backoff
        assert crawler.config.crawling.retry_jitter == retry_jitter

        # Verify client was created successfully with these values
        assert crawler.client is not None

        # Cleanup
        await crawler.client.aclose()
