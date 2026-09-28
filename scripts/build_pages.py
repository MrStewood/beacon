#!/usr/bin/env python3
"""Generate individual resource pages, county pages, and need pages."""

import json
import os
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
PAGES_DIR = REPO_ROOT / "pages"
SCHEMA_DIR = REPO_ROOT / "schema"
BASE_PATH = "/beacon"

NEED_LABELS = {
    "addiction": "Addiction & Recovery", "clothing": "Clothing & Supplies",
    "community": "Community Support", "crisis": "Crisis & Safety",
    "documents": "ID & Documents", "education": "Education",
    "family": "Family & Children", "food": "Food & Water",
    "health": "Healthcare", "housing": "Housing",
    "jobs": "Jobs & Income", "legal": "Legal Help",
    "mental-health": "Mental Health", "shelter": "Shelter & Sleep",
    "transportation": "Transportation", "veterans": "Veterans"
}

POP_LABELS = {
    "anyone": "Open to All", "families": "Families", "women": "Women",
    "men": "Men", "youth": "Youth", "seniors": "Seniors",
    "veterans": "Veterans", "lgbtq+": "LGBTQ+", "disability": "Disability",
    "re-entry": "Re-Entry", "pregnant": "Pregnant",
    "substance-use": "Active Substance Use", "recovery": "In Recovery"
}

def load_data():
    with open(DATA_DIR / "resources.json") as f:
        return json.load(f)

def esc(s):
    """HTML escape."""
    if not s: return ""
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


def _service_area_label(area):
    """Human-readable label for a single service_area entry."""
    t = area.get("type", "")
    vals = area.get("values", [])
    names = [v.get("name", "") for v in vals if v.get("name")]
    state = area.get("state", "")
    if t == "county":
        if len(names) == 1:
            return f"{names[0]} County, {state}"
        elif len(names) <= 6:
            return ", ".join(names) + f" Counties, {state}"
        else:
            return f"{len(names)} counties in {state}"
    elif t == "city":
        return ", ".join(names) + (f", {state}" if state else "")
    elif t == "postal-code":
        return "ZIP: " + ", ".join(names)
    elif t == "radius":
        return f"Within {area.get('radius_miles', '?')} miles"
    elif t == "state":
        return state or "Statewide"
    elif t == "country":
        return "Nationwide"
    return t


