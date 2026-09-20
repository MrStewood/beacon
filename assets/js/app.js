/**
 * Beacon — Main Application JavaScript
 * Nocturne Design System
 */

/* global BEACON_CONFIG */

const NL = BEACON_CONFIG.needs;
const PL = BEACON_CONFIG.populations;
const SL = BEACON_CONFIG.serviceTypes;

let ALL = [];
let currentPage = 1;
const pageSize = 25;
let lastResults = [];
let userLocation = null;

// ── Search Configuration ──────────────────────────────────────────────

const STOP_WORDS = new Set([
  'i','me','my','we','our','you','your','a','an','the','is','are','was',
  'were','be','been','being','have','has','had','do','does','did','will',
  'would','could','should','may','might','shall','can','need','to','of',
  'in','for','on','with','at','by','from','as','into','through','during',
  'before','after','above','below','between','out','off','over','under',
  'again','further','then','once','please','thanks','thank','help',
  'looking','find','want','near'
]);

const PHRASE_MAP = {
  'food tonight': 'food', 'hungry': 'food', 'meal': 'food',
  'place to sleep': 'shelter', 'bed tonight': 'shelter',
  'detox': 'addiction', 'rehab': 'addiction', 'sober living': 'addiction',
  'therapy': 'mental-health', 'counseling': 'mental-health',
  'electric bill': 'utility-assistance', 'power bill': 'utility-assistance',
  'lawyer': 'legal', 'attorney': 'legal',
  'crisis': 'crisis', 'hotline': 'crisis', 'emergency': 'crisis', 'suicide': 'crisis'
};

const WORD_MAP = {
  'hungry': 'food', 'food': 'food', 'meal': 'food',
  'shelter': 'shelter', 'bed': 'shelter', 'sleep': 'shelter',
  'detox': 'addiction', 'rehab': 'addiction', 'sober': 'addiction', 'recovery': 'addiction',
  'therapy': 'mental-health', 'counseling': 'mental-health',
  'electric': 'utility-assistance', 'power': 'utility-assistance', 'utility': 'utility-assistance',
  'lawyer': 'legal', 'attorney': 'legal', 'legal': 'legal',
  'job': 'jobs', 'employment': 'jobs', 'work': 'jobs',
  'crisis': 'crisis', 'hotline': 'crisis', 'emergency': 'crisis', 'suicide': 'crisis'
};

// ── Search Functions ──────────────────────────────────────────────────

function tokenize(q) {
  return q.toLowerCase().split(/\s+/).filter(function(w) {
    return w.length > 0 && !STOP_WORDS.has(w);
  });
}

function expandTokens(tokens) {
  var needs = new Set();
  var words = [];
  var joined = tokens.join(' ');
  for (var phrase in PHRASE_MAP) {
    if (joined.includes(phrase)) needs.add(PHRASE_MAP[phrase]);
  }
  for (var i = 0; i < tokens.length; i++) {
    var t = tokens[i];
    if (WORD_MAP[t]) needs.add(WORD_MAP[t]);
    else words.push(t);
  }
  return { needs: Array.from(needs), words: words };
}

function scoreResource(r, tokens, needs, words) {
  var score = 0;
  var name = (r.name || '').toLowerCase();
  var desc = (r.description || '').toLowerCase();
  var rneeds = r.needs || [];

  if (tokens.every(function(t) { return name.includes(t); })) score += 100;
  for (var i = 0; i < needs.length; i++) {
    if (rneeds.includes(needs[i])) score += 50;
  }
  for (var j = 0; j < words.length; j++) {
    if (name.includes(words[j])) score += 30;
  }
  for (var k = 0; k < words.length; k++) {
    if (desc.includes(words[k])) score += 10;
  }
  return score;
}

function searchWithQuery(q) {
  var tokens = tokenize(q);
  if (!tokens.length) return ALL.slice();
  var expanded = expandTokens(tokens);
  var results = ALL.map(function(r) {
    return { r: r, score: scoreResource(r, tokens, expanded.needs, expanded.words) };
  }).filter(function(s) { return s.score > 0; });

  if (userLocation) {
    results.forEach(function(item) {
      var loc = item.r.locations && item.r.locations[0];
      if (loc && loc.latitude && loc.longitude) {
        var dist = haversine(userLocation.lat, userLocation.lon, loc.latitude, loc.longitude);
        item.r._distance = dist;
        if (dist < 10) item.score += 20;
        else if (dist < 25) item.score += 10;
        else if (dist < 50) item.score += 5;
      }
    });
  }
  return results.sort(function(a, b) { return b.score - a.score; }).map(function(s) { return s.r; });
}

// ── Location Functions ────────────────────────────────────────────────

