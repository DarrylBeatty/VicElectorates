#!/usr/bin/env python3
"""Generate data.js and HTML files from downloaded VEC CSV data."""

import csv
import json
import re
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse


def slugify(text):
    """Convert text to URL slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')


def load_electorates():
    """Load electorates from CSV."""
    electorates = []
    with open('data/vec/electorates.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            electorates.append(row)
    return electorates


def load_candidate_votes():
    """Load candidate votes from CSV."""
    votes = []
    with open('data/vec/candidate_votes.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            votes.append(row)
    return votes


def filter_valid_electorates(electorates):
    """Filter to only real electoral districts."""
    filtered = []
    exclude_keywords = [
        'state districts',
        'supplementary',
        'boundaries',
        'by-election',
        'timeline',
    ]
    
    for e in electorates:
        name = e['electorate'].lower()
        # Exclude specific non-electorate entries
        if any(keyword in name for keyword in exclude_keywords):
            continue
        # Keep entries that have "results" in the name and are actual electorates
        if 'results' in name and len(e['electorate'].strip()) > 2:
            # Extract the actual electorate name by removing "results"
            electorate_name = e['electorate'].replace(' results', '').strip()
            filtered.append({
                **e,
                'electorate': electorate_name,
            })
    
    return filtered


def get_election_results_for_electorate(electorate_name, votes_list):
    """Extract election results for an electorate from candidate votes."""
    electorate_votes = [v for v in votes_list if v['electorate'] == electorate_name]
    
    if not electorate_votes:
        return None
    
    # Parse votes - some are percentages, some are raw numbers
    candidates = []
    for vote in electorate_votes:
        vote_str = vote['votes'].strip()
        if '%' in vote_str:
            vote_count = float(vote_str.rstrip('%'))
        else:
            try:
                vote_count = float(vote['1st_pref_votes'] or 0)
            except (ValueError, TypeError):
                vote_count = 0
        
        candidates.append({
            'name': vote['candidate'],
            'party': vote['party'] or 'Independent',
            'votes': vote_count,
            'vote_str': vote_str,
        })
    
    # Sort by votes descending
    candidates.sort(key=lambda x: x['votes'], reverse=True)
    
    if candidates:
        top_candidate = candidates[0]
        return {
            'winner': f"{top_candidate['name']} ({top_candidate['party']})",
            'winner_name': top_candidate['name'],
            'winner_party': top_candidate['party'],
            'all_candidates': candidates,
        }
    
    return None


def generate_electorate_data(electorates_list, votes_list):
    """Generate data structure for all electorates."""
    electorates_data = []
    
    for e in electorates_list:
        name = e['electorate'].strip()
        slug = slugify(name)
        
        # Get election results
        results = get_election_results_for_electorate(name, votes_list)
        
        electorate_data = {
            'slug': slug,
            'name': name,
            'region': 'Victoria',  # Default region
            'mapEmbedUrl': f"https://www.google.com/maps?q={name}%20Victoria%20Australia&output=embed",
            'current_mp': {
                'name': e['current_mp'] or 'Unknown',
                'party': 'Unknown',
                'since': 'Unknown',
            },
            'lastElection': {
                'year': 2022,  # Default based on CSV metadata
                'winner': results['winner'] if results else 'Unknown',
                'twoPartyPreferred': 'Data not available',
                'voterTurnout': 'Data not available',
            },
        }
        
        electorates_data.append(electorate_data)
    
    return electorates_data


def generate_data_js(electorates_data, output_path='data.js'):
    """Generate data.js file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('window.electorates = ')
        json.dump(electorates_data, f, indent=2)
        f.write(';\n')
    
    print(f"Generated {output_path} with {len(electorates_data)} electorates")


def generate_electorate_html(electorate_data, output_dir='electorates'):
    """Generate individual electorate HTML file."""
    Path(output_dir).mkdir(exist_ok=True)
    
    slug = electorate_data['slug']
    output_path = Path(output_dir) / f"{slug}.html"
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{electorate_data['name']} - Victorian Electorates</title>
  <link rel="stylesheet" href="../styles.css" />
</head>
<body data-electorate-slug="{slug}">
  <header>
    <h1><a href="../index.html">← Victorian Electorates</a></h1>
  </header>

  <main>
    <h1 id="page-title">Loading...</h1>
    <div id="electorate-content"></div>
  </main>

  <script src="../data.js"></script>
  <script src="../electorate-page.js"></script>
</body>
</html>
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)


def generate_all_electorate_html(electorates_data, output_dir='electorates'):
    """Generate HTML files for all electorates."""
    Path(output_dir).mkdir(exist_ok=True)
    
    for electorate_data in electorates_data:
        generate_electorate_html(electorate_data, output_dir)
    
    print(f"Generated {len(electorates_data)} HTML files in {output_dir}/")


def main():
    print("Loading CSV data...")
    electorates = load_electorates()
    votes = load_candidate_votes()
    
    print(f"Loaded {len(electorates)} electorates and {len(votes)} candidate vote records")
    
    # Filter to valid electorates
    electorates = filter_valid_electorates(electorates)
    print(f"Filtered to {len(electorates)} valid electorates")
    
    # Generate electorate data
    electorates_data = generate_electorate_data(electorates, votes)
    
    # Generate data.js
    generate_data_js(electorates_data)
    
    # Generate HTML files
    generate_all_electorate_html(electorates_data)
    
    print("\n✓ Done! Generated data.js and HTML files for all electorates")
    print(f"Total electorates: {len(electorates_data)}")


if __name__ == '__main__':
    main()
