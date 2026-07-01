"""
generate_members.py
-------------------
Run this script once to generate members.json for the Informed Republic
officials directory. Pulls member data AND committee assignments from the
unitedstates/congress-legislators public domain dataset (CC0 license).

Usage:
    python generate_members.py

Output:
    members.json  (in the same folder as this script)

Requirements:
    Python 3.8+ with requests installed:
    pip install requests
"""

import json
import sys
try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

MEMBERS_URL    = "https://unitedstates.github.io/congress-legislators/legislators-current.json"
COMMITTEES_URL = "https://unitedstates.github.io/congress-legislators/committee-membership-current.json"

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
    'WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming','DC':'District of Columbia',
    'PR':'Puerto Rico','GU':'Guam','VI':'Virgin Islands','AS':'American Samoa',
    'MP':'Northern Mariana Islands'
}

def fetch(url, label):
    print(f"Fetching {label}...")
    resp = requests.get(url, timeout=30,
                        headers={'User-Agent': 'InformedRepublic/1.0 civic-education'})
    resp.raise_for_status()
    print(f"  OK — {len(resp.content):,} bytes")
    return resp.json()

def build_member_id(chamber, state_abbr, district, bioguide):
    if chamber == 'House':
        d = str(district).zfill(2) if district is not None else '00'
        return f"{state_abbr}-H-{d}"
    return f"{state_abbr}-S-{bioguide}"

def clean_office(office_str):
    if not office_str:
        return ''
    if 'Washington DC' in office_str:
        office_str = office_str.split('Washington DC')[0].strip().rstrip(';,').strip()
    return office_str

def build_display_name(chamber, first, last, suffix):
    prefix = 'Rep.' if chamber == 'House' else 'Sen.'
    parts = [prefix, first, last]
    if suffix:
        parts.append(suffix)
    return ' '.join(p for p in parts if p)

def earliest_year(terms):
    years = [int(t.get('start', '9999')[:4]) for t in terms if t.get('start')]
    return min(years) if years else None

def build_committee_lookup(committee_data):
    """
    committee-membership-current.json structure:
    {
      "HSAP": [ {"bioguide": "A000055", "name": "Robert Aderholt", "party": "Republican", ...}, ... ],
      "SSAF": [ ... ],
      ...
    }
    Returns a dict: { bioguide_id: [committee_name, ...] }
    """
    # We also need committee names — they're the keys (thomas_ids like HSAP, SSAF).
    # The committee-membership file doesn't include full names, but we can build
    # readable names from the thomas_id prefix convention:
    #   H = House, S = Senate, J = Joint
    # We'll include the thomas_id as a fallback label.
    
    # Fetch committees to get full names
    try:
        committees_meta = fetch(
            "https://unitedstates.github.io/congress-legislators/committees-current.json",
            "committee names"
        )
        # Build lookup: thomas_id -> full name
        committee_names = {}
        for c in committees_meta:
            tid = c.get('thomas_id', '')
            name = c.get('name', tid)
            committee_names[tid] = name
            # Also index subcommittees
            for sub in c.get('subcommittees', []):
                sub_id = tid + sub.get('thomas_id', '')
                committee_names[sub_id] = f"{name} — {sub.get('name', '')}"
    except Exception as e:
        print(f"  Warning: could not fetch committee names ({e}). Using IDs as labels.")
        committee_names = {}

    lookup = {}
    for committee_id, members in committee_data.items():
        full_name = committee_names.get(committee_id, committee_id)
        for m in members:
            bio = m.get('bioguide', '')
            if not bio:
                continue
            if bio not in lookup:
                lookup[bio] = []
            # Only add the committee (not subcommittee) to keep cards clean
            # Subcommittees have longer IDs (e.g. HSAP01)
            if len(committee_id) <= 4 and full_name not in lookup[bio]:
                lookup[bio].append(full_name)
    return lookup

def main():
    try:
        raw = fetch(MEMBERS_URL, "member data")
        committee_data = fetch(COMMITTEES_URL, "committee assignments")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"\nBuilding committee lookup...")
    committee_lookup = build_committee_lookup(committee_data)
    print(f"  Committee assignments found for {len(committee_lookup)} members")

    print("\nTransforming member records...")
    members = []
    skipped = 0

    for leg in raw:
        terms = leg.get('terms', [])
        if not terms:
            skipped += 1
            continue

        current_term = terms[-1]
        term_type = current_term.get('type', '')
        if term_type not in ('rep', 'sen'):
            skipped += 1
            continue

        chamber = 'House' if term_type == 'rep' else 'Senate'
        state_abbr = current_term.get('state', '')
        party = current_term.get('party', '')
        district = current_term.get('district', None)
        bioguide = leg.get('id', {}).get('bioguide', '')

        name_obj = leg.get('name', {})
        first = name_obj.get('nickname') or name_obj.get('first', '')
        last = name_obj.get('last', '')
        suffix = name_obj.get('suffix', '')

        committees = committee_lookup.get(bioguide, [])

        member = {
            "id": build_member_id(chamber, state_abbr, district, bioguide),
            "bioguide_id": bioguide,
            "chamber": chamber,
            "first_name": first,
            "last_name": last,
            "display_name": build_display_name(chamber, first, last, suffix),
            "party": party,
            "state": STATE_NAMES.get(state_abbr, state_abbr),
            "state_abbr": state_abbr,
            "district": district if chamber == 'House' else None,
            "phone": current_term.get('phone', ''),
            "office_room": clean_office(current_term.get('office', '')),
            "photo_url": f"https://unitedstates.github.io/images/congress/225x275/{bioguide}.jpg",
            "photo": None,
            "official_url": current_term.get('url', ''),
            "profile": {
                "bio": "",
                "committees": committees,
                "years_served": earliest_year(terms),
                "notes": ""
            }
        }
        members.append(member)

    members.sort(key=lambda m: (
        0 if m['chamber'] == 'Senate' else 1,
        m['state'],
        m['district'] if m['district'] is not None else 0
    ))

    house_count = sum(1 for m in members if m['chamber'] == 'House')
    senate_count = sum(1 for m in members if m['chamber'] == 'Senate')
    with_committees = sum(1 for m in members if m['profile']['committees'])

    output = {
        "_meta": {
            "description": "Informed Republic — Members of Congress directory",
            "last_updated": "2026-06-30",
            "source": "unitedstates/congress-legislators (CC0 public domain), https://unitedstates.github.io/congress-legislators/",
            "total_members": len(members),
            "house_count": house_count,
            "senate_count": senate_count,
            "notes": (
                "Photo paths are relative to /assets/photos/members/. "
                "District is null for Senate members. "
                "years_served is the year the member was first sworn in. "
                "Committees lists full committee assignments only (not subcommittees). "
                "Refresh each new Congress and after special elections or resignations."
            )
        },
        "members": members
    }

    out_path = "members.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSuccess! Written to {out_path}")
    print(f"  Total members:          {len(members)}")
    print(f"  House:                  {house_count}")
    print(f"  Senate:                 {senate_count}")
    print(f"  Members with committees:{with_committees}")
    print(f"  Skipped:                {skipped}")
    print("\nNext step: copy members.json into your site folder alongside index.html.")

if __name__ == "__main__":
    main()
