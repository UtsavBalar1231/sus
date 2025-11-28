"""Benchmark fixtures for deterministic, repeatable performance tests.

All fixtures generate data programmatically - no external dependencies.
"""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sus.config import (
    CrawlingRules,
    MarkdownConfig,
    OutputConfig,
    PathMappingConfig,
    PathPattern,
    SiteConfig,
    SusConfig,
)


@pytest.fixture
def small_html() -> str:
    """1KB minimal HTML page."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Small Page</title>
</head>
<body>
    <h1>Title</h1>
    <p>This is a small page with minimal content for benchmark testing.</p>
    <a href="/page1">Link 1</a>
    <a href="/page2">Link 2</a>
    <a href="/page3">Link 3</a>
</body>
</html>"""


@pytest.fixture
def medium_html() -> str:
    """~10KB documentation page with typical structure."""
    links = "\n".join(f'        <li><a href="/docs/page{i}">Page {i}</a></li>' for i in range(100))
    paragraphs = "\n".join(
        f"    <p>Paragraph {i} with some content about documentation and APIs. "
        f"This text provides realistic content length for benchmarking purposes.</p>"
        for i in range(50)
    )
    code_blocks = "\n".join(
        f"""    <pre><code class="language-python">
def function_{i}():
    '''Example function {i}.'''
    return {i} * 2
</code></pre>"""
        for i in range(10)
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Documentation Page</title>
    <link rel="stylesheet" href="/css/style.css">
</head>
<body>
    <main>
        <article>
            <h1>Documentation</h1>
            <nav>
                <ul>
{links}
                </ul>
            </nav>
            <section>
                <h2>Introduction</h2>
{paragraphs}
            </section>
            <section>
                <h2>Code Examples</h2>
{code_blocks}
            </section>
        </article>
    </main>
</body>
</html>"""


@pytest.fixture
def large_html() -> str:
    """~100KB large documentation page."""
    links = "\n".join(f'        <li><a href="/docs/page{i}">Page {i}</a></li>' for i in range(500))
    paragraphs = "\n".join(
        f"    <p>Paragraph {i} with extensive content about documentation, APIs, "
        f"and software development best practices. This text provides realistic "
        f"content length for benchmarking large page processing. Lorem ipsum dolor "
        f"sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt.</p>"
        for i in range(200)
    )
    code_blocks = "\n".join(
        f"""    <pre><code class="language-python">
class Example{i}:
    '''Example class {i} for testing.'''

    def __init__(self, value: int) -> None:
        self.value = value

    def process(self) -> int:
        '''Process the value.'''
        return self.value * {i}

    def __repr__(self) -> str:
        return f"Example{i}(value={{self.value}})"
</code></pre>"""
        for i in range(50)
    )
    tables = "\n".join(
        f"""    <table>
        <caption>Table {i}</caption>
        <thead><tr><th>Column A</th><th>Column B</th><th>Column C</th></tr></thead>
        <tbody>
            <tr><td>Row {i}.1</td><td>Value A</td><td>100</td></tr>
            <tr><td>Row {i}.2</td><td>Value B</td><td>200</td></tr>
            <tr><td>Row {i}.3</td><td>Value C</td><td>300</td></tr>
        </tbody>
    </table>"""
        for i in range(20)
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Large Documentation Page</title>
    <link rel="stylesheet" href="/css/style.css">
    <script src="/js/app.js"></script>
</head>
<body>
    <main>
        <article>
            <h1>Comprehensive Documentation</h1>
            <nav>
                <h2>Navigation</h2>
                <ul>
{links}
                </ul>
            </nav>
            <section>
                <h2>Content</h2>
{paragraphs}
            </section>
            <section>
                <h2>Code Examples</h2>
{code_blocks}
            </section>
            <section>
                <h2>Data Tables</h2>
{tables}
            </section>
        </article>
    </main>
</body>
</html>"""


@pytest.fixture
def spa_shell_html() -> str:
    """SPA shell with React root, minimal content."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>React App</title>
</head>
<body>
    <div id="root"></div>
    <noscript>Please enable JavaScript to use this application.</noscript>
    <script src="/static/js/bundle.js"></script>
</body>
</html>"""


@pytest.fixture
def vue_shell_html() -> str:
    """Vue.js SPA shell."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Vue App</title>
</head>
<body>
    <div id="app" data-v-app></div>
    <noscript>JavaScript is required for this application.</noscript>
    <script src="/js/app.js"></script>
</body>
</html>"""


@pytest.fixture
def loading_page_html() -> str:
    """Page with loading indicators."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Loading</title>
</head>
<body>
    <div class="loading">
        <div class="spinner"></div>
        <p>Loading...</p>
    </div>
</body>
</html>"""


@pytest.fixture
def sample_urls() -> list[str]:
    """100 URLs for normalization benchmarks."""
    return [f"HTTP://Example.COM:80/path/{i}?query=value&b={i}#fragment{i}" for i in range(100)]


@pytest.fixture
def sample_paths() -> list[str]:
    """100 paths for pattern matching benchmarks."""
    return [f"/docs/api/v{i % 3}/endpoint{i}.html" for i in range(100)]


@pytest.fixture
def sample_config(tmp_path: Path) -> SusConfig:
    """Standard config for benchmark tests."""
    return SusConfig(
        name="benchmark-test",
        site=SiteConfig(
            start_urls=["http://example.com/docs/"],
            allowed_domains=["example.com"],
        ),
        crawling=CrawlingRules(
            include_patterns=[
                PathPattern(pattern="^/docs/", type="regex"),
            ],
            exclude_patterns=[
                PathPattern(pattern="*.pdf", type="glob"),
                PathPattern(pattern="/api/", type="prefix"),
            ],
            delay_between_requests=0,
            global_concurrent_requests=50,
            per_domain_concurrent_requests=10,
            respect_robots_txt=False,
        ),
        output=OutputConfig(
            base_dir=str(tmp_path),
            path_mapping=PathMappingConfig(),
            markdown=MarkdownConfig(),
        ),
    )


@pytest.fixture
def markdown_config() -> MarkdownConfig:
    """Standard markdown config for converter benchmarks."""
    return MarkdownConfig(
        add_frontmatter=True,
        frontmatter_fields=["title", "url", "scraped_at"],
    )
