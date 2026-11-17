#!/usr/bin/env python3
"""
Daily arXiv update script for GitHub Actions.
Fetches papers, extracts figures, and writes to Supabase.
"""
import os
import sys
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from supabase import create_client, Client

# Supabase setup
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY environment variables required")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / 'data'
WORK_DIR = Path('/tmp/arxiv_work')
WORK_DIR.mkdir(exist_ok=True)

def run_fetcher():
    """Step 1: Fetch new papers from arXiv"""
    print("=" * 60)
    print("STEP 1: Fetching from arXiv")
    print("=" * 60)

    keywords_file = DATA_DIR / 'keywords.json'
    output_file = WORK_DIR / 'fetch.json'

    result = subprocess.run([
        'python3', SCRIPT_DIR / 'fetcher.py',
        str(keywords_file), str(output_file)
    ], capture_output=True, text=True)

    print(result.stdout)
    if result.returncode == 2:
        print("FETCH_ANOMALY detected")
        return None, {"error": "FETCH_ANOMALY", "stderr": result.stderr}
    elif result.returncode == 3:
        print("All feeds failed")
        return None, {"error": "ALL_FEEDS_FAILED", "stderr": result.stderr}
    elif result.returncode != 0:
        print(f"Fetcher failed with code {result.returncode}")
        return None, {"error": f"exit_{result.returncode}", "stderr": result.stderr}

    if not output_file.exists():
        return None, {"error": "fetch.json not created"}

    with open(output_file) as f:
        fetch_data = json.load(f)

    return fetch_data, None

def load_existing_papers():
    """Load existing papers from Supabase"""
    try:
        response = supabase.table('papers').select('arxiv_id,state,figures,text_parts').execute()
        return {p['arxiv_id']: p for p in response.data}
    except Exception as e:
        print(f"Warning: Could not load existing papers: {e}")
        return {}

def run_extraction(fetch_data, existing_papers):
    """Step 2: Extract figures from PDFs"""
    print("\n" + "=" * 60)
    print("STEP 2: Extracting figures")
    print("=" * 60)

    # Install pymupdf
    subprocess.run(['pip', 'install', 'pymupdf', '--quiet'], check=True)

    # Determine which papers need extraction
    to_extract = []
    for paper in fetch_data.get('papers', []):
        pid = paper['arxiv_id']
        existing = existing_papers.get(pid, {})
        # Extract if: new paper OR existing but no figures/text
        if not existing or (not existing.get('figures') and not existing.get('text_parts')):
            to_extract.append(paper)

    if not to_extract:
        print("No papers need extraction")
        return [], 0

    # Write papers to extract
    extract_input = WORK_DIR / 'to_extract.json'
    with open(extract_input, 'w') as f:
        json.dump({'papers': to_extract}, f)

    # Run extractor
    result = subprocess.run([
        'python3', SCRIPT_DIR / 'extract_figs.py',
        str(extract_input), str(WORK_DIR)
    ], capture_output=True, text=True)

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    # Collect extracted data
    extracted = []
    for paper in to_extract:
        pid = paper['arxiv_id']
        paper_dir = WORK_DIR / pid
        if not paper_dir.exists():
            continue

        # Read metadata
        meta_file = paper_dir / 'meta.json'
        if meta_file.exists():
            with open(meta_file) as f:
                meta = json.load(f)
                extracted.append({
                    'arxiv_id': pid,
                    'figures': meta.get('figures', []),
                    'text_parts': meta.get('text_parts', 0),
                    'extract_error': meta.get('error')
                })

    return extracted, len(to_extract)