def _map_and_service_area_html(r):
    """Build the map + service area section for a resource detail page."""
    import json as _json

    loc = next(
        (l for l in r.get("locations", [])
         if l.get("publicly_displayed", True) and l.get("location_type") != "virtual"),
        None,
    )
    lat = (loc or {}).get("latitude")
    lon = (loc or {}).get("longitude")
    service_areas = r.get("service_areas", [])

    if not service_areas and not lat:
        return ""

    # --- Text labels ---
    sa_labels = [_service_area_label(a) for a in service_areas]
    icon_map = {"county": "\U0001f5fa", "city": "\U0001f3d8", "postal-code": "\U0001f4ee",
                "radius": "\U0001f4e1", "state": "\U0001f3db", "country": "\U0001f30e"}
    items = "".join(
        f'<li>{icon_map.get(a.get("type",""), "\U0001f4cd")} {esc(lbl)}</li>'
        for a, lbl in zip(service_areas, sa_labels)
    )
    text_html = (
        '<div class="service-area-text">'
        '<h3 class="sa-heading">Service Area</h3>'
        f'<ul class="sa-list">{items}</ul>'
        '</div>'
    ) if items else ""

    if not lat:
        return f'<div class="service-area-section">{text_html}</div>' if text_html else ""

    # --- JS data ---
    pin_js = f"[{lat}, {lon}]"

    county_fips_list = []
    for area in service_areas:
        if area.get("type") == "county":
            for v in area.get("values", []):
                if v.get("fips"):
                    county_fips_list.append({"fips": v["fips"], "name": v.get("name", "")})
    county_layers_js = _json.dumps(county_fips_list)

    radius_js = "null"
    for area in service_areas:
        if area.get("type") == "radius":
            miles = area.get("radius_miles", 25)
            center = area.get("center", {})
            radius_js = _json.dumps({
                "lat": center.get("latitude", lat),
                "lon": center.get("longitude", lon),
                "miles": miles,
            })
            break

    name_js  = _json.dumps(r.get("name", ""))
    addr_js  = _json.dumps(r.get("address") or "")

    map_js = (
        "(function(){{"
        "var PIN={pin};var COUNTIES={counties};var RADIUS={radius};var NAME={name};var ADDR={addr};"
        "function initMap(){{"
        "var map=L.map('resource-map',{{zoomControl:true,scrollWheelZoom:false}});"
        "L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{"
        "attribution:'\u00a9 <a href=\'https://www.openstreetmap.org/copyright\'>OpenStreetMap</a> contributors',"
        "maxZoom:18}}).addTo(map);"
        "var marker=L.marker(PIN).addTo(map);"
        "marker.bindPopup('<strong>'+NAME+'</strong>'+(ADDR?'<br>'+ADDR:''));"
        "var bounds=L.latLngBounds([PIN]);"
        "if(COUNTIES.length>0){{"
        "var pending=COUNTIES.length,allLayers=[];"
        "COUNTIES.forEach(function(c){{"
        "var st=c.fips.substring(0,2),co=c.fips.substring(2);"
        "var url='https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query'"
        "+'?where=STATE%3D%27'+st+'%27%20AND%20COUNTY%3D%27'+co+'%27&outFields=NAME,GEOID&outSR=4326&f=geojson';"
        "fetch(url).then(function(res){{return res.json();}}).then(function(gj){{"
        "if(gj.features&&gj.features.length){{"
        "var ly=L.geoJSON(gj,{{style:{{color:'#2563eb',weight:2,fillColor:'#3b82f6',fillOpacity:0.12}}}});"
        "ly.addTo(map);allLayers.push(ly);bounds.extend(ly.getBounds());"
        "}}}}).catch(function(){{}}).finally(function(){{"
        "pending--;if(pending===0&&allLayers.length>0)map.fitBounds(bounds.pad(0.1));"
        "}});}});}}"
        "if(RADIUS){{"
        "var circ=L.circle([RADIUS.lat,RADIUS.lon],{{radius:RADIUS.miles*1609.34,"
        "color:'#2563eb',weight:2,fillColor:'#3b82f6',fillOpacity:0.12}}).addTo(map);"
        "bounds.extend(circ.getBounds());}}"
        "if(COUNTIES.length===0&&!RADIUS)map.setView(PIN,13);"
        "else if(COUNTIES.length===0)map.fitBounds(bounds.pad(0.1));"
        "else map.setView(PIN,10);}}"
        "if(!window.L){{"
        "var lnk=document.createElement('link');lnk.rel='stylesheet';"
        "lnk.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';document.head.appendChild(lnk);"
        "var scr=document.createElement('script');scr.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';"
        "scr.onload=initMap;document.head.appendChild(scr);}}else initMap();"
        "}})();"
    ).format(
        pin=pin_js, counties=county_layers_js, radius=radius_js,
        name=name_js, addr=addr_js,
    )

    return (
        '<div class="service-area-section">'
        + text_html
        + '<div class="map-container" id="resource-map" aria-label="Map showing location and service area"></div>'
        + f'<script>{map_js}</script>'
        + '</div>'
    )


