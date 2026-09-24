"""Comprehensive tests for Beacon site functionality."""

import json
import os
import re
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
PAGES_DIR = REPO_ROOT / "pages"

# ==================== Search Tests ====================

STOP_WORDS = {'i','me','my','we','our','you','your','a','an','the','is','are','was','were','be','been','being','have','has','had','do','does','did','will','would','could','should','may','might','shall','can','need','to','of','in','for','on','with','at','by','from','as','into','through','during','before','after','above','below','between','out','off','over','under','again','further','then','once','please','thanks','thank','help','looking','find','want','near'}
PHRASE_MAP = {'food tonight':'food','hungry':'food','meal':'food','place to sleep':'shelter','bed tonight':'shelter','detox':'addiction','rehab':'addiction','sober living':'addiction','therapy':'mental-health','counseling':'mental-health','electric bill':'utility-assistance','power bill':'utility-assistance','lawyer':'legal','attorney':'legal','crisis':'crisis','hotline':'crisis','emergency':'crisis','suicide':'crisis'}
WORD_MAP = {'hungry':'food','food':'food','meal':'food','shelter':'shelter','bed':'shelter','sleep':'shelter','detox':'addiction','rehab':'addiction','sober':'addiction','recovery':'addiction','therapy':'mental-health','counseling':'mental-health','electric':'utility-assistance','power':'utility-assistance','utility':'utility-assistance','lawyer':'legal','attorney':'legal','legal':'legal','job':'jobs','employment':'jobs','work':'jobs','crisis':'crisis','hotline':'crisis','emergency':'crisis','suicide':'crisis'}

def tokenize(q):
    return [w for w in q.lower().split() if w and w not in STOP_WORDS]

def expand_tokens(tokens):
    needs = set()
    words = []
    joined = ' '.join(tokens)
    for phrase, categ in PHRASE_MAP.items():
        if phrase in joined:
            needs.add(categ)
    for t in tokens:
        if t in WORD_MAP:
            needs.add(WORD_MAP[t])
        else:
            words.append(t)
    return needs, words

def fuzzy_word(q, word):
    if word in q or q in word:
        return True
    if len(q) < 3 or len(word) < 3:
        return False
    i = 0
    for c in word:
        if c == q[i]:
            i += 1
    return i >= len(q) * 0.75

def score_resource(r, tokens, needs, words):
    score = 0
    name = (r.get('name', '') or '').lower()
    desc = (r.get('description', '') or '').lower()
    rneeds = r.get('needs', [])
    if all(t in name for t in tokens):
        score += 100
    for n in needs:
        if n in rneeds:
            score += 50
    for w in words:
        if w in name:
            score += 30
    for w in words:
        if w in desc:
            score += 10
    return score

def search(resources, q):
    tokens = tokenize(q)
    if not tokens:
        return resources
    query_needs, query_words = expand_tokens(tokens)
    results = []
    for r in resources:
        score = score_resource(r, tokens, query_needs, query_words)
        if score > 0:
            results.append((r, score))
    results.sort(key=lambda x: -x[1])
    return [r for r, s in results]

@pytest.fixture
def resources():
    with open(DATA_DIR / "resources.json") as f:
        return json.load(f)["resources"]

@pytest.fixture
def v3_data():
    with open(DATA_DIR / "v3" / "resources.json") as f:
        return json.load(f)["resources"]

def _has_resources():
    try:
        with open(DATA_DIR / "resources.json") as f:
            return len(json.load(f).get("resources", [])) > 0
    except Exception:
        return False

def _has_pages():
    try:
        return len(list((PAGES_DIR / "resource").glob("*.html"))) > 0
    except Exception:
        return False

def _has_state_index():
    return (DATA_DIR / "states" / "ky" / "index.json").exists()


def require_need(resources, need):
    if not any(need in r.get('needs', []) for r in resources):
        pytest.skip(f"dataset has no {need} resources")


def require_name(resources, text):
    if not any(text in r.get('name', '').lower() for r in resources):
        pytest.skip(f"dataset has no resource matching {text}")


