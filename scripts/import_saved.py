#!/usr/bin/env python3
"""One-off: import saved papers from data/import_saved.json.

Each entry carries the arXiv id, the original saved_at time, score, matched keywords,
week and category. Title, abstract and authors are fetched from the arXiv API.
Rows are written with state='saved'; figures and text are left to run_daily.py's
extraction queue (run it with --extract-only afterwards).
"""
import os, sys, json, re, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from supabase import create_client

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
src = json.load(open(Path(__file__).resolve().parent.parent / 'data' / 'import_saved.json'))['papers']

ids = ",".join(p['arxiv_id'] for p in src)
req = urllib.request.Request(f"https://export.arxiv.org/api/query?id_list={ids}&max_results=100",
                             headers={"User-Agent": "research-desk/1.0 (+https://github.com/shenyong0714/paper_databases)"})
A, AX = "{http://www.w3.org/2005/Atom}", "{http://arxiv.org/schemas/atom}"
meta = {}
for e in ET.fromstring(urllib.request.urlopen(req, timeout=60).read()).findall(A + "entry"):
    aid = re.sub(r"v\d+$", "", e.findtext(A + "id").split("/abs/")[-1])
    meta[aid] = dict(title=" ".join(e.findtext(A + "title").split()),
                     abstract=" ".join(e.findtext(A + "summary").split()),
                     authors=[a.findtext(A + "name") for a in e.findall(A + "author")])

existing = {r['arxiv_id']: r for r in sb.table('papers').select('arxiv_id,state').execute().data}
ok, bad = 0, []
for p in src:
    aid = p['arxiv_id']
    if aid not in meta:
        bad.append(f"{aid}: not found on arXiv"); continue
    row = {**p, **meta[aid], 'state': 'saved'}
    if aid in existing:
        row = {'arxiv_id': aid, 'state': 'saved', 'saved_at': p['saved_at']}  # keep its other fields
    try:
        sb.table('papers').upsert(row).execute(); ok += 1
        print(f"✓ {aid}: {meta[aid]['title'][:70]}")
    except Exception as e:
        bad.append(f"{aid}: {e}")
print(f"\nimported {ok}/{len(src)}")
for b in bad: print("✗", b)
sys.exit(1 if bad else 0)
