#!/usr/bin/env python3
"""
Daily arXiv update script for GitHub Actions.

1. fetcher.py reads the arXiv RSS feeds and scores papers against data/keywords.json
2. new matches are written to the `papers` table (existing rows keep their state)
3. PDFs are downloaded and figures + full text extracted with extract_figs.extract()
   for every paper (new or already in the table) that has never been extracted;
   figures go to the public `figures` storage bucket, text to the `fulltext` table
4. a row is written to `runs`

Run with --extract-only to skip the fetch and only process the extraction queue.
"""
import os
import sys
import json
import time
import shutil
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
from pathlib import Path
from supabase import create_client, Client

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY environment variables required")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / 'data'
WORK_DIR = Path('/tmp/arxiv_work')
WORK_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(SCRIPT_DIR))
import extract_figs  # noqa: E402

UA = "research-desk/1.0 (+https://github.com/shenyong0714/paper_databases)"
MAX_EXTRACT = int(os.environ.get('MAX_EXTRACT', '25'))  # papers per run
PDF_PAUSE = 3          # seconds between arXiv PDF downloads (arXiv asks for politeness)
TEXT_CHUNK = 60000     # characters per fulltext row
ROW_FIELDS = ('arxiv_id', 'title', 'abstract', 'authors', 'cat', 'score', 'matched')
ET_TZ = ZoneInfo('America/New_York')
KEEP_WEEKS = 2         # 'This week' keeps the current and the previous week; older unsaved papers are deleted


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean(s):
    # Postgres text cannot hold NUL; some PDFs emit it in extracted text
    return (s or '').replace('\x00', '')


# ---- arXiv listing dates (US Eastern). arXiv announces at 20:00 ET Sun-Thu; a listing is
# labelled with the next day's date, which is when the morning digest picks it up.
def _weekday_back(d):
    return d - timedelta(days={5: 1, 6: 2}.get(d.weekday(), 0))   # Sat/Sun -> Fri


def listing_date_now():
    t = datetime.now(ET_TZ)
    d = t.date() + timedelta(days=1 if t.hour >= 20 else 0)
    return _weekday_back(d)


def listing_date_from_submission(ts):
    """Approximate listing date from the v1 submission time (14:00 ET cutoff, no holidays)."""
    t = ts.astimezone(ET_TZ)
    d = t.date()
    if d.weekday() >= 5 or t.hour >= 14:          # after cutoff or weekend -> next weekday's cutoff
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
    nxt = d + timedelta(days=1)                   # listed the day after the cutoff day
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def keep_from():
    """Monday of the oldest week still shown in 'This week'."""
    today = datetime.now(ET_TZ).date()
    return today - timedelta(days=today.weekday()) - timedelta(weeks=KEEP_WEEKS - 1)


def iso_week():
    y, w, _ = datetime.now(timezone.utc).isocalendar()
    return f"{y}-W{w:02d}"


# ---------------------------------------------------------------- step 1: fetch
def run_fetcher():
    print("=" * 60)
    print("STEP 1: Fetching from arXiv")
    print("=" * 60)

    output_file = WORK_DIR / 'fetch.json'
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / 'fetcher.py'),
         str(DATA_DIR / 'keywords.json'), str(output_file)],
        capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    if result.returncode == 2:
        return None, {"error": "FETCH_ANOMALY"}
    if result.returncode == 3:
        return None, {"error": "ALL_FEEDS_FAILED"}
    if result.returncode != 0:
        return None, {"error": f"fetcher exit {result.returncode}"}
    if not output_file.exists():
        return None, {"error": "fetch.json not created"}

    with open(output_file) as f:
        return json.load(f), None


# ---------------------------------------------------------------- step 2: write rows
def load_existing():
    rows = supabase.table('papers').select(
        'arxiv_id,state,score,figures,text_parts,extract_error,extracted_at,announced').execute().data
    return {r['arxiv_id']: r for r in rows}