def write_to_supabase(fetch_data, extracted_data):
    """Step 3: Write everything to Supabase"""
    print("\n" + "=" * 60)
    print("STEP 3: Writing to Supabase")
    print("=" * 60)

    added = 0
    updated = 0
    errors = []

    # Create a map of extracted data
    extracted_map = {e['arxiv_id']: e for e in extracted_data}

    # Process each paper
    for paper in fetch_data.get('papers', []):
        pid = paper['arxiv_id']

        # Merge with extraction data
        if pid in extracted_map:
            paper.update(extracted_map[pid])

        # Upload figures to Supabase storage
        if paper.get('figures'):
            uploaded_figs = []
            for fig in paper['figures']:
                fig_path = WORK_DIR / pid / f"fig{fig['n']:02d}.png"
                if fig_path.exists():
                    try:
                        # Upload to Supabase storage
                        with open(fig_path, 'rb') as f:
                            storage_path = f"{pid}/fig{fig['n']:02d}.png"
                            supabase.storage.from_('figures').upload(
                                storage_path, f.read(),
                                file_options={"content-type": "image/png"}
                            )
                        # Get public URL
                        public_url = supabase.storage.from_('figures').get_public_url(storage_path)
                        fig['url'] = public_url
                        uploaded_figs.append(fig)
                    except Exception as e:
                        print(f"Warning: Could not upload {storage_path}: {e}")
            paper['figures'] = uploaded_figs

        # Upload full text if available
        if paper.get('text_parts', 0) > 0:
            for k in range(paper['text_parts']):
                text_file = WORK_DIR / pid / f"text_{k}.txt"
                if text_file.exists():
                    try:
                        with open(text_file) as f:
                            text_data = {'text': f.read()}
                        supabase.table('fulltext').upsert({
                            'id': f"{pid}__{k}",
                            'arxiv_id': pid,
                            'part': k,
                            **text_data
                        }).execute()
                    except Exception as e:
                        print(f"Warning: Could not write fulltext {pid}__{k}: {e}")

        # Upsert paper
        try:
            # Set state to 'week' for new papers
            if 'state' not in paper:
                paper['state'] = 'week'

            response = supabase.table('papers').upsert(paper).execute()
            if response.data:
                added += 1
                print(f"✓ {pid}: {paper['title'][:60]}")
            else:
                updated += 1
        except Exception as e:
            errors.append(f"{pid}: {str(e)}")
            print(f"✗ {pid}: {e}")

    return added, updated, errors

def record_run(fetch_data, extracted_count, added, updated, errors):
    """Record run statistics"""
    today = datetime.now(timezone.utc).date().isoformat()

    feed_info = fetch_data.get('feed_updated', {}) if fetch_data else {}
    feeds_ok = list(feed_info.keys()) if feed_info else []

    run_record = {
        'date': today,
        'at': datetime.now(timezone.utc).isoformat(),
        'feeds_ok': feeds_ok,
        'feeds_failed': [],
        'fetched': len(fetch_data.get('papers', [])) if fetch_data else 0,
        'kept': len(fetch_data.get('papers', [])) if fetch_data else 0,
        'added': added,
        'extracted': extracted_count,
        'updated': updated,
        'errors': errors
    }

    try:
        supabase.table('runs').upsert(run_record).execute()
        print(f"\n✓ Run recorded: {added} added, {extracted_count} extracted")
    except Exception as e:
        print(f"Warning: Could not record run: {e}")

def main():
    print("Research Desk Daily Update")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}\n")

    # Step 1: Fetch
    fetch_data, fetch_error = run_fetcher()
    if fetch_error:
        print(f"\nFetch failed: {fetch_error}")
        record_run(None, 0, 0, 0, [fetch_error['error']])
        sys.exit(1)

    if not fetch_data.get('papers'):
        print("\nNo new papers to process")
        record_run(fetch_data, 0, 0, 0, [])
        return

    # Step 2: Load existing + extract
    existing_papers = load_existing_papers()
    extracted_data, extract_count = run_extraction(fetch_data, existing_papers)

    # Step 3: Write to Supabase
    added, updated, errors = write_to_supabase(fetch_data, extracted_data)

    # Record run
    record_run(fetch_data, extract_count, added, updated, errors)

    print(f"\nCompleted: {datetime.now(timezone.utc).isoformat()}")
    print(f"Summary: {added} papers added, {extract_count} extracted")
    if errors:
        print(f"Errors: {len(errors)}")
        for err in errors[:5]:
            print(f"  - {err}")

if __name__ == '__main__':
    main()
