"""Benchmarks for content quality analysis.

Tests performance of:
- ContentQualityAnalyzer.analyze() - Full HTML analysis
- ContentQuality.needs_js - JS requirement heuristic
- ContentQuality.quality_score - Quality scoring
"""

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from sus.content_quality import ContentQuality, ContentQualityAnalyzer


class TestContentQualityAnalyzerBenchmarks:
    """Benchmark ContentQualityAnalyzer.analyze() method."""

    def test_analyze_small_html(self, benchmark: BenchmarkFixture, small_html: str) -> None:
        """Benchmark analysis of small (~1KB) HTML page."""
        result = benchmark(ContentQualityAnalyzer.analyze, small_html)
        assert isinstance(result, ContentQuality)
        assert result.text_length > 0

    def test_analyze_medium_html(self, benchmark: BenchmarkFixture, medium_html: str) -> None:
        """Benchmark analysis of medium (~10KB) documentation page."""
        result = benchmark(ContentQualityAnalyzer.analyze, medium_html)
        assert result.text_length > 1000
        assert result.link_count >= 100
        assert result.paragraph_count >= 50

    def test_analyze_large_html(self, benchmark: BenchmarkFixture, large_html: str) -> None:
        """Benchmark analysis of large (~100KB) documentation page."""
        result = benchmark(ContentQualityAnalyzer.analyze, large_html)
        assert result.text_length > 10000
        assert result.link_count >= 500
        assert result.paragraph_count >= 200

    def test_analyze_spa_shell(self, benchmark: BenchmarkFixture, spa_shell_html: str) -> None:
        """Benchmark SPA shell detection (React)."""
        result = benchmark(ContentQualityAnalyzer.analyze, spa_shell_html)
        assert result.has_react_root is True
        assert result.has_noscript_warning is True

    def test_analyze_vue_shell(self, benchmark: BenchmarkFixture, vue_shell_html: str) -> None:
        """Benchmark SPA shell detection (Vue)."""
        result = benchmark(ContentQualityAnalyzer.analyze, vue_shell_html)
        assert result.has_vue_app is True

    def test_analyze_loading_page(
        self, benchmark: BenchmarkFixture, loading_page_html: str
    ) -> None:
        """Benchmark loading indicator detection."""
        result = benchmark(ContentQualityAnalyzer.analyze, loading_page_html)
        assert result.has_loading_indicators is True

    def test_analyze_empty_html(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark handling of empty HTML."""
        result = benchmark(ContentQualityAnalyzer.analyze, "")
        assert result.text_length == 0

    def test_analyze_batch_10(self, benchmark: BenchmarkFixture, medium_html: str) -> None:
        """Benchmark analyzing 10 pages (typical crawl batch)."""
        pages = [medium_html] * 10

        def analyze_batch() -> list[ContentQuality]:
            return [ContentQualityAnalyzer.analyze(p) for p in pages]

        results = benchmark(analyze_batch)
        assert len(results) == 10
        assert all(r.text_length > 0 for r in results)


class TestContentQualityPropertiesBenchmarks:
    """Benchmark ContentQuality property computations."""

    @pytest.fixture
    def spa_quality(self, spa_shell_html: str) -> ContentQuality:
        """Pre-analyzed SPA shell quality."""
        return ContentQualityAnalyzer.analyze(spa_shell_html)

    @pytest.fixture
    def good_quality(self, medium_html: str) -> ContentQuality:
        """Pre-analyzed good quality page."""
        return ContentQualityAnalyzer.analyze(medium_html)

    def test_needs_js_spa(self, benchmark: BenchmarkFixture, spa_quality: ContentQuality) -> None:
        """Benchmark needs_js for SPA shell (should be True)."""
        result = benchmark(lambda: spa_quality.needs_js)
        assert result is True

    def test_needs_js_good_content(
        self, benchmark: BenchmarkFixture, good_quality: ContentQuality
    ) -> None:
        """Benchmark needs_js for good content (should be False)."""
        result = benchmark(lambda: good_quality.needs_js)
        assert result is False

    def test_quality_score_spa(
        self, benchmark: BenchmarkFixture, spa_quality: ContentQuality
    ) -> None:
        """Benchmark quality_score for SPA shell (low score)."""
        result = benchmark(lambda: spa_quality.quality_score)
        assert result < 0.3

    def test_quality_score_good(
        self, benchmark: BenchmarkFixture, good_quality: ContentQuality
    ) -> None:
        """Benchmark quality_score for good content (high score)."""
        result = benchmark(lambda: good_quality.quality_score)
        assert result > 0.5


class TestShouldRetryWithJsBenchmarks:
    """Benchmark should_retry_with_js decision logic."""

    @pytest.fixture
    def spa_quality(self, spa_shell_html: str) -> ContentQuality:
        """Pre-analyzed SPA shell quality."""
        return ContentQualityAnalyzer.analyze(spa_shell_html)

    @pytest.fixture
    def good_quality(self, medium_html: str) -> ContentQuality:
        """Pre-analyzed good quality page."""
        return ContentQualityAnalyzer.analyze(medium_html)

    def test_should_retry_spa(
        self, benchmark: BenchmarkFixture, spa_quality: ContentQuality
    ) -> None:
        """Benchmark retry decision for SPA shell."""
        result = benchmark(
            ContentQualityAnalyzer.should_retry_with_js,
            spa_quality,
            min_quality_score=0.3,
        )
        assert result is True

    def test_should_retry_good_content(
        self, benchmark: BenchmarkFixture, good_quality: ContentQuality
    ) -> None:
        """Benchmark retry decision for good content."""
        result = benchmark(
            ContentQualityAnalyzer.should_retry_with_js,
            good_quality,
            min_quality_score=0.3,
        )
        assert result is False

    def test_should_retry_with_force_domain(
        self, benchmark: BenchmarkFixture, good_quality: ContentQuality
    ) -> None:
        """Benchmark retry decision with force_js_domains."""
        force_domains = {"spa.example.com", "app.example.com"}
        result = benchmark(
            ContentQualityAnalyzer.should_retry_with_js,
            good_quality,
            min_quality_score=0.3,
            force_js_domains=force_domains,
            domain="spa.example.com",
        )
        assert result is True
