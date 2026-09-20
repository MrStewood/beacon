#!/usr/bin/env python3
"""Generate print-ready HTML pages for counties and needs."""

import json
import os
import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
PRINT_DIR = REPO_ROOT / "print"

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

def esc(s):
    if not s: return ""
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def qr_url(text):
    """Generate QR code URL using free API."""
    return f"https://api.qrserver.com/v1/create-qr-code/?size=100x100&data={text}"

def print_head(title, subtitle="", large=False):
    font_size = "12pt" if large else "10pt"
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{esc(title)} — Beacon Print Guide</title>
<style>
@page {{margin: 0.6in; size: letter;}}
@page :first {{margin-top: 0.4in;}}
body {{font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; font-size: {font_size}; line-height: 1.4; color: #0f172a;}}
.header {{display: flex; justify-content: space-between; align-items: start; border-bottom: 2px solid #1d4ed8; padding-bottom: 8pt; margin-bottom: 12pt;}}
.header-left h1 {{font-size: 18pt; color: #1d4ed8; margin: 0;}}
.header-left p {{font-size: 9pt; color: #64748b; margin: 2pt 0 0;}}
.header-right {{text-align: right;}}
.header-right img {{width: 60pt; height: 60pt;}}
.header-right p {{font-size: 7pt; color: #64748b; margin: 2pt 0 0;}}
.section {{page-break-inside: avoid; margin-bottom: 10pt;}}
.section-header {{background: #f1f5f9; padding: 4pt 8pt; font-weight: 600; font-size: 11pt; color: #1d4ed8; margin-bottom: 6pt; page-break-after: avoid;}}
.resource {{border-bottom: 1px solid #e2e8f0; padding: 6pt 0; page-break-inside: avoid;}}
.resource:last-child {{border-bottom: none;}}
.resource-name {{font-weight: 600; font-size: {font_size};}}
.resource-meta {{font-size: 8pt; color: #475569; margin-top: 2pt;}}
.resource-meta span {{margin-right: 12pt;}}
.resource-desc {{font-size: 8pt; color: #64748b; margin-top: 2pt;}}
.resource-tags {{font-size: 7pt; color: #1d4ed8; margin-top: 2pt;}}
.footer {{position: fixed; bottom: 0; left: 0; right: 0; border-top: 1px solid #e2e8f0; padding: 6pt 0.6in; font-size: 7pt; color: #94a3b8; display: flex; justify-content: space-between;}}
.disclaimer {{background: #fef3c7; border: 1px solid #fbbf24; border-radius: 4pt; padding: 6pt 8pt; font-size: 8pt; color: #92400e; margin: 10pt 0;}}
@media print {{
    .no-print {{display: none;}}
    .footer {{position: fixed; bottom: 0;}}
}}
@media large-print {{
    body {{font-size: 16pt; line-height: 1.6;}}
    .resource-name {{font-size: 16pt;}}
    .resource-meta {{font-size: 12pt;}}
    .resource-desc {{font-size: 12pt;}}
}}
</style>
</head>
<body>
'''

def print_footer():
    return '''
<div class="footer">
    <span>Beacon Community Resource Directory — mrstewood.github.io/beacon</span>
    <span>Generated: ''' + __import__('datetime').datetime.now().strftime('%Y-%m-%d') + '''</span>
</div>
</body></html>'''

def resource_to_html(r):
    phones = ' · '.join(r.get("phones", []))
    tags = ' · '.join([NEED_LABELS.get(n, n) for n in r.get("needs", [])[:3]])
    return f'''<div class="resource">
<div class="resource-name">{esc(r["name"])}</div>
<div class="resource-meta">
    <span>📍 {esc(r.get("address", r.get("county", "")))}</span>
    <span>📞 {esc(phones)}</span>
    {f'<span>🌐 {esc(r["url"].replace("https://","").replace("http://",""))}</span>' if r.get("url") else ''}
    {f'<span>🕐 {esc(r["hours"])}</span>' if r.get("hours") else ''}
    {f'<span>💰 {esc(r["cost"])}</span>' if r.get("cost") and r["cost"] != "unknown" else ''}
</div>
{f'<div class="resource-desc">{esc(r.get("description", "")[:150])}</div>' if r.get("description") else ''}
{f'<div class="resource-tags">{esc(tags)}</div>' if tags else ''}
</div>'''

def generate_county_print(county, resources):
    county_resources = [r for r in resources if r["county"] == county]
    county_resources.sort(key=lambda x: x["name"])

    # Group by need
    by_need = {}
    for r in county_resources:
        for n in r.get("needs", []):
            by_need.setdefault(n, []).append(r)

    html = print_head(f"{county} County Resource Guide", f"{len(county_resources)} resources")
    qr = qr_url(f"https://mrstewood.github.io/beacon/?county={county}")

    html += f'''<div class="header">
<div class="header-left">
    <h1>{esc(county)} County</h1>
    <p>Community Resource Guide — {len(county_resources)} resources</p>
</div>
<div class="header-right">
    <img src="{qr}" alt="QR code to live directory">
    <p>Scan for live updates</p>
</div>
</div>

<div class="disclaimer">
<strong>Important:</strong> Always verify hours, eligibility, and availability directly with the provider.
Resource information may change. Scan the QR code or visit mrstewood.github.io/beacon for current data.
</div>
'''

    for need in sorted(by_need.keys()):
        need_resources = by_need[need]
        html += f'<div class="section">'
        html += f'<div class="section-header">{NEED_LABELS.get(need, need)}</div>'
        for r in need_resources[:15]:  # Limit per section
            html += resource_to_html(r)
        html += '</div>'

    html += print_footer()
    return html

def generate_need_print(need, resources):
    need_resources = [r for r in resources if need in r.get("needs", []) and r["county"] != "Statewide"]
    need_resources.sort(key=lambda x: (x["county"], x["name"]))

    # Group by county
    by_county = {}
    for r in need_resources:
        by_county.setdefault(r["county"], []).append(r)

    html = print_head(f"{NEED_LABELS.get(need, need)} — Resource Guide", f"{len(need_resources)} resources across {len(by_county)} counties")
    qr = qr_url(f"https://mrstewood.github.io/beacon/?needs={need}")

    html += f'''<div class="header">
<div class="header-left">
    <h1>{NEED_LABELS.get(need, need)}</h1>
    <p>Resource Guide — {len(need_resources)} resources across {len(by_county)} counties</p>
</div>
<div class="header-right">
    <img src="{qr}" alt="QR code to live directory">
    <p>Scan for live updates</p>
</div>
</div>

<div class="disclaimer">
<strong>Important:</strong> Always verify hours, eligibility, and availability directly with the provider.
Resource information may change. Scan the QR code or visit mrstewood.github.io/beacon for current data.
</div>
'''

    for county in sorted(by_county.keys()):
        county_resources = by_county[county]
        html += f'<div class="section">'
        html += f'<div class="section-header">{esc(county)} County ({len(county_resources)} resources)</div>'
        for r in county_resources[:10]:
            html += resource_to_html(r)
        html += '</div>'

    html += print_footer()
    return html

def main():
    with open(DATA_DIR / "resources.json") as f:
        data = json.load(f)
    resources = data["resources"]

    os.makedirs(PRINT_DIR / "county", exist_ok=True)
    os.makedirs(PRINT_DIR / "need", exist_ok=True)

    # Generate county print pages
    counties = sorted(set(r["county"] for r in resources if r["county"] != "Statewide"))
    print(f"Generating {len(counties)} county print pages...")
    for county in counties:
        html = generate_county_print(county, resources)
        path = PRINT_DIR / "county" / f'{county.lower()}.html'
        with open(path, "w") as f:
            f.write(html)

    # Generate need print pages
    needs = sorted(set(n for r in resources for n in r.get("needs", [])))
    print(f"Generating {len(needs)} need print pages...")
    for need in needs:
        html = generate_need_print(need, resources)
        path = PRINT_DIR / "need" / f'{need}.html'
        with open(path, "w") as f:
            f.write(html)

    print(f"Done! Generated {len(counties)} county + {len(needs)} need print pages")

if __name__ == "__main__":
    main()
