/**
 * Beacon — Main Application JavaScript
 * Loads resources dynamically from data/resources.json
 */

/* global BEACON_CONFIG, L */

// ── Constants ─────────────────────────────────────────────────────

const NEEDS = {
  food:               { t: 'Food & meals',       s: 'Pantries, hot meals, SNAP help',       h: 60  },
  shelter:            { t: 'A place to sleep',   s: 'Emergency shelter tonight',             h: 255 },
  housing:            { t: 'Housing & rent',     s: 'Rent help, transitional housing',       h: 210 },
  health:             { t: 'Doctor & dental',    s: 'Clinics and low-cost care',             h: 150 },
  'mental-health':    { t: 'Someone to talk to', s: 'Counseling and support',                h: 300 },
  addiction:          { t: 'Recovery',           s: 'Detox, treatment, meetings',            h: 185 },
  'utility-assistance':{ t: 'Help with bills',   s: 'Electric, gas, water',                  h: 95  },
  crisis:             { t: 'Safety & abuse',     s: 'Domestic violence, hotlines',           h: 25  },
  jobs:               { t: 'Jobs & income',      s: 'Training, résumés, work',               h: 130 },
  legal:              { t: 'Legal help',         s: 'Legal aid, expungement',                h: 275 },
  family:             { t: 'Kids & family',      s: 'Childcare, parenting',                  h: 345 },
  transportation:     { t: 'Rides',              s: 'Bus passes, medical rides',             h: 230 },
  clothing:           { t: 'Clothes & supplies', s: 'Coats, hygiene, blankets',              h: 40  },
  documents:          { t: 'ID & documents',     s: 'Birth certificate, state ID',           h: 10  },
  veterans:           { t: 'Veterans',           s: 'VA benefits and services',              h: 240 },
  education:          { t: 'GED & classes',      s: 'Adult ed, literacy',                    h: 165 },
  community:          { t: 'Community & support',s: 'Groups, mentoring, faith',              h: 80  },
};

const PRIMARY = ['food','shelter','housing','health','mental-health','addiction','utility-assistance','crisis'];
const ALL_NEEDS = Object.keys(NEEDS);

const POP_LABELS = {
  anyone: 'Open to all', families: 'Families', women: 'Women', men: 'Men',
  youth: 'Youth', seniors: 'Seniors', veterans: 'Veterans', 'lgbtq+': 'LGBTQ+',
  disability: 'Disability', 're-entry': 'Re-Entry', pregnant: 'Pregnant',
  'substance-use': 'Active Substance Use', recovery: 'In Recovery',
};

const SVC_LABELS = {
  hotline: 'Hotline', 'walk-in': 'Walk-In', appointment: 'Appointment',
  residential: 'Residential', outpatient: 'Outpatient', mobile: 'Mobile',
  online: 'Online', 'peer-led': 'Peer-Led', 'faith-based': 'Faith-Based',
  government: 'Government',
};

const C_OPEN = 'oklch(0.5 0.13 155)';
const C_SHUT = 'oklch(0.5 0.02 255)';

// ── State ─────────────────────────────────────────────────────────

const state = {
  q: '',
  need: '',
  county: '',
  sort: 'best',
  more: false,
  f: { free: false, walkin: false, anyone: false },
  loc: null,
  locMsg: '',
  sel: null,
  showSaved: false,
  saved: [],
  big: false,
};

let resources = [];   // normalized from resources.json
let beaconMap = null; // Leaflet map instance
let mapLayer = null;  // Leaflet layer group
let mapKey = '';      // cache key to skip redundant syncs

// ── Utilities ─────────────────────────────────────────────────────

function needColor(n) {
  const h = (NEEDS[n] || { h: 250 }).h;
  return `oklch(0.7 0.13 ${h})`;
}

