"""Tests for sitemap.xml parser."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from sus.exceptions import SitemapError
from sus.sitemap import SitemapEntry, SitemapParser

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sitemaps"


class TestSitemapEntry:
    """Tests for SitemapEntry dataclass."""

    def test_entry_with_all_fields(self) -> None:
        """Test creating entry with all fields."""
        lastmod = datetime(2024, 1, 15, 10, 30, 0)
        entry = SitemapEntry(
            loc="https://example.com/",
            lastmod=lastmod,
            changefreq="daily",
            priority=1.0,
        )
        assert entry.loc == "https://example.com/"
        assert entry.lastmod == lastmod
        assert entry.changefreq == "daily"
        assert entry.priority == 1.0

    def test_entry_minimal_fields(self) -> None:
        """Test creating entry with only required fields."""
        entry = SitemapEntry(loc="https://example.com/page")
        assert entry.loc == "https://example.com/page"
        assert entry.lastmod is None
        assert entry.changefreq is None
        assert entry.priority is None


class TestBasicParsing:
    """Tests for basic sitemap parsing."""

    @pytest.mark.asyncio
    async def test_parse_simple_sitemap(self, httpx_mock: HTTPXMock) -> None:
        """Test parsing a simple sitemap with 3 URLs."""
        sitemap_xml = (FIXTURES_DIR / "simple.xml").read_text()
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        assert len(entries) == 3
        assert entries[0].loc == "https://example.com/"
        assert entries[1].loc == "https://example.com/page1"
        assert entries[2].loc == "https://example.com/page2"

    @pytest.mark.asyncio
    async def test_parse_sitemap_with_all_fields(self, httpx_mock: HTTPXMock) -> None:
        """Test parsing sitemap with all optional fields."""
        sitemap_xml = (FIXTURES_DIR / "full-fields.xml").read_text()
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        assert len(entries) == 3

        # Check first entry with all fields
        entry1 = entries[0]
        assert entry1.loc == "https://example.com/"
        assert entry1.lastmod == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert entry1.changefreq == "daily"
        assert entry1.priority == 1.0

        # Check second entry
        entry2 = entries[1]
        assert entry2.loc == "https://example.com/docs"
        assert entry2.lastmod == datetime(2024, 1, 14, 8, 20, 0, tzinfo=UTC)
        assert entry2.changefreq == "weekly"
        assert entry2.priority == 0.8

        # Check third entry with date-only lastmod
        entry3 = entries[2]
        assert entry3.loc == "https://example.com/blog"
        assert entry3.lastmod is not None
        assert entry3.changefreq == "monthly"
        assert entry3.priority == 0.5

    @pytest.mark.asyncio
    async def test_parse_sitemap_no_namespace(self, httpx_mock: HTTPXMock) -> None:
        """Test parsing sitemap without XML namespace."""
        sitemap_xml = (FIXTURES_DIR / "no-namespace.xml").read_text()
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        assert len(entries) == 2
        assert entries[0].loc == "https://example.com/no-ns-1"
        assert entries[1].loc == "https://example.com/no-ns-2"
        assert entries[1].priority == 0.7

    @pytest.mark.asyncio
    async def test_parse_empty_sitemap(self, httpx_mock: HTTPXMock) -> None:
        """Test parsing empty sitemap returns empty list."""
        sitemap_xml = (FIXTURES_DIR / "empty.xml").read_text()
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_parse_large_sitemap(self, httpx_mock: HTTPXMock) -> None:
        """Test parsing large sitemap with 1000+ URLs."""
        sitemap_xml = (FIXTURES_DIR / "large.xml").read_text()
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        assert len(entries) == 1000
        assert entries[0].loc == "https://example.com/page1"
        assert entries[999].loc == "https://example.com/page1000"


class TestSitemapIndex:
    """Tests for sitemap index parsing."""

    @pytest.mark.asyncio
    async def test_parse_sitemap_index(self, httpx_mock: HTTPXMock) -> None:
        """Test parsing sitemap index with child sitemaps."""
        index_xml = (FIXTURES_DIR / "index.xml").read_text()
        httpx_mock.add_response(
            url="https://example.com/sitemap-index.xml",
            text=index_xml,
        )

        # Mock child sitemaps
        sitemap1_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/from-sitemap1</loc></url>
</urlset>"""
        sitemap2_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/from-sitemap2</loc></url>
