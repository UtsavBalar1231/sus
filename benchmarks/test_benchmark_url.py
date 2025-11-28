"""Benchmarks for URL normalization and pattern matching.

Tests performance of:
- URLNormalizer.normalize_url() - URL canonicalization
- URLNormalizer.filter_dangerous_schemes() - Scheme validation
- PathPattern.matches() - Regex/glob/prefix matching
- RulesEngine.should_crawl() - Full URL filtering
"""

from pytest_benchmark.fixture import BenchmarkFixture

from sus.config import PathPattern, SusConfig
from sus.rules import RulesEngine, URLNormalizer


class TestURLNormalizerBenchmarks:
    """Benchmark URLNormalizer methods."""

    def test_normalize_url_simple(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark simple URL normalization (no changes needed)."""
        url = "https://example.com/docs/guide"
        result = benchmark(URLNormalizer.normalize_url, url)
        assert result == "https://example.com/docs/guide"

    def test_normalize_url_complex(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark URL with port, query, fragment removal."""
        url = "HTTP://Example.COM:80/Path?query=1&b=2#section"
        result = benchmark(URLNormalizer.normalize_url, url)
        assert "example.com" in result
        assert "#" not in result  # Fragment removed

    def test_normalize_url_with_port(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark URL with non-default port (preserved)."""
        url = "https://example.com:8443/api/endpoint"
        result = benchmark(URLNormalizer.normalize_url, url)
        assert ":8443" in result

    def test_normalize_batch_100(self, benchmark: BenchmarkFixture, sample_urls: list[str]) -> None:
        """Benchmark normalizing 100 URLs."""

        def normalize_batch() -> list[str]:
            return [URLNormalizer.normalize_url(u) for u in sample_urls]

        results = benchmark(normalize_batch)
        assert len(results) == 100

    def test_filter_dangerous_schemes_safe(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark filtering safe HTTP/HTTPS schemes."""
        url = "https://example.com/page"
        result = benchmark(URLNormalizer.filter_dangerous_schemes, url)
        assert result is True

    def test_filter_dangerous_schemes_unsafe(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark filtering dangerous schemes."""
        url = "javascript:alert('xss')"
        result = benchmark(URLNormalizer.filter_dangerous_schemes, url)
        assert result is False

    def test_filter_dangerous_schemes_batch(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark scheme filtering on mixed batch."""
        urls = [
            "https://example.com/page1",
            "http://example.com/page2",
            "javascript:alert(1)",
            "mailto:user@example.com",
            "https://example.com/page3",
            "data:text/html,<h1>test</h1>",
            "http://example.com/page4",
            "file:///etc/passwd",
        ] * 12  # 96 URLs

        def filter_batch() -> list[bool]:
            return [URLNormalizer.filter_dangerous_schemes(u) for u in urls]

        results = benchmark(filter_batch)
        assert len(results) == 96
        # Should have mix of True (safe) and False (unsafe)
        assert any(results)
        assert not all(results)


class TestPatternMatchingBenchmarks:
    """Benchmark PathPattern matching."""

    def test_regex_pattern_match(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark regex pattern matching (match case)."""
        pattern = PathPattern(pattern=r"^/docs/.*\.html$", type="regex")
        path = "/docs/api/guide.html"
        result = benchmark(pattern.matches, path)
        assert result is True

    def test_regex_pattern_no_match(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark regex pattern matching (no match case)."""
        pattern = PathPattern(pattern=r"^/docs/.*\.html$", type="regex")
        path = "/api/endpoint.json"
        result = benchmark(pattern.matches, path)
        assert result is False

    def test_glob_pattern_match(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark glob pattern matching."""
        pattern = PathPattern(pattern="*.pdf", type="glob")
        path = "document.pdf"
        result = benchmark(pattern.matches, path)
        assert result is True

    def test_prefix_pattern_match(self, benchmark: BenchmarkFixture) -> None:
        """Benchmark prefix pattern matching."""
        pattern = PathPattern(pattern="/docs/", type="prefix")
        path = "/docs/api/guide"
        result = benchmark(pattern.matches, path)
        assert result is True

    def test_regex_pattern_batch(
        self, benchmark: BenchmarkFixture, sample_paths: list[str]
    ) -> None:
        """Benchmark regex pattern on 100 paths."""
        pattern = PathPattern(pattern=r"^/docs/api/v\d+/.*\.html$", type="regex")

        def match_batch() -> list[bool]:
            return [pattern.matches(p) for p in sample_paths]

        results = benchmark(match_batch)
        assert len(results) == 100

    def test_glob_pattern_batch(self, benchmark: BenchmarkFixture, sample_paths: list[str]) -> None:
        """Benchmark glob pattern on 100 paths."""
        pattern = PathPattern(pattern="*.html", type="glob")

        def match_batch() -> list[bool]:
            return [pattern.matches(p) for p in sample_paths]

        results = benchmark(match_batch)
        assert len(results) == 100
        assert all(results)  # All paths end in .html

    def test_prefix_pattern_batch(
        self, benchmark: BenchmarkFixture, sample_paths: list[str]
    ) -> None:
        """Benchmark prefix pattern on 100 paths."""
        pattern = PathPattern(pattern="/docs/", type="prefix")

        def match_batch() -> list[bool]:
            return [pattern.matches(p) for p in sample_paths]

        results = benchmark(match_batch)
        assert len(results) == 100
        assert all(results)  # All paths start with /docs/


class TestRulesEngineBenchmarks:
    """Benchmark RulesEngine URL filtering."""

    def test_should_follow_allowed(
        self, benchmark: BenchmarkFixture, sample_config: SusConfig
    ) -> None:
        """Benchmark should_follow for allowed URL."""
        engine = RulesEngine(sample_config)
        url = "http://example.com/docs/guide"
        result = benchmark(engine.should_follow, url)
        assert result is True

    def test_should_follow_excluded(
        self, benchmark: BenchmarkFixture, sample_config: SusConfig
    ) -> None:
        """Benchmark should_follow for excluded URL."""
        engine = RulesEngine(sample_config)
        url = "http://example.com/docs/file.pdf"
        result = benchmark(engine.should_follow, url)
        assert result is False

    def test_should_follow_wrong_domain(
        self, benchmark: BenchmarkFixture, sample_config: SusConfig
    ) -> None:
        """Benchmark should_follow for disallowed domain."""
        engine = RulesEngine(sample_config)
        url = "http://other-site.com/docs/guide"
        result = benchmark(engine.should_follow, url)
        assert result is False

    def test_should_follow_batch(
        self, benchmark: BenchmarkFixture, sample_config: SusConfig
    ) -> None:
        """Benchmark should_follow on 100 mixed URLs."""
        engine = RulesEngine(sample_config)
        urls = [
            f"http://example.com/docs/page{i}.html" if i % 3 != 0 else f"http://example.com/api/{i}"
            for i in range(100)
        ]

        def check_batch() -> list[bool]:
            return [engine.should_follow(u) for u in urls]

        results = benchmark(check_batch)
        assert len(results) == 100