function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function dateShort(s) {
  if (!s) return 'unknown';
  const d = new Date(s + 'T12:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function dateLong(s) {
  if (!s) return 'unknown';
  const d = new Date(s + 'T12:00');
  return d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
}

function miles(a, b) {
  const R = 3958.8, t = x => x * Math.PI / 180;
  const dl = t(b.lat - a.lat), dn = t(b.lng - a.lng);
  const q = Math.sin(dl/2)**2 + Math.cos(t(a.lat)) * Math.cos(t(b.lat)) * Math.sin(dn/2)**2;
  return 2 * R * Math.asin(Math.sqrt(q));
}

function getStatus(r) {
  if (r.always) return { open: true, text: 'Open 24/7', color: C_OPEN };
  return { open: null, text: r.hours || 'Call for hours', color: C_SHUT };
}

// ── Data Normalization ────────────────────────────────────────────

function normalizeResource(r) {
  const physLoc = (r.locations || []).find(l => l.location_type !== 'virtual');
  const isNational = r.coverage_scope === 'national';
  const isAlways = /24.?7|24\s*hour|around the clock|any ?time/i.test(r.hours || '');
  const rawAddr = physLoc?.address_line_1 || null;
  const isPrivate = !isNational && (
    physLoc?.publicly_displayed === false ||
    (rawAddr && /not published|confidential|private/i.test(rawAddr))
  );
  const areaNames = (r.service_areas || []).flatMap(sa => (sa.values || []).map(v => v.name));
  const popsText = (r.populations || []).map(p => POP_LABELS[p] || p).join(', ') || 'Anyone';
  const typesText = (r.service_types || []).map(t => SVC_LABELS[t] || t).filter(Boolean);
  const costBase = (r.cost || 'unknown') === 'free' ? 'Free' : (r.cost || 'Unknown');
  const costFull = r.eligibility ? `${costBase} · ${r.eligibility.split(';')[0]}` : costBase;
  const displayAddr = (!isPrivate && rawAddr && !/not published/i.test(rawAddr))
    ? [rawAddr, r.city, r.state, r.zip].filter(Boolean).join(', ')
    : null;
  const county = r.county && r.county !== 'National' ? r.county : (physLoc?.county_name || null);

  return {
    id: r.id,
    name: r.name,
    needs: (r.needs || []).length ? r.needs : ['community'],
    desc: r.description || '',
    phone: (r.phones || [])[0] || null,
    allPhones: r.phones || [],
    url: r.url || null,
    city: r.city || physLoc?.city || null,
    county,
    state: r.state || physLoc?.state || null,
    lat: isPrivate ? null : (physLoc?.latitude || null),
    lng: isPrivate ? null : (physLoc?.longitude || null),
    addr: displayAddr,
    area: areaNames,
    national: isNational,
    always: isAlways,
    privateAddr: isPrivate,
    pops: popsText,
    types: typesText,
    cost: costFull,
    bring: r.what_to_bring || null,
    start: r.intake_process || null,
    hours: r.hours || null,
    checked: r.last_verified || '',
    conf: r.confidence ? (r.confidence.charAt(0).toUpperCase() + r.confidence.slice(1)) : 'Unknown',
    sources: (r.source_urls || []).length || 1,
  };
}

// ── Coverage label (replaces hardcoded KY text) ───────────────────

function computeCoverageLabel(list) {
  const local = list.filter(r => !r.national);
  if (!local.length) return 'Community Resources';
  const states = [...new Set(local.map(r => r.state).filter(Boolean))];
  const counties = [...new Set([
    ...local.map(r => r.county),
    ...local.flatMap(r => r.area),
  ].filter(Boolean))];

  if (counties.length === 0 && states.length === 1) return states[0];
  if (counties.length === 1) return `${counties[0]} County`;
  if (counties.length <= 4) return counties.join(', ') + (states.length === 1 ? ` · ${states[0]}` : '');
  if (states.length === 1) return `${counties.length} Counties · ${states[0]}`;
  return `${counties.length} Counties`;
}

// ── County dropdown ───────────────────────────────────────────────

function buildCountyOptions(list) {
  const counties = [...new Set([
    ...list.filter(r => !r.national).map(r => r.county),
    ...list.filter(r => !r.national).flatMap(r => r.area),
  ].filter(Boolean))].sort();

  const sel = document.getElementById('county-select');
  sel.innerHTML = '<option value="">All areas</option>' +
    counties.map(c => `<option value="${esc(c)}">${esc(c)} County</option>`).join('');
}

// ── Filtering & sorting ───────────────────────────────────────────

function filterResources() {
  const q = state.q.trim().toLowerCase();
  return resources.filter(r => {
    if (state.need && !r.needs.includes(state.need)) return false;
    if (state.county && !r.national && r.county !== state.county && !(r.area || []).includes(state.county)) return false;
    if (q) {
      const hay = [r.name, r.desc, ...r.needs.map(n => (NEEDS[n]?.t || '') + ' ' + n), ...(r.types || [])].join(' ').toLowerCase();
      if (!q.split(/\s+/).every(w => hay.includes(w))) return false;
    }
    if (state.f.free && !/free/i.test(r.cost)) return false;
    if (state.f.walkin && !(r.types || []).some(t => /walk/i.test(t)) && !r.always) return false;
    if (state.f.anyone && !/open to all|anyone/i.test(r.pops)) return false;
    return true;
  }).map(r => ({ r, s: getStatus(r), d: state.loc && r.lat ? miles(state.loc, r) : null }));
}

function sortList(list) {
  const rank = x => (x.r.national ? 1 : 0);
  if (state.sort === 'near') {
    return list.sort((a, b) => (a.d ?? 9999) - (b.d ?? 9999));
  }
  return list.sort((a, b) => rank(a) - rank(b) || (b.s.open === true ? 1 : 0) - (a.s.open === true ? 1 : 0));
}

// ── Needs tiles ───────────────────────────────────────────────────

function renderTiles(filteredResources) {
  const grid = document.getElementById('needs-grid');
  const ids = state.more ? ALL_NEEDS : PRIMARY;
  const visible = filteredResources.map(x => x.r);

  grid.innerHTML = ids.map(id => {
    const on = state.need === id;
    const n = resources.filter(r => r.needs.includes(id)).length;
    const color = needColor(id);
    const bg = on ? `oklch(0.95 0.04 ${(NEEDS[id] || { h: 250 }).h})` : 'oklch(0.995 0.004 85)';
    const border = on ? color : 'oklch(0.91 0.012 85)';
    return `<button class="need-tile" data-need="${esc(id)}" aria-pressed="${on}"
      style="text-align:left;display:flex;flex-direction:column;gap:6px;min-height:118px;padding:18px 18px 16px;border-radius:18px;border:2px solid ${border};background:${bg};cursor:pointer;font-family:'Atkinson Hyperlegible',sans-serif;color:oklch(0.24 0.03 255)">
      <span style="display:flex;align-items:center;justify-content:space-between;width:100%">
        <span style="width:18px;height:18px;border-radius:6px;background:${color}"></span>
        <span style="font-size:14px;color:oklch(0.5 0.02 255)">${n ? `${n} ${n === 1 ? 'place' : 'places'}` : ''}</span>
      </span>
      <span style="margin-top:auto;font:700 21px/1.15 'Bricolage Grotesque',sans-serif;letter-spacing:-0.01em">${esc((NEEDS[id] || {}).t || id)}</span>
      <span style="font-size:15px;line-height:1.35;color:oklch(0.46 0.02 255)">${esc((NEEDS[id] || {}).s || '')}</span>
    </button>`;
  }).join('');

  document.getElementById('more-btn').textContent = state.more ? 'Show fewer' : 'More kinds of help →';
}

// ── Filter chips ──────────────────────────────────────────────────

function renderChips() {
  const defs = [
    ['free', 'Free'],
    ['walkin', 'Walk in, no appointment'],
    ['anyone', 'Open to everyone'],
  ];
  document.getElementById('filter-chips').innerHTML = defs.map(([k, label]) => {
    const on = !!state.f[k];
    return `<button class="filter-chip" data-filter="${k}" aria-pressed="${on}"
      style="flex:none;white-space:nowrap;display:flex;align-items:center;gap:8px;min-height:44px;padding:0 16px;border-radius:999px;border:1.5px solid ${on ? 'oklch(0.24 0.045 262)' : 'oklch(0.86 0.012 85)'};background:${on ? 'oklch(0.24 0.045 262)' : 'oklch(0.995 0.004 85)'};color:${on ? 'oklch(0.98 0.005 85)' : 'oklch(0.3 0.03 255)'};font:700 15px 'Atkinson Hyperlegible',sans-serif;cursor:pointer">
      ${on ? '✓ ' : ''}${esc(label)}
    </button>`;
  }).join('');
}

// ── Result cards ──────────────────────────────────────────────────

function renderCards(sorted) {
  const list = document.getElementById('results-list');

  if (!sorted.length) {
    list.innerHTML = `<div style="padding:36px 28px;border-radius:20px;border:2px dashed oklch(0.86 0.012 85);text-align:center">
      <h3 style="margin:0;font:700 24px 'Bricolage Grotesque',sans-serif">Nothing matches just yet.</h3>
      <p style="margin:10px auto 18px;max-width:420px;font-size:17px;line-height:1.5;color:oklch(0.42 0.02 255)">Try removing a filter — or call 211 and a real person will help you find something.</p>
      <div style="display:flex;justify-content:center;flex-wrap:wrap;gap:10px">
        <button id="empty-clear" style="min-height:48px;padding:0 20px;border-radius:12px;border:1.5px solid oklch(0.86 0.012 85);background:transparent;font:700 16px 'Atkinson Hyperlegible',sans-serif;cursor:pointer">Clear filters</button>
        <a href="tel:211" style="display:flex;align-items:center;min-height:48px;padding:0 20px;border-radius:12px;background:oklch(0.24 0.045 262);color:#fff;text-decoration:none;font-weight:700">Call 211</a>
      </div>
    </div>`;
    const clearBtn = document.getElementById('empty-clear');
    if (clearBtn) clearBtn.addEventListener('click', clearAll);
    return;
  }

  list.innerHTML = sorted.map(({ r, s, d }) => {
    const saved = state.saved.includes(r.id);
    const where = r.national
      ? 'Anywhere in the U.S. · by phone'
      : [r.city, r.county && `${r.county} Co.`, d != null && `${d.toFixed(1)} mi away`].filter(Boolean).join(' · ');
    const color = needColor(r.needs[0]);
    const phone = r.phone;
    const tags = [r.cost.split(/[·—]/)[0].trim(), ...(r.types || []).slice(0, 2), r.pops]
      .filter((v, i, a) => v && a.indexOf(v) === i).slice(0, 4);
    const hasDir = !!(r.lat && !r.privateAddr);

    return `<article class="result-card" style="padding:22px;border-radius:20px;background:oklch(0.995 0.004 85);border:1px solid oklch(0.9 0.012 85);box-shadow:0 1px 0 oklch(0.9 0.012 85)">
      <div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px">
        <span style="display:flex;align-items:center;gap:8px;font-size:14px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:oklch(0.45 0.02 255)">
          <span style="width:10px;height:10px;border-radius:3px;background:${color}"></span>
          ${esc((NEEDS[r.needs[0]] || {}).t || r.needs[0])}
        </span>
        <span style="font-size:14px;color:oklch(0.45 0.08 155)">✓ Checked ${esc(dateShort(r.checked))}</span>
      </div>
      <h3 style="margin:10px 0 6px;font:700 24px/1.15 'Bricolage Grotesque',sans-serif;letter-spacing:-0.015em;text-wrap:pretty">${esc(r.name)}</h3>
      <div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;font-size:16px">
        <span style="display:flex;align-items:center;gap:7px;font-weight:700;color:${s.color}">
          <span style="width:9px;height:9px;border-radius:50%;background:${s.color}"></span>${esc(s.text)}
        </span>
        <span style="color:oklch(0.48 0.02 255)">${esc(where)}</span>
      </div>
      <p style="margin:12px 0 0;font-size:17px;line-height:1.5;color:oklch(0.35 0.025 255);text-wrap:pretty;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${esc(r.desc)}</p>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:12px">
        ${tags.map(t => `<span style="padding:4px 10px;border-radius:8px;background:oklch(0.95 0.012 85);font-size:14px;color:oklch(0.38 0.025 255)">${esc(t)}</span>`).join('')}
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:18px">
        ${phone ? `<a href="tel:${esc(phone.replace(/[^\d+]/g,''))}" style="display:flex;align-items:center;min-height:48px;padding:0 20px;border-radius:12px;background:oklch(0.24 0.045 262);color:oklch(0.98 0.005 85);text-decoration:none;font-weight:700;font-size:16px">Call ${esc(phone)}</a>` : ''}
        ${hasDir ? `<a href="https://www.google.com/maps/dir/?api=1&destination=${r.lat},${r.lng}" target="_blank" rel="noopener" style="display:flex;align-items:center;min-height:48px;padding:0 18px;border-radius:12px;border:1.5px solid oklch(0.86 0.012 85);color:oklch(0.24 0.03 255);text-decoration:none;font-weight:700;font-size:16px">Directions</a>` : ''}
        <button class="open-detail-btn" data-id="${esc(r.id)}" style="min-height:48px;padding:0 18px;border-radius:12px;border:1.5px solid oklch(0.86 0.012 85);background:transparent;color:oklch(0.24 0.03 255);font:700 16px 'Atkinson Hyperlegible',sans-serif;cursor:pointer">Details</button>
        <button class="save-btn" data-id="${esc(r.id)}" style="margin-left:auto;min-height:48px;padding:0 16px;border-radius:12px;border:0;background:${saved ? 'oklch(0.9 0.08 80)' : 'oklch(0.95 0.012 85)'};color:oklch(0.24 0.03 255);font:700 16px 'Atkinson Hyperlegible',sans-serif;cursor:pointer">${saved ? 'Saved ✓' : '+ Save'}</button>
      </div>
    </article>`;
  }).join('');
}

// ── Map ───────────────────────────────────────────────────────────

function syncMap(visibleResources) {
  const mappable = visibleResources.filter(r => r.lat && !r.privateAddr);
  const hasPts = mappable.length > 0 || !!state.loc;

  // Show/hide the entire map panel
  const panel = document.getElementById('map-panel');
  if (panel) panel.style.display = hasPts ? 'flex' : 'none';
  if (!hasPts) return;

  const el = document.getElementById('map-container');
  if (!el || typeof L === 'undefined') return;

  if (!beaconMap) {
    beaconMap = L.map(el, { scrollWheelZoom: false }).setView([39.5, -98.35], 4);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(beaconMap);
    mapLayer = L.layerGroup().addTo(beaconMap);
  }

  const newKey = mappable.map(r => r.id).join(',') + (state.loc ? 'L' : '');
  if (newKey === mapKey) return;
  mapKey = newKey;

  mapLayer.clearLayers();
  const pts = [];

  mappable.forEach(r => {
    const m = L.circleMarker([r.lat, r.lng], {
      radius: 10, weight: 3, color: '#fff',
      fillColor: needColor(r.needs[0]), fillOpacity: 1,
    }).addTo(mapLayer);
    m.bindTooltip(r.name, { direction: 'top', offset: [0, -8] });
    m.on('click', () => openDetail(r.id));
    pts.push([r.lat, r.lng]);
  });

  if (state.loc) {
    L.circleMarker([state.loc.lat, state.loc.lng], {
      radius: 8, weight: 4, color: '#e5a020',
      fillColor: '#1e2d5c', fillOpacity: 1,
    }).bindTooltip('You').addTo(mapLayer);
    pts.push([state.loc.lat, state.loc.lng]);
  }

  if (pts.length > 1) beaconMap.fitBounds(pts, { padding: [40, 40], maxZoom: 13 });
  else if (pts.length === 1) beaconMap.setView(pts[0], 12);
}

// ── Detail drawer ─────────────────────────────────────────────────

function openDetail(id) {
  const r = resources.find(x => x.id === id);
  if (!r) return;
  state.sel = id;

  const s = getStatus(r);
  const color = needColor(r.needs[0]);
  const d = state.loc && r.lat ? miles(state.loc, r) : null;
  const where = r.national
    ? 'Nationwide'
    : [r.city, r.county && `${r.county} County`, d != null && `${d.toFixed(1)} mi`].filter(Boolean).join(' · ');
  const hasDir = !!(r.lat && !r.privateAddr);
  const saved = state.saved.includes(id);

  const rows = [
    ['Hours', r.hours],
    ['Who it\'s for', r.pops],
    ['Cost', r.cost],
    ['Type', (r.types || []).join(', ') || null],
    ['Address', r.privateAddr ? null : r.addr],
    ['Serves', r.national ? 'Nationwide' : r.area.length ? r.area.join(', ') + ' counties' : where],
    ['What to bring', r.bring],
    ['How to start', r.start],
  ].filter(x => x[1]);

  document.getElementById('detail-need-dot').style.background = color;
  document.getElementById('detail-need-text').textContent = (NEEDS[r.needs[0]] || {}).t || r.needs[0];

  document.getElementById('detail-body').innerHTML = `
    <h2 style="margin:0;font:800 32px/1.08 'Bricolage Grotesque',sans-serif;letter-spacing:-0.02em;text-wrap:balance">${esc(r.name)}</h2>
    <div style="display:flex;align-items:center;gap:8px;margin-top:10px;font-size:17px;font-weight:700;color:${s.color}">
      <span style="width:10px;height:10px;border-radius:50%;background:${s.color}"></span>${esc(s.text)}
    </div>
    <p style="margin:16px 0 0;font-size:18px;line-height:1.55;color:oklch(0.32 0.025 255);text-wrap:pretty">${esc(r.desc)}</p>
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:20px">
      ${r.phone ? `<a href="tel:${esc(r.phone.replace(/[^\d+]/g,''))}" style="flex:1 1 200px;display:flex;align-items:center;justify-content:center;min-height:54px;padding:0 20px;border-radius:14px;background:oklch(0.24 0.045 262);color:#fff;text-decoration:none;font-weight:700;font-size:17px">Call ${esc(r.phone)}</a>` : ''}
      ${hasDir ? `<a href="https://www.google.com/maps/dir/?api=1&destination=${r.lat},${r.lng}" target="_blank" rel="noopener" style="flex:1 1 160px;display:flex;align-items:center;justify-content:center;min-height:54px;padding:0 20px;border-radius:14px;border:1.5px solid oklch(0.86 0.012 85);color:oklch(0.24 0.03 255);text-decoration:none;font-weight:700;font-size:17px">Directions</a>` : ''}
      <button id="detail-save-btn" data-id="${esc(id)}" style="flex:1 1 140px;min-height:54px;padding:0 20px;border-radius:14px;border:0;background:${saved ? 'oklch(0.9 0.08 80)' : 'oklch(0.95 0.012 85)'};font:700 17px 'Atkinson Hyperlegible',sans-serif;color:oklch(0.24 0.03 255);cursor:pointer">${saved ? 'Saved ✓' : '+ Save'}</button>
    </div>
    ${r.privateAddr ? `<div style="margin-top:20px;padding:16px 18px;border-radius:14px;background:oklch(0.95 0.03 300);font-size:16px;line-height:1.5;color:oklch(0.3 0.05 300)"><strong>Address kept private for your safety.</strong> Call and staff will arrange a safe way to meet you.</div>` : ''}
    <dl style="margin:28px 0 0">
      ${rows.map(([k, v]) => `<div style="display:grid;grid-template-columns:minmax(120px,160px) 1fr;gap:12px;padding:14px 0;border-top:1px solid oklch(0.9 0.012 85)">
        <dt style="font-size:15px;font-weight:700;color:oklch(0.45 0.02 255)">${esc(k)}</dt>
        <dd style="margin:0;font-size:17px;line-height:1.5">${esc(v)}</dd>
      </div>`).join('')}
    </dl>
    <a href="/beacon/pages/resource/${esc(r.id)}.html" style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:20px;min-height:54px;padding:0 20px;border-radius:14px;border:1.5px solid oklch(0.86 0.012 85);color:oklch(0.24 0.03 255);text-decoration:none;font:700 17px 'Atkinson Hyperlegible',sans-serif">Full page with coverage map <span aria-hidden="true">→</span></a>
    <div style="margin-top:24px;padding:20px;border-radius:16px;background:oklch(0.95 0.035 155);color:oklch(0.28 0.05 155)">
      <div style="font:700 18px 'Bricolage Grotesque',sans-serif">✓ How we checked this</div>
      <p style="margin:8px 0 0;font-size:16px;line-height:1.5">Last checked ${esc(dateLong(r.checked))} against ${r.sources === 1 ? '1 official source' : `${r.sources} independent sources`}. Confidence: <strong>${esc(r.conf)}</strong>.</p>
      <a href="https://github.com/MrStewood/beacon/issues/new?template=update-resource.md" style="display:inline-block;margin-top:10px;font-size:16px;font-weight:700;color:oklch(0.3 0.08 155)">Something wrong? Tell us →</a>
    </div>`;

  document.getElementById('detail-drawer').classList.add('open');
  document.getElementById('detail-save-btn').addEventListener('click', () => {
    toggleSave(id);
    // Refresh save button state
    const btn = document.getElementById('detail-save-btn');
    if (btn) {
      const isSaved = state.saved.includes(id);
      btn.textContent = isSaved ? 'Saved ✓' : '+ Save';
      btn.style.background = isSaved ? 'oklch(0.9 0.08 80)' : 'oklch(0.95 0.012 85)';
    }
  });
}

function closeDetail() {
  state.sel = null;
  document.getElementById('detail-drawer').classList.remove('open');
}

// ── Saved drawer ──────────────────────────────────────────────────

function openSaved() {
  state.showSaved = true;
  const saved = resources.filter(r => state.saved.includes(r.id));
  const listText = saved.map(r => `${r.name} — ${r.phone || r.url || ''}${r.addr ? ' — ' + r.addr : ''}`).join('\n');

  document.getElementById('saved-items').innerHTML = saved.length
    ? saved.map(r => `<div style="display:flex;align-items:center;gap:12px;padding:14px 16px;border-radius:14px;background:oklch(0.995 0.004 85);border:1px solid oklch(0.9 0.012 85)">
        <span style="width:10px;height:10px;border-radius:3px;background:${needColor(r.needs[0])};flex:none"></span>
        <div style="flex:1;min-width:0">
          <div style="font:700 18px/1.2 'Bricolage Grotesque',sans-serif">${esc(r.name)}</div>
          <div style="font-size:15px;color:oklch(0.45 0.02 255)">${esc(r.phone || '')}</div>
        </div>
        <button class="saved-remove-btn" data-id="${esc(r.id)}" aria-label="Remove" style="min-height:44px;padding:0 12px;border:0;background:none;font:700 15px 'Atkinson Hyperlegible',sans-serif;color:oklch(0.5 0.12 27);cursor:pointer">Remove</button>
      </div>`).join('')
    : '<p style="color:oklch(0.45 0.02 255)">No items saved yet.</p>';

  document.getElementById('saved-sms').href = 'sms:?&body=' + encodeURIComponent('My Beacon list:\n' + listText);

  document.getElementById('saved-copy').textContent = 'Copy';
  document.getElementById('saved-copy').onclick = () => {
    try { navigator.clipboard.writeText(listText); } catch (e) { /* noop */ }
    const btn = document.getElementById('saved-copy');
    if (btn) { btn.textContent = 'Copied ✓'; setTimeout(() => { btn.textContent = 'Copy'; }, 1800); }
  };

  document.getElementById('saved-drawer').classList.add('open');
}

function closeSaved() {
  state.showSaved = false;
  document.getElementById('saved-drawer').classList.remove('open');
}

// ── Save / unsave ─────────────────────────────────────────────────

function toggleSave(id) {
  const idx = state.saved.indexOf(id);
  if (idx >= 0) state.saved.splice(idx, 1);
  else state.saved.push(id);
  try { localStorage.setItem('beacon_saved', JSON.stringify(state.saved)); } catch (e) { /* noop */ }
  updatePill();
  // Re-render save buttons without full render (avoid map jitter)
  document.querySelectorAll(`.save-btn[data-id="${CSS.escape(id)}"]`).forEach(btn => {
    const isSaved = state.saved.includes(id);
    btn.textContent = isSaved ? 'Saved ✓' : '+ Save';
    btn.style.background = isSaved ? 'oklch(0.9 0.08 80)' : 'oklch(0.95 0.012 85)';
  });
}

function updatePill() {
  const pill = document.getElementById('list-pill');
  const count = document.getElementById('list-pill-count');
  const n = state.saved.length;
  if (n > 0) {
    pill.classList.add('visible');
    count.textContent = n;
  } else {
    pill.classList.remove('visible');
  }
}

// ── Master render ─────────────────────────────────────────────────

function render() {
  const filtered = filterResources();
  const sorted = sortList([...filtered]);
  const visible = sorted.map(x => x.r);

  // Header counts
  const n = sorted.length;
  document.getElementById('context-label').textContent =
    state.need ? (NEEDS[state.need]?.t || state.need) :
    state.county ? `${state.county} County` : 'All help';
  document.getElementById('count-label').textContent =
    n === 0 ? 'No matches' : n === 1 ? '1 place can help' : `${n} places can help`;

  // Clear-all button
  const hasFilters = !!(state.need || state.county || state.q || Object.values(state.f).some(Boolean));
  document.getElementById('clear-all-btn').style.display = hasFilters ? 'inline-flex' : 'none';

  renderTiles(filtered);
  renderChips();
  renderCards(sorted);
  syncMap(visible);
  updatePill();
}

// ── Helpers ───────────────────────────────────────────────────────

function clearAll() {
  state.q = '';
  state.need = '';
  state.county = '';
  state.f = { free: false, walkin: false, anyone: false };
  document.getElementById('q').value = '';
  document.getElementById('county-select').value = '';
  render();
}

function scrollToResults() {
  const el = document.getElementById('results');
  if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 8, behavior: 'smooth' });
}