def write_rows(kept, existing):
    print("\n" + "=" * 60)
    print("STEP 2: Writing papers")
    print("=" * 60)
    added, updated, errors = 0, 0, []
    week = iso_week()
    listed = listing_date_now().isoformat()
    for p in kept:
        row = {k: p[k] for k in ROW_FIELDS if k in p}
        is_new = p['arxiv_id'] not in existing
        if is_new:
            # only brand-new papers get a state; existing rows keep saved/read/etc.
            row.update(state='week', week=week, announced=listed)
        try:
            supabase.table('papers').upsert(row).execute()
            if is_new:
                added += 1
                existing[p['arxiv_id']] = {'arxiv_id': p['arxiv_id'], 'state': 'week',
                                           'score': p.get('score', 0), 'announced': listed}
                print(f"+ {p['arxiv_id']}: {p['title'][:70]}")
            else:
                updated += 1
        except Exception as e:
            errors.append(f"{p['arxiv_id']}: {e}")
            print(f"✗ {p['arxiv_id']}: {e}")
    print(f"{added} added, {updated} already present")
    return added, updated, errors


# ---------------------------------------------------------------- listing dates + pruning
def fill_announced(existing):
    """Give older rows (backfilled/imported) a listing date from their arXiv submission time."""
    todo = [pid for pid, r in existing.items() if not r.get('announced')]
    if not todo:
        return
    print(f"\nFilling listing dates for {len(todo)} papers")
    A = "{http://www.w3.org/2005/Atom}"
    for i in range(0, len(todo), 50):
        ids = ",".join(todo[i:i + 50])
        req = urllib.request.Request(f"https://export.arxiv.org/api/query?id_list={ids}&max_results=50",
                                     headers={"User-Agent": UA})
        try:
            root = ET.fromstring(urllib.request.urlopen(req, timeout=60).read())
        except Exception as e:
            print(f"  arXiv API failed: {e}"); return
        for e in root.findall(A + "entry"):
            pid = e.findtext(A + "id").split("/abs/")[-1].split("v")[0]
            pub = e.findtext(A + "published")
            if pid not in existing or not pub:
                continue
            d = listing_date_from_submission(datetime.fromisoformat(pub.replace("Z", "+00:00"))).isoformat()
            supabase.table('papers').update({'announced': d}).eq('arxiv_id', pid).execute()
            existing[pid]['announced'] = d
        time.sleep(PDF_PAUSE)


def prune_old(existing):
    """Delete unsaved papers listed before the oldest kept week, with their figures and text."""
    cutoff = keep_from().isoformat()
    old = [pid for pid, r in existing.items()
           if r.get('state') == 'week' and r.get('announced') and r['announced'] < cutoff]
    print(f"\nPruning unsaved papers listed before {cutoff}: {len(old)}")
    bucket = supabase.storage.from_('figures')
    for pid in old:
        try:
            files = [f"{pid}/{f['name']}" for f in (bucket.list(pid) or []) if f.get('name')]
            if files:
                bucket.remove(files)
            supabase.table('fulltext').delete().eq('arxiv_id', pid).execute()
            supabase.table('papers').delete().eq('arxiv_id', pid).eq('state', 'week').execute()
            existing.pop(pid, None)
            print(f"- {pid}")
        except Exception as e:
            print(f"  could not prune {pid}: {e}")
    return len(old)


# ---------------------------------------------------------------- step 3: extract
def extraction_queue(existing):
    """Papers never extracted, or whose last attempt failed. Saved papers first."""
    todo = [r for r in existing.values()
            if not r.get('extracted_at') or r.get('extract_error')]
    todo.sort(key=lambda r: (r.get('state') == 'week', -(r.get('score') or 0)))
    return todo[:MAX_EXTRACT], len(todo)


