#!/usr/bin/env python3
"""Generate CSV from resources.json (v2 schema)."""
import json, csv, os
from config import DATA_DIR

def main():
    with open(DATA_DIR / 'resources.json') as f:
        data = json.load(f)

    resources = data['resources']

    # Main CSV
    with open(DATA_DIR / 'resources.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([
            'Name', 'Address', 'City', 'State', 'Zip', 'County',
            'Phone', 'Website', 'Needs', 'Service Types', 'Populations',
            'Description', 'Eligibility', 'Cost', 'Hours', 'Languages',
            'What to Bring', 'Referral Required', 'Intake Hours', 'Map URL',
            'Status', 'Intake Process', 'Last Verified', 'Confidence', 'Notes'
        ])
        for r in resources:
            w.writerow([
                r['name'],
                r.get('address', ''),
                r.get('city', ''),
                r.get('state', ''),
                r.get('zip', ''),
                r.get('county', ''),
                '; '.join(r.get('phones', [])),
                r.get('url', '') or '',
                '; '.join(r.get('needs', [])),
                '; '.join(r.get('service_types', [])),
                '; '.join(r.get('populations', [])),
                r.get('description', ''),
                r.get('eligibility', '') or '',
                r.get('cost', ''),
                r.get('hours', '') or '',
                '; '.join(r.get('languages', [])),
                r.get('what_to_bring', '') or '',
                r.get('referral_required', '') if r.get('referral_required') is not None else '',
                r.get('intake_hours', '') or '',
                r.get('map_url', '') or '',
                r.get('status', ''),
                r.get('intake_process', '') or '',
                r.get('last_verified', ''),
                r.get('confidence', ''),
                r.get('notes', '') or ''
            ])

    # Per-county CSVs
    by_county = {}
    for r in resources:
        c = r.get('county', 'Unknown')
        by_county.setdefault(c, []).append(r)

    os.makedirs(DATA_DIR / 'csv-by-county', exist_ok=True)
    for county, items in sorted(by_county.items()):
        fname = county.lower().replace(' ', '-')
        with open(DATA_DIR / 'csv-by-county' / f'{fname}.csv', 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['Name', 'Address', 'Phone', 'Website', 'Needs', 'Description', 'Hours', 'Cost', 'Status'])
            for r in items:
                w.writerow([
                    r['name'],
                    r.get('address', ''),
                    '; '.join(r.get('phones', [])),
                    r.get('url', '') or '',
                    '; '.join(r.get('needs', [])),
                    r.get('description', ''),
                    r.get('hours', '') or '',
                    r.get('cost', ''),
                    r.get('status', '')
                ])

    print(f"Generated resources.csv ({len(resources)} rows)")
    print(f"Generated {len(by_county)} county CSVs")

if __name__ == '__main__':
    main()