// ── Init ──────────────────────────────────────────────────────────

async function init() {
  // Restore saved list
  try { state.saved = JSON.parse(localStorage.getItem('beacon_saved') || '[]'); } catch (e) { state.saved = []; }

  try {
    const res = await fetch('data/resources.json');
    const data = await res.json();
    resources = (data.resources || []).map(normalizeResource);
  } catch (e) {
    document.getElementById('count-label').textContent = 'Unable to load resources. Try refreshing.';
    console.error('Failed to load resources.json', e);
    return;
  }

  // Set hero location dynamically (fixes KY hardcode)
  document.getElementById('hero-location').textContent = computeCoverageLabel(resources);

  // Populate county dropdown dynamically
  buildCountyOptions(resources);

  render();
}

// ── Event listeners ───────────────────────────────────────────────

// Search form
document.getElementById('search-form').addEventListener('submit', e => {
  e.preventDefault();
  state.q = document.getElementById('q').value;
  scrollToResults();
  render();
});

document.getElementById('q').addEventListener('input', e => {
  state.q = e.target.value;
  render();
});

document.getElementById('county-select').addEventListener('change', e => {
  state.county = e.target.value;
  render();
});

document.getElementById('sort-select').addEventListener('change', e => {
  state.sort = e.target.value;
  render();
});