def extract_one(pid):
    pdir = WORK_DIR / pid
    shutil.rmtree(pdir, ignore_errors=True)
    pdir.mkdir(parents=True)
    pdf = pdir / f"{pid}.pdf"
    req = urllib.request.Request(f"https://arxiv.org/pdf/{pid}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        pdf.write_bytes(r.read())

    figs, text = extract_figs.extract(str(pdf), str(pdir))
    text = clean(text)

    bucket = supabase.storage.from_('figures')
    out_figs = []
    for f in figs:
        path = f"{pid}/fig{f['n']:02d}.png"
        with open(f['file'], 'rb') as fh:
            bucket.upload(path, fh.read(),
                          file_options={"content-type": "image/png", "upsert": "true"})
        url = bucket.get_public_url(path).rstrip('?')
        out_figs.append({"n": f['n'], "page": f['page'], "caption": clean(f['caption']), "url": url})

    parts = [text[i:i + TEXT_CHUNK] for i in range(0, len(text), TEXT_CHUNK)] if text.strip() else []
    for k, chunk in enumerate(parts):
        supabase.table('fulltext').upsert(
            {'id': f"{pid}__{k}", 'arxiv_id': pid, 'part': k, 'text': chunk}).execute()

    return out_figs, len(parts)


def run_extraction(existing):
    print("\n" + "=" * 60)
    print("STEP 3: Extracting figures and text")
    print("=" * 60)
    queue, total = extraction_queue(existing)
    print(f"{total} papers need extraction, doing {len(queue)} this run")
    done, errors = 0, []
    for i, r in enumerate(queue):
        pid = r['arxiv_id']
        if i:
            time.sleep(PDF_PAUSE)
        try:
            figs, n_parts = extract_one(pid)
            supabase.table('papers').update({
                'figures': figs, 'text_parts': n_parts,
                'extract_error': None, 'extracted_at': now_iso()}).eq('arxiv_id', pid).execute()
            done += 1
            print(f"✓ {pid}: {len(figs)} figures, {n_parts} text parts")
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            errors.append(f"{pid}: {msg}")
            print(f"✗ {pid}: {msg}")
            try:
                supabase.table('papers').update({
                    'extract_error': msg[:500], 'extracted_at': now_iso()}).eq('arxiv_id', pid).execute()
            except Exception as e2:
                print(f"  could not record error: {e2}")
        finally:
            shutil.rmtree(WORK_DIR / pid, ignore_errors=True)
    return done, errors


# ---------------------------------------------------------------- step 4: record
def record_run(fetch_data, added, updated, extracted, errors):
    fd = fetch_data or {}
    rec = {
        'date': datetime.now(timezone.utc).date().isoformat(),
        'at': now_iso(),
        'feeds_ok': fd.get('feeds_ok', []),
        'feeds_failed': fd.get('feeds_failed', []),
        'fetched': fd.get('fetched', 0),
        'kept': len(fd.get('kept', [])),
        'added': added,
        'extracted': extracted,
        'updated': updated,
        'errors': errors,
    }
    try:
        supabase.table('runs').upsert(rec).execute()
        print(f"\n✓ Run recorded: {added} added, {extracted} extracted, {len(errors)} errors")
    except Exception as e:
        print(f"Warning: could not record run: {e}")


def main():
    print("Research Desk Daily Update")
    print(f"Started: {now_iso()}\n")
    extract_only = '--extract-only' in sys.argv

    fetch_data, added, updated, errors = None, 0, 0, []
    existing = load_existing()

    if not extract_only:
        fetch_data, fetch_error = run_fetcher()
        if fetch_error:
            print(f"\nFetch failed: {fetch_error}")
            errors.append(fetch_error['error'])
        else:
            added, updated, errs = write_rows(fetch_data.get('kept', []), existing)
            errors += errs

    fill_announced(existing)
    if not extract_only:
        prune_old(existing)

    # extraction runs even if the fetch failed, so older papers still get figures
    extracted, errs = run_extraction(existing)
    errors += errs

    record_run(fetch_data, added, updated, extracted, errors)
    print(f"\nCompleted: {now_iso()}")
    # a failed fetch should show up red in the Actions tab
    if fetch_data is None and not extract_only:
        sys.exit(1)


if __name__ == '__main__':
    main()
