#!/usr/bin/env python3
"""
Backfill papers from the past N days into Supabase.
Usage: python backfill.py [days]

Requires environment variables:
  SUPABASE_URL
  SUPABASE_KEY
"""
import os
import sys
import json
import subprocess
from pathlib import Path

try:
    from supabase import create_client, Client
except ImportError:
    print("ERROR: supabase package not installed")
    print("Run: pip install supabase --break-system-packages")
    sys.exit(1)

def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7

    # Check environment
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: Environment variables required:")
        print("  SUPABASE_URL")
        print("  SUPABASE_KEY")
        sys.exit(1)

    print(f"Backfilling papers from past {days} days...")
    print(f"Supabase: {SUPABASE_URL}")
    print("=" * 60)

    # Connect to Supabase
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Get existing papers
    print("\n1. Checking existing papers...")
    response = supabase.table('papers').select('arxiv_id').execute()
    existing_ids = {r['arxiv_id'] for r in response.data}
    print(f"   Found {len(existing_ids)} existing papers")

    # Fetch papers
    print(f"\n2. Fetching papers from past {days} days...")
    scripts_dir = Path(__file__).parent
    keywords_file = scripts_dir.parent / "data" / "keywords.json"
    output_file = scripts_dir / "backfill_papers.json"

    result = subprocess.run([
        sys.executable,
        str(scripts_dir / "fetch_week.py"),
        str(keywords_file),
        str(output_file),
        str(days)
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print("ERROR: fetch_week.py failed")
        print(result.stderr)
        sys.exit(1)

    print(result.stdout)

    # Load fetched papers
    with open(output_file) as f:
        data = json.load(f)

    papers = data['kept']
    print(f"\n3. Processing {len(papers)} papers...")

    # Filter out existing papers
    new_papers = [p for p in papers if p['arxiv_id'] not in existing_ids]
    print(f"   {len(new_papers)} new papers to add")

    if not new_papers:
        print("\n✓ No new papers to add")
        return

    # Prepare papers for Supabase
    print("\n4. Writing to Supabase...")
    success_count = 0
    error_count = 0

    for paper in new_papers:
        try:
            # Prepare paper data
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

            # Insert paper
            supabase.table('papers').insert(paper_data).execute()
            success_count += 1
            print(f"   ✓ {paper['arxiv_id']}: {paper['title'][:60]}...")

        except Exception as e:
            error_count += 1
            print(f"   ✗ {paper['arxiv_id']}: {e}")

    print("\n" + "=" * 60)
    print(f"Backfill complete:")
    print(f"  New papers added: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total papers in database: {len(existing_ids) + success_count}")

if __name__ == '__main__':
    main()