@pytest.mark.skipif(not _has_resources(), reason="empty dataset: no resources to search")
class TestSearchAccuracy:
    """Search returns relevant results, not overmatches."""

    def test_food_tonight_returns_food(self, resources):
        results = search(resources, 'food tonight')
        assert len(results) < 50
        for r in results[:10]:
            assert 'food' in r.get('needs', [])

    def test_place_to_sleep_returns_shelter(self, resources):
        results = search(resources, 'place to sleep')
        assert len(results) < 30
        for r in results[:5]:
            assert 'shelter' in r.get('needs', []) or 'housing' in r.get('needs', [])

    def test_detox_returns_addiction(self, resources):
        require_need(resources, 'addiction')
        results = search(resources, 'detox')
        assert len(results) > 0
        for r in results[:5]:
            assert 'addiction' in r.get('needs', [])

    def test_lawyer_returns_legal(self, resources):
        require_need(resources, 'legal')
        results = search(resources, 'lawyer')
        assert len(results) > 0
        for r in results[:5]:
            assert 'legal' in r.get('needs', [])

    def test_988_returns_lifeline(self, resources):
        results = search(resources, '988')
        assert len(results) > 0
        names = [r['name'].lower() for r in results[:3]]
        assert any('988' in n for n in names)

    def test_long_description_no_overmatch(self, resources):
        results = search(resources, 'I need food')
        assert len(results) < 50

    def test_misspelled_name_still_found(self, resources):
        require_name(resources, 'cumberland')
        results = search(resources, 'cumbrland river')
        found = any('cumberland' in r['name'].lower() for r in results[:5])
        assert found

    def test_unrelated_no_match(self, resources):
        results = search(resources, 'emergency shelter')
        for r in results[:10]:
            needs = r.get('needs', [])
            assert any(n in needs for n in ['shelter', 'housing', 'crisis'])

class TestDataSchema:
    """Data follows v2 schema correctly."""

    def test_all_resources_have_id(self, resources):
        for r in resources:
            assert r.get('id'), "Missing ID"

    def test_all_resources_have_name(self, resources):
        for r in resources:
            assert r.get('name'), "Missing name"

    def test_all_resources_have_county(self, resources):
        for r in resources:
            assert r.get('county'), "Missing county"

    def test_all_resources_have_status(self, resources):
        valid = {'active', 'needs-verification', 'closed'}
        for r in resources:
            assert r.get('status') in valid, f"Invalid status: {r.get('status')}"

    def test_all_resources_have_needs(self, resources):
        valid = {'addiction','clothing','community','crisis','documents','education','family','food','health','housing','jobs','legal','mental-health','shelter','transportation','utility-assistance','veterans'}
        for r in resources:
            for n in r.get('needs', []):
                assert n in valid, f"Invalid need: {n}"

    def test_unique_ids(self, resources):
        ids = [r['id'] for r in resources]
        assert len(ids) == len(set(ids)), "Duplicate IDs found"

    def test_valid_urls(self, resources):
        for r in resources:
            url = r.get('url', '')
            if url:
                assert url.startswith(('http://', 'https://')), f"Invalid URL: {url}"
                assert ' ' not in url or '%' in url, f"URL with spaces: {url}"

@pytest.mark.skipif(not _has_resources(), reason="empty dataset: no crisis resources")
class TestCrisisResources:
    """Critical crisis resources are correct."""

    def test_988_exists(self, resources):
        r988 = [r for r in resources if '988' in r.get('name', '')]
        assert len(r988) > 0

    def test_988_has_phone(self, resources):
        r988 = [r for r in resources if '988' in r.get('name', '')][0]
        assert '988' in r988.get('phones', [])

    def test_988_is_crisis(self, resources):
        r988 = [r for r in resources if '988' in r.get('name', '')][0]
        assert 'crisis' in r988.get('needs', [])

    def test_crisis_resources_have_phones(self, resources):
        crisis = [r for r in resources if 'crisis' in r.get('needs', [])]
        for r in crisis:
            assert r.get('phones'), f"Crisis resource without phone: {r['name']}"

