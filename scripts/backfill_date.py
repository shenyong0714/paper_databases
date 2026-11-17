#!/usr/bin/env python3
"""
Backfill papers from a specific date range.
Usage: python backfill_date.py START_DATE END_DATE

Example:
  python backfill_date.py 2026-11-10 2026-11-11

Dates are in UTC, format: YYYY-MM-DD
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

try:
    from supabase import create_client, Client
except ImportError:
    print("ERROR: supabase package not installed")
    sys.exit(1)

# Import from fetch_week
sys.path.insert(0, str(Path(__file__).parent))
from fetch_week import fetch_arxiv_category, rx

def main():
    if len(sys.argv) < 3:
        print("Usage: python backfill_date.py START_DATE END_DATE")
        print("\nExample:")
        print("  python backfill_date.py 2026-11-10 2026-11-11")
        print("\nDates are in UTC, format: YYYY-MM-DD")
        sys.exit(1)

    start_date_str = sys.argv[1]
    end_date_str = sys.argv[2]

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError as e:
        print(f"ERROR: Invalid date format: {e}")
        print("Use YYYY-MM-DD format")
        sys.exit(1)

    if start_date >= end_date:
        print("ERROR: START_DATE must be before END_DATE")
        sys.exit(1)

    # Check environment
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_KEY")
        sys.exit(1)

    print(f"Backfilling papers from {start_date_str} to {end_date_str} (UTC)")
    print("=" * 60)

    # Connect to Supabase
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Get existing papers
    response = supabase.table('papers').select('arxiv_id').execute()
    existing_ids = {r['arxiv_id'] for r in response.data}
    print(f"Existing papers in database: {len(existing_ids)}")

    # Load keywords
    scripts_dir = Path(__file__).parent
    keywords_file = scripts_dir.parent / "data" / "keywords.json"
    with open(keywords_file) as f:
        data = json.load(f)
        cfg = data.get("data", data)

    groups = [(g["w"], [(t, rx(t)) for t in g["terms"]]) for g in cfg["groups"]]
    categories = cfg['categories']

    print(f"Categories: {categories}")
    print()

    # Fetch papers from all categories
    all_papers = {}

    for category in categories:
        print(f"Fetching {category}...")

        # Fetch more papers to ensure we get the date range
        entries, error = fetch_arxiv_category(category, days_back=14, max_results=200, retries=5)

        if error:
            print(f"  ERROR: {error}")
            continue

        print(f"  Fetched {len(entries)} papers")

        # Filter by date range
        filtered = []
        for entry in entries:
            pub_str = entry.get('published', '')
            if pub_str:
                # Parse published date (format: 2026-11-10T12:34:56Z)
                try:
                    pub_date = datetime.fromisoformat(pub_str.replace('Z', '+00:00'))
                    if start_date <= pub_date < end_date:
                        filtered.append(entry)
                except Exception as e:
                    print(f"  Warning: Could not parse date {pub_str}: {e}")

        print(f"  In date range: {len(filtered)} papers")

        for entry in filtered:
            aid = entry['arxiv_id']
            if aid not in all_papers:
                all_papers[aid] = entry

        # Wait a bit between categories
        if category != categories[-1]:
            import time
            print(f"  Waiting 5s...")
            time.sleep(5)

    print(f"\nTotal papers in date range: {len(all_papers)}")

    # Score papers
    kept = []
    for paper in all_papers.values():
        txt = paper['title'] + " " + paper['abstract']
        score = 0
        matched = []

        for w, terms in groups:
            for term_text, term_rx in terms:
                if term_rx.search(txt):
                    score += w
                    matched.append(term_text)
                    break

        if score >= cfg["min_score"]:
            paper['score'] = score
            paper['matched'] = matched
            kept.append(paper)

    kept.sort(key=lambda p: -p['score'])
    print(f"Matched (score >= {cfg['min_score']}): {len(kept)} papers")

    # Show all matched papers
    if kept:
        print("\nMatched papers:")
        for p in kept:
            print(f"  [{p['score']}] {p['arxiv_id']} - {p['title']}")
            print(f"      Published: {p['published']}")
            print(f"      Matched: {', '.join(p['matched'])}")

    # Filter new papers
    new_papers = [p for p in kept if p['arxiv_id'] not in existing_ids]
    print(f"\nNew papers to add: {len(new_papers)}")

    if not new_papers:
        print("\n✓ No new papers to add")
        return

    # Insert papers
    print("\nInserting papers...")
    success = 0
    for paper in new_papers:
        try:
            paper_data = {
                'arxiv_id': paper['arxiv_id'],
                'title': paper['title'],
                'abstract': paper['abstract'],
                'authors': paper['authors'],
                'cat': paper['cat'],
                'score': paper['score'],
                'matched': paper['matched'],
                'state': 'week'
            }
            supabase.table('papers').insert(paper_data).execute()
            print(f"  ✓ {paper['arxiv_id']}: {paper['title'][:60]}...")
            success += 1
        except Exception as e:
            print(f"  ✗ {paper['arxiv_id']}: {e}")

    print(f"\n✓ Added {success}/{len(new_papers)} papers")

    # Total count
    response = supabase.table('papers').select('arxiv_id', count='exact').execute()
    print(f"Total papers in database: {response.count}")

if __name__ == '__main__':
    main()