</urlset>"""

        httpx_mock.add_response(url="https://example.com/sitemap1.xml", text=sitemap1_xml)
        httpx_mock.add_response(url="https://example.com/sitemap2.xml", text=sitemap2_xml)

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            entries = await parser.parse_sitemap("https://example.com/sitemap-index.xml")

        assert len(entries) == 2
        assert entries[0].loc == "https://example.com/from-sitemap1"
        assert entries[1].loc == "https://example.com/from-sitemap2"

    @pytest.mark.asyncio
    async def test_parse_nested_sitemap_index(self, httpx_mock: HTTPXMock) -> None:
        """Test parsing nested sitemap indexes (index containing index)."""
        parent_index = (FIXTURES_DIR / "nested-index.xml").read_text()
        httpx_mock.add_response(
            url="https://example.com/parent-index.xml",
            text=parent_index,
        )

        # Child index
        child_index_xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>https://example.com/nested-sitemap.xml</loc>
  </sitemap>
</sitemapindex>"""

        httpx_mock.add_response(
            url="https://example.com/sitemap-index-child.xml", text=child_index_xml
        )

        # Regular sitemap from child index
        nested_sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/nested-url</loc></url>
</urlset>"""

        httpx_mock.add_response(
            url="https://example.com/nested-sitemap.xml", text=nested_sitemap_xml
        )

        # Regular sitemap from parent index
        regular_sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/regular-url</loc></url>
</urlset>"""

        httpx_mock.add_response(
            url="https://example.com/sitemap-regular.xml", text=regular_sitemap_xml
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            entries = await parser.parse_sitemap("https://example.com/parent-index.xml")

        assert len(entries) == 2
        assert entries[0].loc == "https://example.com/nested-url"
        assert entries[1].loc == "https://example.com/regular-url"

    @pytest.mark.asyncio
    async def test_circular_reference_detection(self, httpx_mock: HTTPXMock) -> None:
        """Test circular reference detection in sitemap indexes."""
        # Index A points to Index B
        index_a_xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/index-b.xml</loc></sitemap>
</sitemapindex>"""

        # Index B points back to Index A (circular)
        index_b_xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/index-a.xml</loc></sitemap>
</sitemapindex>"""

        httpx_mock.add_response(url="https://example.com/index-a.xml", text=index_a_xml)
        httpx_mock.add_response(url="https://example.com/index-b.xml", text=index_b_xml)

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            # Should not hang, should detect circular reference and return empty
            entries = await parser.parse_sitemap("https://example.com/index-a.xml")

        # Circular reference detected, should return empty list
        assert len(entries) == 0


class TestCompression:
    """Tests for compressed sitemap parsing."""

    @pytest.mark.asyncio
    async def test_parse_gzipped_sitemap(self, httpx_mock: HTTPXMock) -> None:
        """Test parsing .xml.gz compressed sitemap."""
        compressed_content = (FIXTURES_DIR / "compressed.xml.gz").read_bytes()
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml.gz",
            content=compressed_content,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml.gz")

        assert len(entries) == 2
        assert entries[0].loc == "https://example.com/compressed1"
        assert entries[1].loc == "https://example.com/compressed2"

    @pytest.mark.asyncio
    async def test_malformed_gzip_non_strict(self, httpx_mock: HTTPXMock) -> None:
        """Test malformed gzip file in non-strict mode returns empty list."""
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml.gz",
            content=b"not a valid gzip file",
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client, strict=False)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml.gz")

        assert len(entries) == 0


