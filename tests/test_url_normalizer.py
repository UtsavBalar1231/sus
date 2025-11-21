"""Unit tests for URLNormalizer edge cases."""

from typing import Literal

import pytest

from sus.rules import URLNormalizer


@pytest.mark.parametrize(
    "url,expected",
    [
        # Basic normalization
        ("http://example.com", "http://example.com"),
        ("https://example.com", "https://example.com"),
        # Case normalization
        ("HTTP://EXAMPLE.COM", "http://example.com"),
        ("HtTp://ExAmPlE.cOm", "http://example.com"),
        ("https://EXAMPLE.COM/PATH", "https://example.com/PATH"),
        # Port normalization (remove default ports)
        ("http://example.com:80", "http://example.com"),
        ("https://example.com:443", "https://example.com"),
        ("http://example.com:80/path", "http://example.com/path"),
        ("https://example.com:443/path", "https://example.com/path"),
        # Keep non-default ports
        ("http://example.com:8080", "http://example.com:8080"),
        ("https://example.com:8443", "https://example.com:8443"),
        ("http://example.com:3000/api", "http://example.com:3000/api"),
        # Fragment removal
        ("http://example.com#section", "http://example.com"),
        ("http://example.com/path#anchor", "http://example.com/path"),
        ("http://example.com/page?q=1#top", "http://example.com/page?q=1"),
        # Preserve query parameters
        ("http://example.com?foo=bar", "http://example.com?foo=bar"),
        ("http://example.com/path?a=1&b=2", "http://example.com/path?a=1&b=2"),
        # Preserve path
        ("http://example.com/path/to/page", "http://example.com/path/to/page"),
        ("http://example.com/path/", "http://example.com/path/"),
        # Complex combinations
        (
            "HTTP://Example.COM:80/Path?query=value#fragment",
            "http://example.com/Path?query=value",
        ),
        (
            "HTTPS://EXAMPLE.COM:443/PATH/?Q=1#SECTION",
            "https://example.com/PATH/?Q=1",
        ),
    ],
)
def test_normalize_url_basic(url: str, expected: str) -> None:
    """Test basic URL normalization."""
    assert URLNormalizer.normalize_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",  # Empty string
        "   ",  # Whitespace only
        "\t\n",  # Tabs and newlines
    ],
)
def test_normalize_url_empty_raises(url: str) -> None:
    """Test normalizing empty URLs raises ValueError."""
    with pytest.raises(ValueError, match="URL cannot be empty"):
        URLNormalizer.normalize_url(url)


@pytest.mark.parametrize(
    "url,expected",
    [
        # Trailing slashes
        ("http://example.com/", "http://example.com/"),
        ("http://example.com/path/", "http://example.com/path/"),
        ("http://example.com/path", "http://example.com/path"),
        # Multiple slashes in path
        ("http://example.com//path", "http://example.com//path"),
        ("http://example.com///path", "http://example.com///path"),
        # Encoded characters (should be preserved)
        ("http://example.com/path%20with%20spaces", "http://example.com/path%20with%20spaces"),
        ("http://example.com/path?q=%3Fvalue", "http://example.com/path?q=%3Fvalue"),
    ],
)
def test_normalize_url_path_handling(url: str, expected: str) -> None:
    """Test URL normalization handles paths correctly."""
    assert URLNormalizer.normalize_url(url) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        # User authentication (rare but valid)
        ("http://user@example.com", "http://user@example.com"),
        ("http://user:pass@example.com", "http://user:pass@example.com"),
        (
            "http://user:pass@example.com:8080/path",
            "http://user:pass@example.com:8080/path",
        ),
        # Case: username/password should be preserved, hostname normalized
        ("http://USER:PASS@EXAMPLE.COM", "http://USER:PASS@example.com"),
    ],
)
def test_normalize_url_with_auth(url: str, expected: str) -> None:
    """Test URL normalization with authentication credentials."""
    assert URLNormalizer.normalize_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "example.com",  # Missing scheme
        "//example.com",  # Protocol-relative URL
        "ftp://example.com",  # Valid but different scheme
    ],
)
def test_normalize_url_malformed(url: str) -> None:
    """Test normalization of malformed URLs (should not crash)."""
    # These may raise ValueError or return unexpected results
    # The key is they don't crash the application
    try:
        result = URLNormalizer.normalize_url(url)
        # If it succeeds, result should be a string
        assert isinstance(result, str)
    except ValueError:
        # ValueError is acceptable for malformed URLs
        pass