def resource_page(r, data):
    """Generate HTML for a single resource."""
    needs = r.get("needs", [])
    pops = [p for p in r.get("populations", []) if p != "anyone"]
    svcs = r.get("service_types", [])
    county = r.get("county", "")

    # JSON-LD
    jsonld = {
        "@context": "https://schema.org",
        "@type": "SocialService",
        "name": r["name"],
        "description": r.get("description", ""),
        "url": r.get("url"),
        "telephone": r.get("phones", [None])[0] if r.get("phones") else None,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": r.get("address", ""),
            "addressLocality": r.get("city", ""),
            "addressRegion": r.get("state", "KY"),
            "postalCode": r.get("zip", "")
        } if r.get("address") and r["address"] != "Statewide" else None,
        "areaServed": {"@type": "State", "name": "Kentucky"},
        "serviceType": [NEED_LABELS.get(n, n) for n in needs]
    }
    jsonld = {k:v for k,v in jsonld.items() if v is not None}

    # Related resources (same county, same needs, excluding self)
    related = [x for x in data["resources"]
               if x["id"] != r["id"]
               and (x["county"] == county or set(x["needs"]) & set(needs))
               and x["county"] != "Statewide"][:5]

    # Breadcrumbs
    if county != "Statewide":
        breadcrumbs = f'''<nav class="breadcrumbs" aria-label="Breadcrumb">
            <a href="/beacon/">Home</a> ›
            <a href="/beacon/pages/county/{county.lower()}.html">{esc(county)} County</a> ›
            <span>{esc(r["name"])}</span>
        </nav>'''
    else:
        breadcrumbs = f'''<nav class="breadcrumbs" aria-label="Breadcrumb">
            <a href="/beacon/">Home</a> ›
            <span>Statewide Resources</span> ›
            <span>{esc(r["name"])}</span>
        </nav>'''

    # Action buttons
    actions = ""
    if r.get("phones"):
        actions += f'<a href="tel:{r["phones"][0]}" class="action-btn call">📞 Call {esc(r["phones"][0])}</a>'
    if r.get("url"):
        actions += f'<a href="{esc(r["url"])}" target="_blank" rel="noopener noreferrer" class="action-btn">🌐 Website</a>'
    if r.get("map_url"):
        actions += f'<a href="{r["map_url"]}" target="_blank" rel="noopener noreferrer" class="action-btn">🗺 Directions</a>'
    actions += f'<a href="https://github.com/MrStewood/beacon/issues/new?template=update-resource.md&title=Update:{r["name"]}" target="_blank" rel="noopener noreferrer" class="action-btn">✏️ Report Issue</a>'
    actions += f'<button class="action-btn" onclick="navigator.share({{title:\'{esc(r["name"])}\',url:location.href}}).catch(()=>{{}})">🔗 Share</button>'

    # Details
    details = ""
    if r.get("eligibility"):
        details += f'<dt>Eligibility</dt><dd>{esc(r["eligibility"])}</dd>'
    if r.get("intake_process"):
        details += f'<dt>How to Apply</dt><dd>{esc(r["intake_process"])}</dd>'
    if r.get("what_to_bring"):
        details += f'<dt>What to Bring</dt><dd>{esc(r["what_to_bring"])}</dd>'
    if r.get("hours"):
        details += f'<dt>Hours</dt><dd>{esc(r["hours"])}</dd>'
    if r.get("cost") and r["cost"] != "unknown":
        details += f'<dt>Cost</dt><dd>{esc(r["cost"])}</dd>'
    if r.get("capacity"):
        details += f'<dt>Capacity</dt><dd>{esc(r["capacity"])}</dd>'
    if r.get("waitlist") is True:
        details += f'<dt>Waitlist</dt><dd>Currently has a waiting list</dd>'
    if r.get("notes"):
        details += f'<dt>Notes</dt><dd>{esc(r["notes"])}</dd>'

    # Related
    related_html = ""
    if related:
        related_html = '<div class="related"><h3>Related Resources</h3><ul>'
        for x in related:
            related_html += f'<li><a href="/beacon/pages/resource/{x["id"]}.html">{esc(x["name"])}</a> — {esc(x.get("description","")[:80])}</li>'
        related_html += '</ul></div>'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{esc(r["name"])} — Beacon</title>
    <meta name="description" content="{esc(r.get("description","")[:160])}">
    <meta property="og:title" content="{esc(r["name"])} — Beacon">
    <meta property="og:description" content="{esc(r.get("description","")[:160])}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://mrstewood.github.io/beacon/pages/resource/{r["id"]}.html">
    <link rel="canonical" href="https://mrstewood.github.io/beacon/pages/resource/{r["id"]}.html">
    <script type="application/ld+json">{json.dumps(jsonld)}</script>
    <link rel="stylesheet" href="/beacon/assets/css/beacon.css">
    <style>
        .resource-detail{{max-width:800px;margin:0 auto;padding:var(--space-4)}}
        .resource-header{{margin-bottom:var(--space-6)}}
        .resource-title{{font-size:28px;margin-bottom:var(--space-2)}}
        .resource-meta{{display:flex;flex-wrap:wrap;gap:var(--space-3);font-size:14px;color:var(--color-text-muted);margin-bottom:var(--space-4)}}
        .resource-meta span{{display:flex;align-items:center;gap:var(--space-1)}}
        .resource-actions{{display:flex;flex-wrap:wrap;gap:var(--space-2);margin:var(--space-4) 0}}
        .resource-details{{margin-top:var(--space-6);padding-top:var(--space-4);border-top:1px solid var(--color-divider)}}
        .resource-details dt{{font-weight:600;margin-top:var(--space-3);font-size:14px;color:var(--color-text)}}
        .resource-details dd{{margin:0;color:var(--color-text-muted);font-size:14px}}
        .resource-related{{margin-top:var(--space-6);padding-top:var(--space-4);border-top:1px solid var(--color-divider)}}
        .resource-related h3{{font-size:18px;margin-bottom:var(--space-3)}}
        .resource-related ul{{list-style:none;padding:0}}
        .resource-related li{{padding:var(--space-2) 0;font-size:14px;border-bottom:1px solid var(--color-divider)}}
        .resource-related li:last-child{{border-bottom:none}}
        .resource-related a{{color:var(--color-accent);text-decoration:none}}
        .resource-related a:hover{{text-decoration:underline}}
        .service-area-section{{margin-top:var(--space-6);padding-top:var(--space-4);border-top:1px solid var(--color-divider)}}
        .sa-heading{{font-size:18px;margin-bottom:var(--space-3)}}
        .sa-list{{list-style:none;padding:0;margin:0 0 var(--space-4) 0;display:flex;flex-wrap:wrap;gap:var(--space-2)}}
        .sa-list li{{background:var(--color-surface);border:1px solid var(--color-divider);border-radius:6px;padding:4px 12px;font-size:14px;color:var(--color-text)}}
        .map-container{{width:100%;height:320px;border-radius:8px;border:1px solid var(--color-divider);background:#f0f4f8}}
        @media(max-width:600px){{.map-container{{height:220px}}}}
        .resource-related a:hover{{text-decoration:underline}}
    </style>
</head>
        footer a{{color:#93c5fd;text-decoration:none}}
    </style>
</head>
<body>
    <a href="#main-content" class="skip-link">Skip to content</a>

    <!-- Navigation -->
    <nav class="nav" aria-label="Main navigation">
        <a href="/beacon/" class="nav-brand">Beacon</a>
        <a href="/beacon/">Find Help</a>
        <a href="/beacon/organizations.html">For Organizations</a>
        <a href="https://github.com/MrStewood/beacon" target="_blank" rel="noopener noreferrer">GitHub</a>
    </nav>

    <main id="main-content" class="resource-detail">
        {breadcrumbs}

        <div class="resource-header">
            <h1 class="resource-title">{esc(r["name"])}</h1>
            <div class="resource-meta">
                {f'<span>📍 {esc(r["address"])}</span>' if r.get("address") and r["address"] != "Statewide" else ''}
                {f'<span>📞 <a href="tel:{r["phones"][0]}" class="phone" style="color:var(--color-success)">{esc(r["phones"][0])}</a></span>' if r.get("phones") else ''}
                {f'<span>🌐 <a href="{esc(r["url"])}" target="_blank" rel="noopener noreferrer">{r["url"].replace("https://","").replace("http://","")}</a></span>' if r.get("url") else ''}
                {f'<span>🕐 {esc(r["hours"])}</span>' if r.get("hours") else ''}
                {f'<span>🗣 {", ".join(r["languages"])}</span>' if r.get("languages") and len(r["languages"]) > 1 else ''}
            </div>
            {f'<p>{esc(r["description"])}</p>' if r.get("description") else ''}
            <div class="chip-group">
                {"".join(f'<span class="tag tag-accent">{NEED_LABELS.get(n,n)}</span>' for n in needs)}
                {"".join(f'<span class="tag">{POP_LABELS.get(p,p)}</span>' for p in pops)}
            </div>
            <div class="resource-actions">{actions}</div>
        </div>

        {f'<div class="resource-details"><dl>{details}</dl></div>' if details else ''}

        {_map_and_service_area_html(r)}

        {related_html}

        <a href="/beacon/" class="btn btn-ghost" style="margin-top:var(--space-4)">← Back to Directory</a>
    </main>

    <footer class="footer">
        <div class="wrap">
            <p>Beacon Community Resource Directory</p>
            <p style="margin-top:var(--space-2)">Data from <a href="https://is5810.com/main/resources/">Isaiah 58:10 Ministries</a> · <a href="https://github.com/MrStewood/beacon">Source Code</a></p>
        </div>
    </footer>
</body>
</html>'''

def county_page(county, resources, data):
    """Generate HTML for a county landing page."""
    county_resources = [r for r in resources if r["county"] == county]
    needs_in_county = sorted(set(n for r in county_resources for n in r.get("needs", [])))

    resource_list = ""
    for r in county_resources:
        phones = f' · 📞 <a href="tel:{r["phones"][0]}">{esc(r["phones"][0])}</a>' if r.get("phones") else ""
        resource_list += f'<li><a href="/beacon/pages/resource/{r["id"]}.html">{esc(r["name"])}</a>{phones} — {esc(r.get("description","")[:100])}</li>\n'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{esc(county)} County Resources — Beacon</title>
    <meta name="description" content="Find food, shelter, healthcare, and crisis support in {esc(county)} County, Kentucky. {len(county_resources)} resources available.">
    <link rel="canonical" href="https://mrstewood.github.io/beacon/pages/county/{county.lower()}.html">
    <style>
        :root{{--primary:#1d4ed8;--bg:#f1f5f9;--card:#fff;--text:#0f172a;--muted:#64748b;--border:#e2e8f0;--radius:10px}}
        *{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.6}}
        .wrap{{max-width:900px;margin:0 auto;padding:0 1rem}}
        h1{{font-size:1.8rem;color:var(--primary);padding:1.5rem 0 .5rem}}
        .count{{color:var(--muted);margin-bottom:1rem}}
        .needs{{display:flex;flex-wrap:wrap;gap:.5rem;margin:1rem 0}}
        .need-link{{padding:.4rem .8rem;background:#dbeafe;color:#1e40af;border-radius:9999px;text-decoration:none;font-size:.85rem}}
        ul{{list-style:none;margin:1rem 0}}
        li{{padding:.5rem 0;border-bottom:1px solid var(--border);font-size:.9rem}}
        li a{{color:var(--primary);text-decoration:none;font-weight:500}}
        li a:hover{{text-decoration:underline}}
        .back{{display:inline-block;margin:1rem 0;color:var(--primary);text-decoration:none}}
        footer{{background:#0f172a;color:#94a3b8;padding:1rem 0;text-align:center;font-size:.8rem;margin-top:2rem}}
    </style>
</head>
<body>
<div class="wrap">
    <nav style="padding:1rem 0;font-size:.85rem;color:var(--muted)"><a href="/beacon/" style="color:var(--primary);text-decoration:none">Home</a> › <span>{esc(county)} County</span></nav>
    <h1>{esc(county)} County</h1>
    <p class="count">{len(county_resources)} resources available</p>
    <p>Browse by need:</p>
    <div class="needs">{"".join(f'<a href="/beacon/?county={county}&needs={n}" class="need-link">{NEED_LABELS.get(n,n)}</a>' for n in needs_in_county)}</div>
    <h2 style="font-size:1.2rem;margin:1rem 0 .5rem">All Resources</h2>
    <ul>{resource_list}</ul>
    <a href="/beacon/" class="back">← Back to Directory</a>
</div>
<footer><div class="wrap">Beacon Community Resource Directory</div></footer>
</body>
</html>'''

def need_page(need, resources):
    """Generate HTML for a need/category landing page."""
    need_resources = [r for r in resources if need in r.get("needs", [])]
    counties_in = sorted(set(r["county"] for r in need_resources if r["county"] != "Statewide"))

    resource_list = ""
    for r in need_resources[:50]:  # Limit to 50
        county_link = f' · <a href="/beacon/pages/county/{r["county"].lower()}.html">{esc(r["county"])}</a>' if r["county"] != "Statewide" else ""
        phones = f' · 📞 {esc(r["phones"][0])}' if r.get("phones") else ""
        resource_list += f'<li><a href="/beacon/pages/resource/{r["id"]}.html">{esc(r["name"])}</a>{county_link}{phones}</li>\n'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{NEED_LABELS.get(need, need)} — Beacon Resources</title>
    <meta name="description" content="Find {NEED_LABELS.get(need, need).lower()} resources in Kentucky. {len(need_resources)} services available.">
    <link rel="canonical" href="https://mrstewood.github.io/beacon/pages/need/{need}.html">
    <style>
        :root{{--primary:#1d4ed8;--bg:#f1f5f9;--card:#fff;--text:#0f172a;--muted:#64748b;--border:#e2e8f0;--radius:10px}}
        *{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.6}}
        .wrap{{max-width:900px;margin:0 auto;padding:0 1rem}}
        h1{{font-size:1.8rem;color:var(--primary);padding:1.5rem 0 .5rem}}
        .count{{color:var(--muted);margin-bottom:1rem}}
        .county-links{{display:flex;flex-wrap:wrap;gap:.5rem;margin:1rem 0}}
        .county-link{{padding:.4rem .8rem;background:#dcfce7;color:#166534;border-radius:9999px;text-decoration:none;font-size:.85rem}}
        ul{{list-style:none;margin:1rem 0}}
        li{{padding:.5rem 0;border-bottom:1px solid var(--border);font-size:.9rem}}
        li a{{color:var(--primary);text-decoration:none;font-weight:500}}
        li a:hover{{text-decoration:underline}}
        .back{{display:inline-block;margin:1rem 0;color:var(--primary);text-decoration:none}}
        footer{{background:#0f172a;color:#94a3b8;padding:1rem 0;text-align:center;font-size:.8rem;margin-top:2rem}}
    </style>
</head>
<body>
<div class="wrap">
    <nav style="padding:1rem 0;font-size:.85rem;color:var(--muted)"><a href="/beacon/" style="color:var(--primary);text-decoration:none">Home</a> › <span>{NEED_LABELS.get(need, need)}</span></nav>
    <h1>{NEED_LABELS.get(need, need)}</h1>
    <p class="count">{len(need_resources)} resources available</p>
    <p>Browse by county:</p>
    <div class="county-links">{"".join(f'<a href="/beacon/?county={c}&needs={need}" class="county-link">{esc(c)}</a>' for c in counties_in)}</div>
    <h2 style="font-size:1.2rem;margin:1rem 0 .5rem">Resources</h2>
    <ul>{resource_list}</ul>
    <a href="/beacon/" class="back">← Back to Directory</a>
</div>
<footer><div class="wrap">Beacon Community Resource Directory</div></footer>
</body>
</html>'''

def main():
    data = load_data()
    resources = data["resources"]

    # Create directories
    os.makedirs(PAGES_DIR / "resource", exist_ok=True)
    os.makedirs(PAGES_DIR / "county", exist_ok=True)
    os.makedirs(PAGES_DIR / "need", exist_ok=True)

    # Generate resource pages
    print(f"Generating {len(resources)} resource pages...")
    for r in resources:
        html = resource_page(r, data)
        path = PAGES_DIR / "resource" / f'{r["id"]}.html'
        with open(path, "w") as f:
            f.write(html)

    # Generate county pages
    counties = sorted(set(r["county"] for r in resources if r["county"] != "Statewide"))
    print(f"Generating {len(counties)} county pages...")
    for county in counties:
        html = county_page(county, resources, data)
        path = PAGES_DIR / "county" / f'{county.lower()}.html'
        with open(path, "w") as f:
            f.write(html)

    # Generate need pages
    needs = sorted(set(n for r in resources for n in r.get("needs", [])))
    print(f"Generating {len(needs)} need pages...")
    for need in needs:
        html = need_page(need, resources)
        path = PAGES_DIR / "need" / f'{need}.html'
        with open(path, "w") as f:
            f.write(html)

    # Generate sitemap
    print("Generating sitemap...")
    sitemap_urls = [
        ('https://mrstewood.github.io/beacon/', '1.0', 'weekly'),
    ]
    for r in resources:
        sitemap_urls.append((f'https://mrstewood.github.io/beacon/pages/resource/{r["id"]}.html', '0.7', 'monthly'))
    for county in counties:
        sitemap_urls.append((f'https://mrstewood.github.io/beacon/pages/county/{county.lower()}.html', '0.8', 'monthly'))
    for need in needs:
        sitemap_urls.append((f'https://mrstewood.github.io/beacon/pages/need/{need}.html', '0.8', 'monthly'))

    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url, prio, freq in sitemap_urls:
        sitemap += f'  <url><loc>{url}</loc><changefreq>{freq}</changefreq><priority>{prio}</priority></url>\n'
    sitemap += '</urlset>'

    with open(REPO_ROOT / "sitemap.xml", "w") as f:
        f.write(sitemap)

    print(f"Done! Generated {len(resources)} resource + {len(counties)} county + {len(needs)} need pages + sitemap")

if __name__ == "__main__":
    main()
