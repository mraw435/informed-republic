#!/usr/bin/env python3
"""
fetch_candidates.py — Informed Republic candidate data fetcher
--------------------------------------------------------------
Pulls 2026 Senate and House candidates from the FEC public API
and writes candidates.json to the current directory.

No API key required for basic use (rate limited to 1000 calls/hour).
For higher limits, register free at https://api.data.gov/signup/

Usage:
    python fetch_candidates.py

Output:
    candidates.json

Requirements:
    pip install requests
"""

import json, os, time
from datetime import datetime

try:
    import requests
except ImportError:
    print("ERROR: Run: pip install requests")
    exit(1)

FEC_BASE     = 'https://api.open.fec.gov/v1'
FEC_API_KEY  = os.environ.get('FEC_API_KEY', 'DEMO_KEY')  # DEMO_KEY works but is rate-limited
ELECTION_YEAR = 2026

STATE_NAMES = {
    'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California',
    'CO':'Colorado','CT':'Connecticut','DE':'Delaware','FL':'Florida','GA':'Georgia',
    'HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa',
    'KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland',
    'MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi',
    'MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire',
    'NJ':'New Jersey','NM':'New Mexico','NY':'New York','NC':'North Carolina',
    'ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania',
    'RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee',
    'TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington',
    'WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming'
}

# 2026 Senate Class 2 seats up for election
SENATE_SEATS_2026 = [
    'AK','AL','AR','CO','DE','GA','ID','IL','IA','KS','KY','LA',
    'ME','MA','MI','MN','MS','MT','NE','NH','NJ','NM','NC','OK',
    'OR','RI','SC','SD','TN','TX','VA','WA','WV','WI','WY'
]

def fec_get(endpoint, params):
    params['api_key'] = FEC_API_KEY
    params['per_page'] = 100
    url = f"{FEC_BASE}{endpoint}"
    try:
        res = requests.get(url, params=params, timeout=20)
        if res.status_code == 429:
            print("  Rate limited — waiting 10 seconds...")
            time.sleep(10)
            return fec_get(endpoint, params)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"  FEC API error: {e}")
        return None

def fetch_senate_candidates():
    print("Fetching Senate candidates...")
    data = fec_get('/candidates/', {
        'election_year': ELECTION_YEAR,
        'office': 'S',
        'is_active_candidate': True,
        'sort': 'name',
    })
    if not data:
        return []

    candidates = []
    for c in data.get('results', []):
        state = c.get('state', '')
        if state not in SENATE_SEATS_2026:
            continue
        candidates.append({
            'fec_id': c.get('candidate_id', ''),
            'name': (c.get('name') or '').title(),
            'party': normalize_party(c.get('party') or ''),
            'race_type': 'Senate',
            'state': STATE_NAMES.get(state, state),
            'state_abbr': state,
            'district': None,
            'incumbent': c.get('incumbent_challenge', '') == 'I',
            'incumbent_challenge': c.get('incumbent_challenge_full', ''),
            'campaign_url': '',
            'photo': None,
            'status': 'filed',
            'polling_url': '',
            'notes': ''
        })

    print(f"  Found {len(candidates)} Senate candidates")
    return candidates

def fetch_house_candidates():
    print("Fetching House candidates...")
    all_candidates = []

    # Fetch all states — FEC returns paginated results
    data = fec_get('/candidates/', {
        'election_year': ELECTION_YEAR,
        'office': 'H',
        'is_active_candidate': True,
        'sort': 'state',
    })

    if not data:
        return []

    results = data.get('results', [])

    # Handle pagination
    pagination = data.get('pagination', {})
    total_pages = pagination.get('pages', 1)
    if total_pages > 1:
        for page in range(2, min(total_pages + 1, 10)):  # cap at 10 pages
            time.sleep(0.3)
            page_data = fec_get('/candidates/', {
                'election_year': ELECTION_YEAR,
                'office': 'H',
                'is_active_candidate': True,
                'sort': 'state',
                'page': page,
            })
            if page_data:
                results.extend(page_data.get('results', []))

    for c in results:
        state = c.get('state', '')
        if state not in STATE_NAMES:
            continue
        district_raw = c.get('district', '0')
        try:
            district = int(district_raw)
        except:
            district = 0

        all_candidates.append({
            'fec_id': c.get('candidate_id', ''),
            'name': (c.get('name') or '').title(),
            'party': normalize_party(c.get('party') or ''),
            'race_type': 'House',
            'state': STATE_NAMES.get(state, state),
            'state_abbr': state,
            'district': district,
            'incumbent': c.get('incumbent_challenge', '') == 'I',
            'incumbent_challenge': c.get('incumbent_challenge_full', ''),
            'campaign_url': '',
            'photo': None,
            'status': 'filed',
            'polling_url': '',
            'notes': ''
        })

    print(f"  Found {len(all_candidates)} House candidates")
    return all_candidates

def normalize_party(code):
    mapping = {
        'DEM': 'Democrat',
        'REP': 'Republican',
        'IND': 'Independent',
        'LIB': 'Libertarian',
        'GRE': 'Green',
        'NNE': 'No Party',
        'OTH': 'Other',
        'UNK': 'Unknown',
        'W':   'Write-in',
    }
    if not code: return 'Unknown'
    return mapping.get(code.upper(), code)

def main():
    print(f"Informed Republic — FEC Candidate Fetch")
    print(f"Election year: {ELECTION_YEAR}")
    print(f"API key: {'Custom' if FEC_API_KEY != 'DEMO_KEY' else 'DEMO_KEY (rate limited)'}")
    print()

    senate = fetch_senate_candidates()
    time.sleep(0.5)
    house = fetch_house_candidates()

    all_candidates = senate + house

    # Sort: Senate first, then House; by state, then district
    all_candidates.sort(key=lambda c: (
        0 if c['race_type'] == 'Senate' else 1,
        c['state'],
        c['district'] or 0,
        c['name']
    ))

    output = {
        '_meta': {
            'description': 'Informed Republic — 2026 Election candidates',
            'last_updated': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'election_year': ELECTION_YEAR,
            'source': 'Federal Election Commission public API (api.open.fec.gov)',
            'total_candidates': len(all_candidates),
            'senate_candidates': len(senate),
            'house_candidates': len(house),
            'notes': (
                'campaign_url, photo, polling_url, and notes fields are '
                'manually maintained. status field: filed, primary_winner, '
                'general_candidate, winner, lost. '
                'Refresh periodically as candidates file and primaries conclude.'
            )
        },
        'cycle_status': {
            'status': 'active',
            'label': '2026 Midterm Elections',
            'description': 'Primary and general election coverage for the 119th Congress.',
            'election_day': '2026-11-03',
            'between_cycles_message': ''
        },
        'candidates': all_candidates
    }

    with open('candidates.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSuccess! Written to candidates.json")
    print(f"  Total candidates: {len(all_candidates)}")
    print(f"  Senate:           {len(senate)}")
    print(f"  House:            {len(house)}")
    print()
    print("Next steps:")
    print("  1. Add candidates.json to your GitHub repo")
    print("  2. Manually add campaign_url for notable candidates")
    print("  3. Add polling_url links to FiveThirtyEight/RCP for competitive races")
    print("  4. Upload to your server alongside elections.html")

if __name__ == '__main__':
    main()