@pytest.mark.parametrize(
    "url,expected_safe",
    [
        # Safe schemes
        ("http://example.com", True),
        ("https://example.com", True),
        ("HTTP://example.com", True),  # Case insensitive
        ("HTTPS://EXAMPLE.COM", True),
        ("http://example.com:8080/path", True),
        # Dangerous schemes
        ("mailto:user@example.com", False),
        ("tel:+1234567890", False),
        ("javascript:alert('xss')", False),
        ("data:text/html,<script>alert(1)</script>", False),
        ("file:///etc/passwd", False),
        ("ftp://ftp.example.com", False),
        ("blob:http://example.com/uuid", False),
        ("about:blank", False),
        # Case insensitive dangerous schemes
        ("MAILTO:user@example.com", False),
        ("JavaScript:alert(1)", False),
        ("FTP://example.com", False),
    ],
)
def test_filter_dangerous_schemes(url: str, expected_safe: bool) -> None:
    """Test dangerous URL scheme filtering."""
    assert URLNormalizer.filter_dangerous_schemes(url) == expected_safe


@pytest.mark.parametrize(
    "url",
    [
        "",  # Empty
        "not-a-url",  # No scheme
        "///path",  # Invalid
        "http//example.com",  # Malformed
    ],
)
def test_filter_dangerous_schemes_malformed(url: str) -> None:
    """Test dangerous scheme filter with malformed URLs."""
    # Malformed URLs should be considered unsafe (return False)
    assert URLNormalizer.filter_dangerous_schemes(url) is False


@pytest.mark.parametrize(
    "url,strategy,expected",
    [
        # Strip strategy
        (
            "http://example.com/path?foo=bar",
            "strip",
            "http://example.com/path",
        ),
        (
            "http://example.com/path?a=1&b=2&c=3",
            "strip",
            "http://example.com/path",
        ),
        (
            "http://example.com?query=value",
            "strip",
            "http://example.com",
        ),
        # Preserve strategy
        (
            "http://example.com/path?foo=bar",
            "preserve",
            "http://example.com/path?foo=bar",
        ),
        (
            "http://example.com/path?a=1&b=2",
            "preserve",
            "http://example.com/path?a=1&b=2",
        ),
        # URLs without query params (no change)
        (
            "http://example.com/path",
            "strip",
            "http://example.com/path",
        ),
        (
            "http://example.com/path",
            "preserve",
            "http://example.com/path",
        ),
    ],
)
def test_handle_query_parameters(url: str, strategy: Literal["strip", "preserve"], expected: str) -> None:
    """Test query parameter handling with strip/preserve strategies."""
    assert URLNormalizer.handle_query_parameters(url, strategy) == expected


def test_handle_query_parameters_preserves_fragments() -> None:
    """Test query parameter stripping preserves fragments.

    Note: This is current behavior - URLNormalizer.normalize_url() removes
    fragments, but handle_query_parameters() preserves them.
    """
    url = "http://example.com/path?query=1#section"
    result = URLNormalizer.handle_query_parameters(url, "strip")
    assert result == "http://example.com/path#section"


def test_handle_query_parameters_complex() -> None:
    """Test query parameter handling with complex query strings."""
    url = "http://example.com/path?foo=bar&baz=qux&test=1%202%203"

    # Strip should remove entire query string
    result_strip = URLNormalizer.handle_query_parameters(url, "strip")
    assert "?" not in result_strip
    assert result_strip == "http://example.com/path"

    # Preserve should keep everything
    result_preserve = URLNormalizer.handle_query_parameters(url, "preserve")
    assert "?" in result_preserve
    assert "foo=bar" in result_preserve
    assert "baz=qux" in result_preserve


def test_normalize_url_ipv4_address() -> None:
    """Test URL normalization with IPv4 addresses."""
    url = "http://192.168.1.1:8080/path"
    result = URLNormalizer.normalize_url(url)
    assert result == "http://192.168.1.1:8080/path"


def test_normalize_url_localhost() -> None:
    """Test URL normalization with localhost."""
    url = "http://localhost:3000/api"
    result = URLNormalizer.normalize_url(url)
    assert result == "http://localhost:3000/api"

    # localhost on default port
    url2 = "http://localhost:80/"
    result2 = URLNormalizer.normalize_url(url2)
    assert result2 == "http://localhost/"


def test_normalize_url_subdomain() -> None:
    """Test URL normalization preserves subdomains."""
    url = "http://api.example.com/v1/users"
    result = URLNormalizer.normalize_url(url)
    assert result == "http://api.example.com/v1/users"

    url2 = "HTTP://API.EXAMPLE.COM/V1/USERS"
    result2 = URLNormalizer.normalize_url(url2)
    assert result2 == "http://api.example.com/V1/USERS"


def test_normalize_url_international_domain() -> None:
    """Test URL normalization with international domain names."""
    # IDN (internationalized domain names) should work
    url = "http://münchen.de/path"
    try:
        result = URLNormalizer.normalize_url(url)
        assert isinstance(result, str)
        assert "münchen" in result.lower() or "xn--" in result  # IDN encoded
    except ValueError:
        # Some systems may not support IDN
        pass


