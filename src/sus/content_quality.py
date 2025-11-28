"""Content quality analysis for HTTP-first smart routing.

Analyzes HTML content to determine if JavaScript rendering is needed.
HTTP fetching is 10-50x faster than JS rendering, so we prefer HTTP
and only fall back to JS when content quality is insufficient.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from lxml import html

if TYPE_CHECKING:
    from lxml.html import HtmlElement


@dataclass
class ContentQuality:
    """Assessment of HTML content quality from HTTP fetch.

    Used to decide whether JavaScript rendering is needed for full content.
    """

    text_length: int
    link_count: int
    heading_count: int
    paragraph_count: int
    has_main_content: bool
    has_article: bool
    has_loading_indicators: bool
    has_noscript_warning: bool
    has_react_root: bool
    has_vue_app: bool
    has_angular_app: bool

    @property
    def needs_js(self) -> bool:
        """Heuristic: returns True if JS rendering is likely needed.

        Conservative approach - only trigger JS rendering when confident
        that HTTP content is insufficient.
        """
        # Explicit noscript warnings indicate JS is required
        if self.has_noscript_warning:
            return True

        # Loading indicators with minimal content suggest SPA shell
        if self.has_loading_indicators and self.text_length < 500:
            return True

        # SPA framework markers with minimal rendered content
        is_spa_shell = self.has_react_root or self.has_vue_app or self.has_angular_app
        if is_spa_shell and self.text_length < 300 and self.paragraph_count < 2:
            return True

        # Very thin content - likely client-side rendered
        return self.text_length < 100 and self.link_count < 3 and self.heading_count == 0

    @property
    def quality_score(self) -> float:
        """Content quality score from 0.0 (empty) to 1.0 (excellent).

        Higher scores indicate more complete content from HTTP fetch.
        """
        score = 0.0

        # Text length contribution (max 0.4)
        if self.text_length >= 2000:
            score += 0.4
        elif self.text_length >= 500:
            score += 0.3
        elif self.text_length >= 100:
            score += 0.1

        # Structure contribution (max 0.3)
        if self.has_main_content or self.has_article:
            score += 0.15
        if self.heading_count >= 3:
            score += 0.15
        elif self.heading_count >= 1:
            score += 0.1

        # Content richness (max 0.3)
        if self.paragraph_count >= 5:
            score += 0.15
        elif self.paragraph_count >= 2:
            score += 0.1
        if self.link_count >= 5:
            score += 0.15
        elif self.link_count >= 2:
            score += 0.1

        return min(1.0, score)


# Patterns for detecting loading indicators
LOADING_PATTERNS = [
    r"loading\.{0,3}",
    r"please wait",
    r"spinner",
    r"skeleton",
    r"initializing",
    r"fetching",
]
LOADING_REGEX = re.compile("|".join(LOADING_PATTERNS), re.IGNORECASE)

# Patterns for noscript warnings
NOSCRIPT_WARNING_PATTERNS = [
    r"javascript.*required",
    r"enable.*javascript",
    r"javascript.*disabled",
    r"browser.*not.*support",
    r"please.*enable.*js",
]
NOSCRIPT_REGEX = re.compile("|".join(NOSCRIPT_WARNING_PATTERNS), re.IGNORECASE)


class ContentQualityAnalyzer:
    """Analyzes HTML content quality to determine if JS rendering is needed."""

    @staticmethod
    def analyze(html_content: str) -> ContentQuality:
        """Analyze HTML content and return quality assessment.

        Args:
            html_content: Raw HTML string from HTTP fetch

        Returns:
            ContentQuality dataclass with analysis results
        """
        if not html_content or not html_content.strip():
            return ContentQuality(
                text_length=0,
                link_count=0,
                heading_count=0,
                paragraph_count=0,
                has_main_content=False,
                has_article=False,
                has_loading_indicators=False,
                has_noscript_warning=False,
                has_react_root=False,
                has_vue_app=False,
                has_angular_app=False,
            )

        try:
            tree = cast("HtmlElement", html.fromstring(html_content))
        except Exception:
            # If HTML parsing fails, assume JS needed
            return ContentQuality(
                text_length=0,
                link_count=0,
                heading_count=0,
                paragraph_count=0,
                has_main_content=False,
                has_article=False,
                has_loading_indicators=True,
                has_noscript_warning=False,
                has_react_root=False,
                has_vue_app=False,
                has_angular_app=False,
            )

        # Extract visible text (excluding scripts/styles)
        text_content = tree.text_content() or ""
        text_length = len(text_content.strip())

        # Count structural elements
        links = tree.cssselect("a[href]")
        headings = tree.cssselect("h1, h2, h3, h4, h5, h6")
        paragraphs = tree.cssselect("p")

        # Check for semantic containers
        main_elements = tree.cssselect("main, [role='main']")
        article_elements = tree.cssselect("article")

        # Detect loading indicators
        has_loading = bool(LOADING_REGEX.search(html_content[:5000]))

        # Check noscript content for warnings
        noscript_elements = tree.cssselect("noscript")
        has_noscript_warning = False
        for noscript in noscript_elements:
            noscript_text = noscript.text_content() or ""
            if NOSCRIPT_REGEX.search(noscript_text):
                has_noscript_warning = True
                break

        # Detect SPA framework markers
        has_react = bool(tree.cssselect("#root, #__next, [data-reactroot]"))
        has_vue = bool(tree.cssselect("#app[data-v-], [data-v-app]"))
        has_angular = bool(tree.cssselect("[ng-version], [_ngcontent-]"))

        return ContentQuality(
            text_length=text_length,
            link_count=len(links),
            heading_count=len(headings),
            paragraph_count=len(paragraphs),
            has_main_content=len(main_elements) > 0,
            has_article=len(article_elements) > 0,
            has_loading_indicators=has_loading,
            has_noscript_warning=has_noscript_warning,
            has_react_root=has_react,
            has_vue_app=has_vue,
            has_angular_app=has_angular,
        )

    @staticmethod
    def should_retry_with_js(
        http_quality: ContentQuality,
        *,
        min_quality_score: float = 0.3,
        force_js_domains: set[str] | None = None,
        domain: str | None = None,
    ) -> bool:
        """Determine if a page should be retried with JavaScript rendering.

        Args:
            http_quality: Quality assessment from HTTP fetch
            min_quality_score: Minimum acceptable quality score (0.0-1.0)
            force_js_domains: Domains known to require JS rendering
            domain: Current page domain for force_js check

        Returns:
            True if JS rendering should be attempted
        """
        # Check domain override
        if force_js_domains and domain and domain in force_js_domains:
            return True

        # Use heuristic assessment or check quality score threshold
        return http_quality.needs_js or http_quality.quality_score < min_quality_score
