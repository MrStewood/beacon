"""Tests for search accuracy and relevance."""

import json
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "data" / "resources.json"

# Import search logic from index.html (simplified Python equivalent)
STOP_WORDS = {'i','me','my','we','our','you','your','a','an','the','is','are','was','were','be','been','being','have','has','had','do','does','did','will','would','could','should','may','might','shall','can','need','to','of','in','for','on','with','at','by','from','as','into','through','during','before','after','above','below','between','out','off','over','under','again','further','then','once','please','thanks','thank','help','looking','find','want','near'}

PHRASE_MAP = {
    'food tonight':'food','tonight food':'food','hungry':'food','hungry tonight':'food',
    'meal':'food','eat':'food','dinner':'food','lunch':'food','pantry':'food',
    'place to sleep':'shelter','bed tonight':'shelter','sleep tonight':'shelter',
    'detox':'addiction','rehab':'addiction','sober living':'addiction',
    'therapy':'mental-health','counseling':'mental-health','depression':'mental-health',
    'electric bill':'utility','power bill':'utility','utility bill':'utility',
    'lawyer':'legal','attorney':'legal','legal help':'legal',
    'crisis':'crisis','hotline':'crisis','emergency':'crisis','suicide':'crisis',
}

WORD_MAP = {
    'hungry':'food','food':'food','meal':'food','eat':'food','pantry':'food',
    'sleep':'shelter','shelter':'shelter','bed':'shelter',
    'detox':'addiction','rehab':'addiction','sober':'addiction','recovery':'addiction',
    'therapy':'mental-health','counseling':'mental-health',
    'electric':'utility-assistance','power':'utility-assistance','utility':'utility-assistance',
    'lawyer':'legal','attorney':'legal','legal':'legal',
    'job':'jobs','employment':'jobs','work':'jobs',
    'crisis':'crisis','hotline':'crisis','emergency':'crisis','suicide':'crisis',
}

NEED_LABELS = {
    'addiction':'Addiction & Recovery','food':'Food & Water','shelter':'Shelter & Sleep',
    'mental-health':'Mental Health','legal':'Legal Help','crisis':'Crisis & Safety',
}


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


def search(resources, q):
    tokens = tokenize(q)
    if not tokens:
        return resources
    query_needs, query_words = expand_tokens(tokens)
    results = []
    for r in resources:
        score = 0
        name = (r.get('name', '') or '').lower()
        desc = (r.get('description', '') or '').lower()
        rneeds = r.get('needs', [])

        # Exact name match
        if all(t in name for t in tokens):
            score += 100

        # Need category match
        for n in query_needs:
            if n in rneeds:
                score += 50

        # Word match in name
        for w in query_words:
            if w in name:
                score += 30

        # Word match in description
        for w in query_words:
            if w in desc:
                score += 10

        # Fuzzy match on name words
        name_words = name.split()
        for w in query_words:
            for nw in name_words:
                if fuzzy_word(w, nw):
                    score += 5

        if score > 0:
            results.append((r, score))

    results.sort(key=lambda x: -x[1])
    return [r for r, s in results]


@pytest.fixture
def resources():
    with open(DATA_PATH) as f:
        return json.load(f)["resources"]


class TestSearchAccuracy:
    """Verify search returns relevant results, not overmatches."""

    def test_food_tonight_returns_food(self, resources):
        """'food tonight' should return food resources, not everything."""
        results = search(resources, 'food tonight')
        assert len(results) < 50, f"Too many results: {len(results)}"
        for r in results[:10]:
            assert 'food' in r.get('needs', []), f"Non-food resource in results: {r['name']} needs={r.get('needs')}"

    def test_place_to_sleep_returns_shelter(self, resources):
        """'place to sleep' should return shelter resources."""
        results = search(resources, 'place to sleep')
        assert len(results) < 30, f"Too many results: {len(results)}"
        for r in results[:5]:
            needs = r.get('needs', [])
            assert 'shelter' in needs or 'housing' in needs, f"Non-shelter resource: {r['name']} needs={needs}"

    def test_detox_returns_addiction(self, resources):
        """'detox' should return addiction-treatment resources."""
        results = search(resources, 'detox')
        assert len(results) > 0, "No results for detox"
        for r in results[:5]:
            assert 'addiction' in r.get('needs', []), f"Non-addiction resource: {r['name']}"

    def test_lawyer_returns_legal(self, resources):
        """'lawyer' should return legal resources."""
        results = search(resources, 'lawyer')
        assert len(results) > 0, "No results for lawyer"
        for r in results[:5]:
            assert 'legal' in r.get('needs', []), f"Non-legal resource: {r['name']}"

    def test_988_returns_lifeline(self, resources):
        """'988' should return the 988 Lifeline."""
        results = search(resources, '988')
        assert len(results) > 0, "No results for 988"
        names = [r['name'].lower() for r in results[:3]]
        assert any('988' in n for n in names), f"988 Lifeline not in top results: {names}"

    def test_long_description_no_overmatch(self, resources):
        """A search with common words should not return most resources."""
        results = search(resources, 'I need food')
        assert len(results) < 50, f"Overmatching on 'I need food': {len(results)} results"

    def test_misspelled_name_still_found(self, resources):
        """A misspelled organization name can still be found via fuzzy match."""
        results = search(resources, 'cumbrland river')
        # Should find Cumberland River resources via fuzzy matching
        found = any('cumberland' in r['name'].lower() for r in results[:5])
        assert found, "Misspelled 'cumbrland' should still find Cumberland River"

    def test_unrelated_no_match(self, resources):
        """Unrelated query should not match unrelated resources."""
        results = search(resources, 'emergency shelter')
        # Should only return shelter/crisis resources
        for r in results[:10]:
            needs = r.get('needs', [])
            has_relevant = any(n in needs for n in ['shelter', 'housing', 'crisis'])
            assert has_relevant, f"Unrelated resource: {r['name']} needs={needs}"