def test_normalize_url_with_params() -> None:
    """Test URL normalization preserves URL parameters (rare in HTTP)."""
    # URL params are different from query strings (e.g., ;param=value)
    url = "http://example.com/path;param=value"
    result = URLNormalizer.normalize_url(url)
    # Should preserve params
    assert "param=value" in result


def test_normalize_url_special_characters_in_path() -> None:
    """Test URL normalization with special characters in path."""
    url = "http://example.com/path/with-dashes_and_underscores/123"
    result = URLNormalizer.normalize_url(url)
    assert result == "http://example.com/path/with-dashes_and_underscores/123"


def test_normalize_url_percent_encoding() -> None:
    """Test URL normalization preserves percent-encoding."""
    # Spaces encoded as %20
    url = "http://example.com/path%20with%20spaces"
    result = URLNormalizer.normalize_url(url)
    assert "%20" in result

    # Special characters
    url2 = "http://example.com/path?q=%3Fvalue%3D1"
    result2 = URLNormalizer.normalize_url(url2)
    assert "%3F" in result2
    assert "%3D" in result2


def test_normalize_url_empty_path() -> None:
    """Test URL normalization with empty or root path."""
    url1 = "http://example.com"
    result1 = URLNormalizer.normalize_url(url1)
    assert result1 == "http://example.com"

    url2 = "http://example.com/"
    result2 = URLNormalizer.normalize_url(url2)
    assert result2 == "http://example.com/"


def test_normalize_url_file_extension() -> None:
    """Test URL normalization preserves file extensions."""
    url = "http://example.com/document.pdf"
    result = URLNormalizer.normalize_url(url)
    assert result == "http://example.com/document.pdf"

    url2 = "http://example.com/path/file.html?v=1"
    result2 = URLNormalizer.normalize_url(url2)
    assert ".html" in result2
    assert "?v=1" in result2


def test_normalize_url_consecutive_processing() -> None:
    """Test normalizing a URL multiple times yields same result (idempotent)."""
    url = "HTTP://Example.COM:80/Path?query=1#section"
    first_pass = URLNormalizer.normalize_url(url)
    second_pass = URLNormalizer.normalize_url(first_pass)
    third_pass = URLNormalizer.normalize_url(second_pass)

    assert first_pass == second_pass == third_pass
    assert first_pass == "http://example.com/Path?query=1"


def test_complete_url_processing_workflow() -> None:
    """Test complete URL processing workflow: normalize + filter + strip query."""
    raw_url = "HTTP://Example.COM:80/path?tracking=123&session=abc#top"

    # Step 1: Normalize
    normalized = URLNormalizer.normalize_url(raw_url)
    assert normalized == "http://example.com/path?tracking=123&session=abc"

    # Step 2: Filter dangerous schemes
    is_safe = URLNormalizer.filter_dangerous_schemes(normalized)
    assert is_safe is True

    # Step 3: Strip query parameters
    clean_url = URLNormalizer.handle_query_parameters(normalized, "strip")
    assert clean_url == "http://example.com/path"


def test_dangerous_url_workflow() -> None:
    """Test workflow rejects dangerous URLs early."""
    dangerous_urls = [
        "javascript:alert('xss')",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
    ]

    for url in dangerous_urls:
        # Filter should reject immediately
        is_safe = URLNormalizer.filter_dangerous_schemes(url)
        assert is_safe is False, f"URL should be rejected: {url}"


def test_url_normalization_for_deduplication() -> None:
    """Test URL normalization helps with deduplication."""
    # These URLs should all normalize to the same URL
    urls = [
        "http://example.com/page",
        "HTTP://EXAMPLE.COM/page",
        "http://example.com:80/page",
        "http://example.com/page#section1",
        "http://example.com/page#section2",
    ]

    normalized = [URLNormalizer.normalize_url(url) for url in urls]
    unique_normalized = set(normalized)

    # All should normalize to the same URL
    assert len(unique_normalized) == 1
    assert unique_normalized.pop() == "http://example.com/page"


def test_query_param_strategy_affects_deduplication() -> None:
    """Test query parameter strategy affects URL deduplication."""
    urls = [
        "http://example.com/page?a=1",
        "http://example.com/page?a=2",
        "http://example.com/page",
    ]

    # With strip strategy, all should become the same
    stripped = [URLNormalizer.handle_query_parameters(url, "strip") for url in urls]
    assert len(set(stripped)) == 1

    # With preserve strategy, all should be different
    preserved = [URLNormalizer.handle_query_parameters(url, "preserve") for url in urls]
    assert len(set(preserved)) == 3
