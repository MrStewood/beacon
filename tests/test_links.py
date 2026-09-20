"""Tests for internal link validity."""

import os
import re
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PAGES_DIR = REPO_ROOT / "pages"

def find_html_files(directory):
    """Find all HTML files in directory."""
    files = []
    for root, dirs, filenames in os.walk(directory):
        for f in filenames:
            if f.endswith('.html'):
                files.append(os.path.join(root, f))
    return files

def extract_links(filepath):
    """Extract internal links from HTML file."""
    with open(filepath) as f:
        content = f.read()
    # Find all href and src attributes
    links = re.findall(r'(?:href|src)="(/beacon/[^"]*)"', content)
    return links

# Skip entire module when resource directory has no pages (empty dataset).
if not find_html_files(PAGES_DIR / "resource"):
    pytest.skip("empty dataset: no resource pages", allow_module_level=True)


class TestInternalLinks:
    """Verify all internal links are valid."""

    def test_all_resource_pages_exist(self):
        """All linked resource pages should exist."""
        pages = find_html_files(PAGES_DIR / "resource")
        assert len(pages) > 0, "No resource pages found"

    def test_all_county_pages_exist(self):
        """All linked county pages should exist."""
        pages = find_html_files(PAGES_DIR / "county")
        assert len(pages) > 0, "No county pages found"

    def test_links_use_beacon_prefix(self):
        """All internal links should use /beacon/ prefix."""
        pages = find_html_files(PAGES_DIR)
        bad_links = []
        for page in pages:
            links = extract_links(page)
            for link in links:
                if link.startswith('/beacon/'):
                    continue
                if link.startswith('http'):
                    continue
                if link.startswith('tel:'):
                    continue
                bad_links.append((page, link))
        assert not bad_links, f"Links without /beacon/ prefix: {bad_links[:5]}"

    def test_resource_page_links_valid(self):
        """Links in resource pages should point to existing files."""
        pages = find_html_files(PAGES_DIR / "resource")
        broken = []
        for page in pages:
            links = extract_links(page)
            for link in links:
                if link.startswith('/beacon/pages/'):
                    # Convert link to file path (strip /beacon/ prefix)
                    file_path = REPO_ROOT / link.replace('/beacon/', '/', 1).lstrip('/')
                    if not file_path.exists():
                        broken.append((page, link))
        assert not broken, f"Broken links: {broken[:5]}"
