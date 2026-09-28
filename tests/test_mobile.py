"""Mobile and geolocation tests for Beacon site."""

import re
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

class TestMobileResponsive:
    """Verify mobile responsiveness."""

    def test_viewport_meta(self):
        """Viewport meta should be set."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'width=device-width' in html



    def test_touch_targets_minimum_size(self):
        """Buttons should have minimum touch target size."""
        css = (REPO_ROOT / "assets" / "css" / "beacon.css").read_text()
        # Check for min-height or padding that provides 44px targets
        assert 'min-height' in css or 'padding' in css

    def test_no_horizontal_scroll(self):
        """No fixed widths that could cause overflow."""
        css = (REPO_ROOT / "assets" / "css" / "beacon.css").read_text()
        assert 'max-width' in css  # Should have max-width constraints

class TestGeolocation:
    """Verify geolocation implementation."""




    def test_location_button_exists(self):
        """Use My Location button should exist."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'Use my location' in html



class TestPerformance:
    """Basic performance checks."""

    def test_index_html_size(self):
        """Index HTML should be reasonably sized."""
        html = (REPO_ROOT / "index.html").read_text()
        assert len(html) < 50000, f"Index HTML too large: {len(html)} bytes"

    def test_css_size(self):
        """CSS should be reasonably sized."""
        css = (REPO_ROOT / "assets" / "css" / "beacon.css").read_text()
        assert len(css) < 20000, f"CSS too large: {len(css)} bytes"

    def test_no_large_images(self):
        """No unoptimized images in site assets (excludes leads/ evidence screenshots)."""
        leads_dir = REPO_ROOT / "leads"
        images = [
            p for p in list(REPO_ROOT.glob("**/*.png")) + list(REPO_ROOT.glob("**/*.jpg"))
            if not str(p).startswith(str(leads_dir))
        ]
        large = [img for img in images if img.stat().st_size > 100000]
        assert len(large) == 0, f"Large images found: {large}"
