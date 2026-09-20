"""Accessibility tests for Beacon site."""

import re
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

class TestAccessibility:
    """Verify accessibility requirements."""

    def test_skip_link_exists(self):
        """Skip link should be present."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'skip-link' in html, "Missing skip link"

    def test_aria_labels_on_nav(self):
        """Navigation should have aria-label."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'aria-label="Main navigation"' in html

    def test_aria_live_on_results(self):
        """Results count should have aria-live."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'aria-live="polite"' in html

    def test_aria_pressed_on_chips(self):
        """Need chips should have aria-pressed."""
        js = (REPO_ROOT / "assets" / "js" / "app.js").read_text()
        assert 'aria-pressed' in js

    def test_form_labels_exist(self):
        """Form inputs should have labels."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'for="search-input"' in html
        assert 'for="location-input"' in html
        assert 'for="county-select"' in html

    def test_resource_names_are_links(self):
        """Resource names should link to detail pages."""
        js = (REPO_ROOT / "assets" / "js" / "app.js").read_text()
        assert 'pages/resource/' in js

    def test_emergency_has_role_alert(self):
        """Emergency banner should have role=alert."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'role="alert"' in html

    def test_pagination_has_aria_current(self):
        """Pagination should use aria-current."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'aria-current="page"' in html or 'aria-current' in html

    def test_resource_page_has_main(self):
        """Resource pages should have main element."""
        pages = list((REPO_ROOT / "pages" / "resource").glob("*.html"))
        assert len(pages) > 0
        html = pages[0].read_text()
        assert '<main' in html

    def test_resource_page_has_heading(self):
        """Resource names should be headings."""
        pages = list((REPO_ROOT / "pages" / "resource").glob("*.html"))
        html = pages[0].read_text()
        assert '<h1' in html

    def test_external_links_have_rel(self):
        """External links should have rel=noopener."""
        html = (REPO_ROOT / "index.html").read_text()
        # Find all anchor tags with target="_blank"
        tags = re.findall(r'<a[^>]*href="https?://[^"]*"[^>]*target="_blank"[^>]*>', html)
        for tag in tags:
            assert 'rel="noopener' in tag, f"Missing rel=noopener: {tag}"

    def test_meta_viewport(self):
        """Pages should have viewport meta."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'viewport' in html

    def test_lang_attribute(self):
        """HTML should have lang attribute."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'lang="en"' in html
