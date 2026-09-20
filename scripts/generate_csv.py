#!/usr/bin/env python3
"""Generate CSV from resources.json (v2 schema)."""
import json, csv, os

def main():
    with open('/tmp/beacon/data/resources.json') as f:
        data = json.load(f)

    resources = data['resources']

    # Main CSV
    with open('/tmp/beacon/data/resources.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([
            'Name', 'Address', 'City', 'State', 'Zip', 'County',
            'Phone', 'Website', 'Needs', 'Service Types', 'Populations',
            'Description', 'Eligibility', 'Cost', 'Hours', 'Status',
            'Intake Process', 'Last Verified', 'Confidence', 'Notes'
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

    os.makedirs('/tmp/beacon/data/csv-by-county', exist_ok=True)
    for county, items in sorted(by_county.items()):
        fname = county.lower().replace(' ', '-')
        with open(f'/tmp/beacon/data/csv-by-county/{fname}.csv', 'w', newline='') as f:
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