// Clear all
document.getElementById('clear-all-btn').addEventListener('click', clearAll);

// Needs tiles (delegated)
document.getElementById('needs-grid').addEventListener('click', e => {
  const btn = e.target.closest('.need-tile');
  if (!btn) return;
  const id = btn.dataset.need;
  state.need = state.need === id ? '' : id;
  render();
  if (state.need) setTimeout(scrollToResults, 30);
});

// More / fewer needs
document.getElementById('more-btn').addEventListener('click', () => {
  state.more = !state.more;
  render();
});

// Filter chips (delegated)
document.getElementById('filter-chips').addEventListener('click', e => {
  const btn = e.target.closest('.filter-chip');
  if (!btn) return;
  const k = btn.dataset.filter;
  state.f[k] = !state.f[k];
  render();
});

// Result cards (delegated)
document.getElementById('results-list').addEventListener('click', e => {
  const openBtn = e.target.closest('.open-detail-btn');
  if (openBtn) { openDetail(openBtn.dataset.id); return; }
  const saveBtn = e.target.closest('.save-btn');
  if (saveBtn) { toggleSave(saveBtn.dataset.id); return; }
});

// Detail drawer
document.getElementById('detail-close').addEventListener('click', closeDetail);
document.getElementById('detail-backdrop').addEventListener('click', closeDetail);