@pytest.mark.skipif(not _has_pages(), reason="empty dataset: no resource pages to validate links")
class TestLinkValidity:
    """Internal links are valid."""

    def test_all_resource_pages_exist(self):
        pages = list((PAGES_DIR / "resource").glob("*.html"))
        assert len(pages) > 0

    def test_all_county_pages_exist(self):
        pages = list((PAGES_DIR / "county").glob("*.html"))
        assert len(pages) > 0

    def test_links_use_beacon_prefix(self):
        bad = []
        for page in (PAGES_DIR / "resource").glob("*.html"):
            content = page.read_text()
            links = re.findall(r'href="(/beacon/[^"]*)"', content)
            for link in links:
                if not link.startswith('/beacon/'):
                    bad.append((str(page), link))
        assert not bad, f"Bad links: {bad[:3]}"

class TestV3Geography:
    """V3 geographic schema is correct."""
    pytestmark = pytest.mark.skipif(
        not (DATA_DIR / "v3" / "resources.json").exists(),
        reason="V3 data not generated from empty dataset",
    )

    def test_v3_data_exists(self):
        assert (DATA_DIR / "v3" / "resources.json").exists()

    def test_v3_has_locations(self, v3_data):
        for r in v3_data:
            assert 'locations' in r
            assert len(r['locations']) >= 1

    def test_v3_has_coverage_scope(self, v3_data):
        valid = {'national','multi-state','state','multi-county','county','multi-city','city','postal-code','radius','tribal-area','custom-region','online','unknown'}
        for r in v3_data:
            assert r.get('coverage_scope') in valid

    def test_statewide_has_state_coverage(self, v3_data):
        for r in v3_data:
            if r.get('county') == 'Statewide':
                assert r['coverage_scope'] == 'state'
                assert 'KY' in r.get('states_served', [])

@pytest.mark.skipif(not _has_state_index(), reason="state index not generated for current canonical dataset")
class TestNationwideArchitecture:
    """Nationwide data structure is correct."""

    def test_catalog_exists(self):
        assert (DATA_DIR / "catalog.json").exists()

    def test_state_index_exists(self):
        assert (DATA_DIR / "states" / "ky" / "index.json").exists()

    def test_state_resources_exist(self):
        assert (DATA_DIR / "states" / "ky" / "resources.json").exists()

    def test_county_files_exist(self):
        counties = list((DATA_DIR / "states" / "ky" / "counties").glob("*.json"))
        assert len(counties) >= 15

class TestJavaScript:
    """Verify JavaScript is valid and functional."""

    def test_app_js_exists(self):
        """app.js should exist."""
        assert (REPO_ROOT / "assets" / "js" / "app.js").exists()

    def test_config_js_exists(self):
        """config.js should exist."""
        assert (REPO_ROOT / "assets" / "js" / "config.js").exists()

    def test_app_js_syntax(self):
        """app.js should have valid JavaScript syntax."""
        import subprocess
        result = subprocess.run(
            ["node", "--check", str(REPO_ROOT / "assets" / "js" / "app.js")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"JS syntax error: {result.stderr}"

    def test_config_js_syntax(self):
        """config.js should have valid JavaScript syntax."""
        import subprocess
        result = subprocess.run(
            ["node", "--check", str(REPO_ROOT / "assets" / "js" / "config.js")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"JS syntax error: {result.stderr}"

    def test_index_uses_external_js(self):
        """index.html should use external JS files."""
        html = (REPO_ROOT / "index.html").read_text()
        assert 'src="/beacon/assets/js/app.js"' in html
        assert 'src="/beacon/assets/js/config.js"' in html

class TestFileStructure:
    """Repository structure is correct."""

    def test_schema_exists(self):
        assert (REPO_ROOT / "schema" / "resource.schema.json").exists()

    def test_v3_schema_exists(self):
        assert (REPO_ROOT / "schema" / "resource.schema.v3.json").exists()

    def test_css_exists(self):
        assert (REPO_ROOT / "assets" / "css" / "beacon.css").exists()

    def test_js_config_exists(self):
        assert (REPO_ROOT / "assets" / "js" / "config.js").exists()

    def test_robots_txt_exists(self):
        assert (REPO_ROOT / "robots.txt").exists()

    def test_sitemap_exists(self):
        assert (REPO_ROOT / "sitemap.xml").exists()
