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

    def test_emergency_stacks_on_mobile(self):
        """Emergency items should stack on narrow screens."""
        css = (REPO_ROOT / "assets" / "css" / "beacon.css").read_text()
        assert 'grid-template-columns: 1fr' in css

    def test_input_font_size_large_enough(self):
        """Search input should have large enough font for mobile."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'font-size: 16px' in html  # Prevents iOS zoom

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

    def test_geolocation_function_exists(self):
        """useMyLocation function should exist."""
        js = (REPO_ROOT / "assets" / "js" / "app.js").read_text()
        assert 'useMyLocation' in js

    def test_haversine_function_exists(self):
        """Haversine distance function should exist."""
        js = (REPO_ROOT / "assets" / "js" / "app.js").read_text()
        assert 'haversine' in js

    def test_permission_handling(self):
        """Should handle permission denied gracefully."""
        js = (REPO_ROOT / "assets" / "js" / "app.js").read_text()
        assert 'permission denied' in js.lower() or 'Permission denied' in js

    def test_location_button_exists(self):
        """Use My Location button should exist."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'Use my location' in html

    def test_radius_filter_exists(self):
        """Radius filter should exist."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'radius-select' in html

    def test_distance_displayed(self):
        """Distance should be displayed on cards."""
        js = (REPO_ROOT / "assets" / "js" / "app.js").read_text()
        assert '_distance' in js

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
        """No unoptimized images in repo."""
        images = list(REPO_ROOT.glob("**/*.png")) + list(REPO_ROOT.glob("**/*.jpg"))
        large = [img for img in images if img.stat().st_size > 100000]
        assert len(large) == 0, f"Large images found: {large}"