// Saved drawer
document.getElementById('list-pill').addEventListener('click', openSaved);
document.getElementById('saved-close').addEventListener('click', closeSaved);
document.getElementById('saved-backdrop').addEventListener('click', closeSaved);
document.getElementById('saved-print').addEventListener('click', () => window.print());

// Saved items remove (delegated)
document.getElementById('saved-items').addEventListener('click', e => {
  const btn = e.target.closest('.saved-remove-btn');
  if (btn) { toggleSave(btn.dataset.id); openSaved(); }
});

// Geolocation
document.getElementById('loc-btn').addEventListener('click', () => {
  if (!navigator.geolocation) {
    document.getElementById('loc-msg').textContent = 'Location isn\'t available — pick an area instead.';
    return;
  }
  document.getElementById('loc-msg').textContent = 'Finding you…';
  document.getElementById('loc-btn-label').textContent = 'Finding…';
  navigator.geolocation.getCurrentPosition(
    pos => {
      state.loc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      state.sort = 'near';
      document.getElementById('sort-select').value = 'near';
      document.getElementById('loc-btn-label').textContent = 'Using your location';
      document.getElementById('loc-msg').textContent = 'Showing nearest first. Your location stays on this device.';
      mapKey = ''; // force map re-sync
      render();
      scrollToResults();
    },
    () => {
      document.getElementById('loc-btn-label').textContent = 'Use my location';
      document.getElementById('loc-msg').textContent = 'Couldn\'t get your location — pick an area instead.';
    },
    { timeout: 8000 }
  );
});

// Text size toggle
document.getElementById('text-size-btn').addEventListener('click', () => {
  state.big = !state.big;
  document.documentElement.style.fontSize = state.big ? '18px' : '';
  document.getElementById('text-size-label').textContent = state.big ? 'Larger text on' : 'Larger text';
});

// Quick exit
document.getElementById('quick-exit-btn').addEventListener('click', () => {
  try { sessionStorage.clear(); } catch (e) { /* noop */ }
  window.location.replace('https://weather.com');
});

// ESC to close drawers
window.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (state.sel) closeDetail();
    else if (state.showSaved) closeSaved();
  }
});

init();
