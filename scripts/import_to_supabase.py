#!/usr/bin/env python3
"""
Import papers from migration_data.json to Supabase.

Usage:
    export SUPABASE_URL='https://xxxxx.supabase.co'
    export SUPABASE_KEY='your-service-role-key'
    python scripts/import_to_supabase.py migration_data.json
"""

import json
import os
import sys
from pathlib import Path

try:
    from supabase import create_client, Client
except ImportError:
    print("ERROR: supabase package not installed")
    print("Run: pip install supabase")
    sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("Usage: python import_to_supabase.py migration_data.json")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    if not input_file.exists():
        print(f"ERROR: File not found: {input_file}")
        sys.exit(1)

    # Check environment
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: Environment variables required:")
        print("  SUPABASE_URL")
        print("  SUPABASE_KEY")
        print("\nSet them with:")
        print("  export SUPABASE_URL='https://xxxxx.supabase.co'")
        print("  export SUPABASE_KEY='your-service-role-key'")
        sys.exit(1)

    # Connect to Supabase
    print(f"Connecting to Supabase: {SUPABASE_URL}")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Load data
    print(f"Loading data from: {input_file}")
    with open(input_file) as f:
        data = json.load(f)

    papers = data.get('papers', [])
    if not papers:
        print("No papers found in input file")
        return

    print(f"Found {len(papers)} papers to import")
    print("=" * 60)

    # Import papers
    imported = 0
    skipped = 0
    errors = []

    for paper in papers:
        arxiv_id = paper.get('arxiv_id')
        if not arxiv_id:
            print(f"⚠ Skipping paper with no arxiv_id")
            skipped += 1
            continue

        try:
            # Upsert paper (insert or update)
            response = supabase.table('papers').upsert(paper).execute()

            if response.data:
                imported += 1
                title = paper.get('title', '')[:60]
                state = paper.get('state', 'week')
                print(f"✓ {arxiv_id} [{state}]: {title}")
            else:
                skipped += 1
                print(f"⚠ {arxiv_id}: No data returned (may already exist)")

        except Exception as e:
            errors.append(f"{arxiv_id}: {str(e)}")
            print(f"✗ {arxiv_id}: {e}")

    # Summary
    print("=" * 60)
    print(f"\nImport complete:")
    print(f"  Imported: {imported}")
    print(f"  Skipped:  {skipped}")
    print(f"  Errors:   {len(errors)}")

    if errors:
        print("\nErrors:")
        for err in errors[:10]:
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")

    print(f"\nTotal papers in Supabase: ", end="")
    try:
        count_response = supabase.table('papers').select('arxiv_id', count='exact').execute()
        print(count_response.count)
    except Exception as e:
        print(f"(could not count: {e})")

    print("\nNote: Figures are referenced by URL in the papers.")
    print("If your artifact had figures stored, you may need to:")
    print("1. Download figures from artifact storage")
    print("2. Upload to Supabase storage bucket 'figures/'")
    print("3. Update figure URLs in papers table")

if __name__ == '__main__':
    main()
