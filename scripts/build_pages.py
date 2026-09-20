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
        ('https://mrstewood.github.io/beacon/print/all.html', '0.8', 'weekly'),
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

    print(f"Done! Generated {len(resources)} resource + {len(counties)} county + {len(need)} need pages + sitemap")

if __name__ == "__main__":
    main()