class TestAutoDiscovery:
    """Tests for sitemap auto-discovery."""

    @pytest.mark.asyncio
    async def test_discover_from_robots_txt(self, httpx_mock: HTTPXMock) -> None:
        """Test discovering sitemaps from robots.txt."""
        robots_txt = """User-agent: *
Disallow: /admin/

Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap-news.xml
"""
        httpx_mock.add_response(url="https://example.com/robots.txt", text=robots_txt)
        httpx_mock.add_response(url="https://example.com/sitemap.xml", status_code=200)

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            sitemaps = await parser.discover_sitemaps("https://example.com")

        assert len(sitemaps) >= 2
        assert "https://example.com/sitemap.xml" in sitemaps
        assert "https://example.com/sitemap-news.xml" in sitemaps

    @pytest.mark.asyncio
    async def test_discover_from_default_location(self, httpx_mock: HTTPXMock) -> None:
        """Test discovering sitemap from default /sitemap.xml location."""
        httpx_mock.add_response(url="https://example.com/robots.txt", status_code=404)
        httpx_mock.add_response(url="https://example.com/sitemap.xml", status_code=200)

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            sitemaps = await parser.discover_sitemaps("https://example.com")

        assert len(sitemaps) == 1
        assert sitemaps[0] == "https://example.com/sitemap.xml"

    @pytest.mark.asyncio
    async def test_no_sitemaps_discovered(self, httpx_mock: HTTPXMock) -> None:
        """Test when no sitemaps are discovered."""
        httpx_mock.add_response(url="https://example.com/robots.txt", status_code=404)
        httpx_mock.add_response(url="https://example.com/sitemap.xml", status_code=404)

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            sitemaps = await parser.discover_sitemaps("https://example.com")

        assert len(sitemaps) == 0

    @pytest.mark.asyncio
    async def test_discover_handles_network_errors(self, httpx_mock: HTTPXMock) -> None:
        """Test auto-discovery handles network errors gracefully."""
        # Simulate network error for robots.txt
        httpx_mock.add_exception(
            httpx.ConnectError("Connection failed"), url="https://example.com/robots.txt"
        )
        # HEAD request for sitemap.xml also fails
        httpx_mock.add_exception(
            httpx.ConnectError("Connection failed"), url="https://example.com/sitemap.xml"
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client, strict=False)
            sitemaps = await parser.discover_sitemaps("https://example.com")

        # Should return empty list, not raise exception
        assert len(sitemaps) == 0


class TestErrorHandling:
    """Tests for error handling in sitemap parsing."""

    @pytest.mark.asyncio
    async def test_malformed_sitemap_strict_mode(self, httpx_mock: HTTPXMock) -> None:
        """Test malformed sitemap raises error in strict mode."""
        sitemap_xml = (FIXTURES_DIR / "malformed.xml").read_text()
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client, strict=True)
            with pytest.raises(SitemapError, match="Missing <loc> element"):
                await parser.parse_sitemap("https://example.com/sitemap.xml")

    @pytest.mark.asyncio
    async def test_malformed_sitemap_non_strict(self, httpx_mock: HTTPXMock) -> None:
        """Test malformed sitemap skips invalid entries in non-strict mode."""
        sitemap_xml = (FIXTURES_DIR / "malformed.xml").read_text()
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client, strict=False)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        # Should skip invalid entries, only return valid ones
        assert len(entries) >= 1
        assert entries[0].loc == "https://example.com/page1"

    @pytest.mark.asyncio
    async def test_http_error_strict_mode(self, httpx_mock: HTTPXMock) -> None:
        """Test HTTP error raises SitemapError in strict mode."""
        httpx_mock.add_response(url="https://example.com/sitemap.xml", status_code=404)

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client, strict=True)
            with pytest.raises(SitemapError, match="Failed to fetch"):
                await parser.parse_sitemap("https://example.com/sitemap.xml")

    @pytest.mark.asyncio
    async def test_http_error_non_strict(self, httpx_mock: HTTPXMock) -> None:
        """Test HTTP error returns empty list in non-strict mode."""
        httpx_mock.add_response(url="https://example.com/sitemap.xml", status_code=404)

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client, strict=False)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_invalid_xml_strict_mode(self, httpx_mock: HTTPXMock) -> None:
        """Test invalid XML raises SitemapError in strict mode."""
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text="<invalid>not closed",
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client, strict=True)
            with pytest.raises(SitemapError, match="Invalid XML"):
                await parser.parse_sitemap("https://example.com/sitemap.xml")

    @pytest.mark.asyncio
    async def test_invalid_xml_non_strict(self, httpx_mock: HTTPXMock) -> None:
        """Test invalid XML returns empty list in non-strict mode."""
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text="<invalid>not closed",
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client, strict=False)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_network_timeout_non_strict(self, httpx_mock: HTTPXMock) -> None:
        """Test network timeout returns empty list in non-strict mode."""
        httpx_mock.add_exception(
            httpx.ReadTimeout("Read timeout"), url="https://example.com/sitemap.xml"
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client, strict=False)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        assert len(entries) == 0