function haversine(lat1, lon1, lat2, lon2) {
  var R = 3959;
  var dLat = (lat2 - lat1) * Math.PI / 180;
  var dLon = (lon2 - lon1) * Math.PI / 180;
  var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
          Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
          Math.sin(dLon / 2) * Math.sin(dLon / 2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function useMyLocation() {
  if (!navigator.geolocation) {
    showLocationStatus('Geolocation is not supported by your browser', 'error');
    return;
  }
  showLocationStatus('Getting your location...', 'loading');
  navigator.geolocation.getCurrentPosition(
    function(pos) {
      userLocation = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      showLocationStatus(
        'Searching near your location (' + userLocation.lat.toFixed(2) + ', ' + userLocation.lon.toFixed(2) + ')',
        'success'
      );
      document.getElementById('radius-select').disabled = false;
      search();
    },
    function(err) {
      var msg = 'Unable to get your location';
      if (err.code === 1) msg = 'Location permission denied. Please enter a location manually.';
      else if (err.code === 2) msg = 'Location unavailable. Please enter a location manually.';
      else if (err.code === 3) msg = 'Location request timed out. Please try again.';
      showLocationStatus(msg, 'error');
    },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
  );
}

function showLocationStatus(msg, type) {
  var el = document.getElementById('location-status');
  el.style.display = 'block';
  el.textContent = msg;
  el.style.color = type === 'error' ? 'var(--color-danger)' : type === 'success' ? 'var(--color-success)' : 'var(--color-text-muted)';
}

// ── Init ──────────────────────────────────────────────────────────────

async function init() {
  var response = await fetch('/beacon/data/resources.json');
  var data = await response.json();
  ALL = data.resources;

  var counties = [...new Set(ALL.map(function(r) { return r.county; }).filter(function(c) { return c !== 'Statewide'; }))].sort();
  var cs = document.getElementById('county-select');
  counties.forEach(function(c) {
    var o = document.createElement('option');
    o.value = c;
    o.textContent = c + ' County';
    cs.appendChild(o);
  });

  var chipGroup = document.querySelector('.chip-group');
  data.metadata.needs.forEach(function(n) {
    var btn = document.createElement('button');
    btn.className = 'chip';
    btn.setAttribute('aria-pressed', 'false');
    btn.textContent = NL[n] || n;
    btn.onclick = function() {
      var pressed = btn.getAttribute('aria-pressed') === 'true';
      btn.setAttribute('aria-pressed', String(!pressed));
      search();
    };
    btn.dataset.need = n;
    chipGroup.appendChild(btn);
  });

  search();
}

// ── Search ────────────────────────────────────────────────────────────

function search() {
  var q = document.getElementById('search-input').value.trim();
  var county = document.getElementById('county-select').value;
  var radius = parseInt(document.getElementById('radius-select').value) || 0;
  var activeNeeds = Array.from(document.querySelectorAll('.chip[aria-pressed="true"]')).map(function(c) { return c.dataset.need; });
  var r = ALL;

  if (county) r = r.filter(function(x) { return x.county === county; });
  if (activeNeeds.length) r = r.filter(function(x) { return x.needs.some(function(n) { return activeNeeds.includes(n); }); });
  if (q) {
    var searched = searchWithQuery(q);
    r = searched.filter(function(x) { return r.includes(x); });
  }

  if (userLocation && radius > 0) {
    r = r.filter(function(x) {
      var loc = x.locations && x.locations[0];
      if (!loc || !loc.latitude || !loc.longitude) return false;
      return haversine(userLocation.lat, userLocation.lon, loc.latitude, loc.longitude) <= radius;
    });
  }

  var sort = document.getElementById('sort-select').value;
  if (sort === 'alpha') {
    r.sort(function(a, b) { return a.name.localeCompare(b.name); });
  } else if (sort === 'county') {
    r.sort(function(a, b) { return a.county.localeCompare(b.county) || a.name.localeCompare(b.name); });
  } else if (userLocation) {
    r.sort(function(a, b) {
      var locA = a.locations && a.locations[0];
      var locB = b.locations && b.locations[0];
      var distA = (locA && locA.latitude && locA.longitude) ? haversine(userLocation.lat, userLocation.lon, locA.latitude, locA.longitude) : 9999;
      var distB = (locB && locB.latitude && locB.longitude) ? haversine(userLocation.lat, userLocation.lon, locB.latitude, locB.longitude) : 9999;
      return distA - distB;
    });
  }
  currentPage = 1;
  lastResults = r;
  render(r);
}

// ── Render ────────────────────────────────────────────────────────────

function render(list) {
  var grid = document.getElementById('results-grid');
  var count = document.getElementById('results-count');
  var pg = document.getElementById('pagination');

  if (!list.length) {
    grid.innerHTML = '<div class="card" style="text-align:center"><h3>No resources found</h3>' +
      '<p style="color:var(--color-text-muted)">Try different search terms or filters.</p>' +
      '<p style="margin-top:var(--space-3)"><strong>Need immediate help?</strong><br>' +
      '<a href="tel:988">Call 988</a> for crisis · <a href="tel:211">Call 211</a> for services</p></div>';
    count.textContent = '0 results';
    pg.innerHTML = '';
    return;
  }

  var total = list.length;
  var pages = Math.ceil(total / pageSize);
  var start = (currentPage - 1) * pageSize;
  var page = list.slice(start, start + pageSize);

  count.textContent = 'Showing ' + (start + 1) + '–' + Math.min(start + pageSize, total) + ' of ' + total + ' resources';

  var cardsHtml = page.map(function(r) {
    var dist = r._distance ? (' · ' + r._distance.toFixed(1) + ' miles') : '';
    var addressHtml = '';
    if (r.address && r.address !== 'Statewide') {
      addressHtml = '<span>📍 ' + esc(r.address) + dist + '</span>';
    } else if (dist) {
      addressHtml = '<span>📍 ' + (r.county || 'Statewide') + dist + '</span>';
    }

    var phoneHtml = r.phones.length ?
      '<a href="tel:' + r.phones[0] + '" style="color:var(--color-success)">📞 ' + esc(r.phones[0]) + '</a>' : '';
    var hoursHtml = r.hours ? '<span>🕐 ' + esc(r.hours) + '</span>' : '';
    var descHtml = r.description ?
      '<div class="card-body">' + esc(r.description.slice(0, 150)) + (r.description.length > 150 ? '…' : '') + '</div>' : '';

    var needsHtml = r.needs.slice(0, 3).map(function(n) {
      return '<span class="tag tag-accent">' + (NL[n] || n) + '</span>';
    }).join('');
    if (r.needs.length > 3) {
      needsHtml += '<span class="tag">+' + (r.needs.length - 3) + '</span>';
    }

    var callBtn = r.phones.length ?
      '<a href="tel:' + r.phones[0] + '" class="btn btn-success" style="font-size:13px">📞 Call</a>' : '';
    var webBtn = r.url ?
      '<a href="' + esc(r.url) + '" target="_blank" rel="noopener noreferrer" class="btn btn-secondary" style="font-size:13px">🌐 Website</a>' : '';
    var mapBtn = r.map_url ?
      '<a href="' + r.map_url + '" target="_blank" rel="noopener noreferrer" class="btn btn-secondary" style="font-size:13px">🗺 Directions</a>' : '';

    return '<div class="card">' +
      '<div class="card-title"><a href="/beacon/pages/resource/' + r.id + '.html">' + esc(r.name) + '</a></div>' +
      '<div class="card-meta">' + addressHtml + phoneHtml + hoursHtml + '</div>' +
      descHtml +
      '<div style="display:flex;flex-wrap:wrap;gap:var(--space-1)">' + needsHtml + '</div>' +
      '<div class="card-actions">' + callBtn + webBtn + mapBtn +
      '<a href="/beacon/pages/resource/' + r.id + '.html" class="btn btn-ghost" style="font-size:13px">View Details →</a></div>' +
      '</div>';
  }).join('');

  grid.innerHTML = cardsHtml;

  // Pagination
  if (pages <= 1) {
    pg.innerHTML = '';
  } else {
    var btns = '';
    btns += '<button class="page-btn" onclick="goPage(' + (currentPage - 1) + ')"' +
      (currentPage === 1 ? ' disabled' : '') + ' aria-label="Previous page">←</button>';
    for (var i = 1; i <= Math.min(pages, 7); i++) {
      var currentAttr = i === currentPage ? ' aria-current="page"' : '';
      btns += '<button class="page-btn" onclick="goPage(' + i + ')"' + currentAttr + '>' + i + '</button>';
    }
    btns += '<button class="page-btn" onclick="goPage(' + (currentPage + 1) + ')"' +
      (currentPage === pages ? ' disabled' : '') + ' aria-label="Next page">→</button>';
    pg.innerHTML = btns;
  }
}

function goPage(p) {
  currentPage = p;
  render(lastResults);
  document.getElementById('results').scrollIntoView({ behavior: 'smooth' });
}

function esc(s) {
  if (!s) return '';
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ── Event Listeners ───────────────────────────────────────────────────

document.getElementById('search-input').addEventListener('input', search);
document.getElementById('county-select').addEventListener('change', search);
document.getElementById('sort-select').addEventListener('change', search);

init();