class TestFieldValidation:
    """Tests for field validation in sitemap entries."""

    @pytest.mark.asyncio
    async def test_invalid_priority_non_strict(self, httpx_mock: HTTPXMock) -> None:
        """Test invalid priority is ignored in non-strict mode."""
        sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/</loc>
    <priority>1.5</priority>
  </url>
</urlset>"""
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client, strict=False)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        assert len(entries) == 1
        # Invalid priority should be ignored (set to None)
        assert entries[0].priority is None

    @pytest.mark.asyncio
    async def test_valid_changefreq_values(self, httpx_mock: HTTPXMock) -> None:
        """Test all valid changefreq values are accepted."""
        valid_freqs = ["always", "hourly", "daily", "weekly", "monthly", "yearly", "never"]

        for freq in valid_freqs:
            sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/</loc>
    <changefreq>{freq}</changefreq>
  </url>
</urlset>"""
            httpx_mock.add_response(
                url=f"https://example.com/sitemap-{freq}.xml",
                text=sitemap_xml,
            )

            async with httpx.AsyncClient() as client:
                parser = SitemapParser(client)
                entries = await parser.parse_sitemap(f"https://example.com/sitemap-{freq}.xml")

            assert len(entries) == 1
            assert entries[0].changefreq == freq

    @pytest.mark.asyncio
    async def test_invalid_changefreq_non_strict(self, httpx_mock: HTTPXMock) -> None:
        """Test invalid changefreq is ignored in non-strict mode."""
        sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/</loc>
    <changefreq>sometimes</changefreq>
  </url>
</urlset>"""
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client, strict=False)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        assert len(entries) == 1
        assert entries[0].changefreq is None


class TestIntegrationWithCrawler:
    """Integration tests for sitemap parser with crawler."""

    @pytest.mark.asyncio
    async def test_priority_sorting(self, httpx_mock: HTTPXMock) -> None:
        """Test URLs can be sorted by priority field."""
        sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/low</loc>
    <priority>0.3</priority>
  </url>
  <url>
    <loc>https://example.com/high</loc>
    <priority>0.9</priority>
  </url>
  <url>
    <loc>https://example.com/medium</loc>
    <priority>0.5</priority>
  </url>
</urlset>"""
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        # Sort by priority (highest first)
        entries.sort(
            key=lambda e: e.priority if e.priority is not None else 0.5,
            reverse=True,
        )

        assert entries[0].loc == "https://example.com/high"
        assert entries[1].loc == "https://example.com/medium"
        assert entries[2].loc == "https://example.com/low"

    @pytest.mark.asyncio
    async def test_max_urls_limiting(self, httpx_mock: HTTPXMock) -> None:
        """Test limiting maximum URLs loaded from sitemap."""
        sitemap_xml = (FIXTURES_DIR / "large.xml").read_text()
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        # Apply max_urls limit
        max_urls = 100
        limited_entries = entries[:max_urls]

        assert len(limited_entries) == max_urls
        assert len(entries) == 1000  # Original unchanged

    @pytest.mark.asyncio
    async def test_url_deduplication(self, httpx_mock: HTTPXMock) -> None:
        """Test deduplicating URLs from multiple sitemaps."""
        sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
  <url><loc>https://example.com/page1</loc></url>
</urlset>"""
        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            text=sitemap_xml,
        )

        async with httpx.AsyncClient() as client:
            parser = SitemapParser(client)
            entries = await parser.parse_sitemap("https://example.com/sitemap.xml")

        # Extract URLs and deduplicate
        urls = [entry.loc for entry in entries]
        unique_urls = list(dict.fromkeys(urls))  # Preserve order

        assert len(urls) == 3  # Original has duplicates
        assert len(unique_urls) == 2  # Deduplicated
        assert unique_urls == ["https://example.com/page1", "https://example.com/page2"]
