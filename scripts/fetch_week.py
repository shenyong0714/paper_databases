#!/usr/bin/env python3
"""
Fetch papers from the past week using arXiv API with rate limiting.
Usage: python fetch_week.py keywords.json out.json [days]
"""
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
import json
import sys
import time
from datetime import datetime, timedelta

def rx(t):
    return re.compile(r"\b" + r"[\s\-]*".join(re.escape(w) for w in re.split(r"[\s\-]+", t)) + r"(?:s|e|es)?\b", re.I)

def fetch_arxiv_category(category, days_back=7, max_results=100, retries=3):
    """Fetch recent papers from a category with retry logic"""
    base_url = "http://export.arxiv.org/api/query"

    # Build query for this category
    query = f"cat:{category}"
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending"
    }

    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    # Retry logic for rate limiting
    last_error = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "research-desk/1.0"
            })
            response = urllib.request.urlopen(req, timeout=60).read()
            root = ET.fromstring(response)

            # Parse namespace
            ns = {'atom': 'http://www.w3.org/2005/Atom',
                  'arxiv': 'http://arxiv.org/schemas/atom'}

            entries = []
            cutoff_date = datetime.now() - timedelta(days=days_back)

            for entry in root.findall('atom:entry', ns):
                # Get published date
                published = entry.findtext('atom:published', namespaces=ns)
                if published:
                    pub_date = datetime.strptime(published[:10], '%Y-%m-%d')
                    if pub_date < cutoff_date:
                        continue

                # Get arXiv ID
                arxiv_id = entry.findtext('atom:id', namespaces=ns)
                if arxiv_id:
                    arxiv_id = arxiv_id.split('/abs/')[-1]
                    arxiv_id = re.sub(r'v\d+$', '', arxiv_id)

                # Get title and abstract
                title = entry.findtext('atom:title', namespaces=ns) or ""
                title = " ".join(title.split())

                summary = entry.findtext('atom:summary', namespaces=ns) or ""
                summary = " ".join(summary.split())

                # Get authors
                authors = []
                for author in entry.findall('atom:author', ns):
                    name = author.findtext('atom:name', namespaces=ns)
                    if name:
                        authors.append(name.strip())

                # Get primary category
                primary_cat = entry.find('arxiv:primary_category', ns)
                cat = primary_cat.get('term') if primary_cat is not None else category

                entries.append({
                    'arxiv_id': arxiv_id,
                    'title': title,
                    'abstract': summary,
                    'authors': authors,
                    'cat': cat,
                    'published': published
                })

            return entries, None

        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 10  # 10, 20, 30 seconds
                print(f"  Attempt {attempt + 1}/{retries} failed: {e}")
                print(f"  Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                return [], f"{type(e).__name__}: {e}"

    return [], f"All retries failed: {last_error}"

def main():
    if len(sys.argv) < 3:
        print("Usage: python fetch_week.py keywords.json out.json [days]")
        sys.exit(1)

    keywords_file = sys.argv[1]
    output_file = sys.argv[2]
    days_back = int(sys.argv[3]) if len(sys.argv) > 3 else 7

    # Load keywords config
    with open(keywords_file) as f:
        cfg = json.load(f)

    cfg = cfg.get("data", cfg)

    # Build scoring groups
    groups = [(g["w"], [(t, rx(t)) for t in g["terms"]]) for g in cfg["groups"]]

    print(f"Fetching papers from past {days_back} days...")
    print(f"Categories: {cfg['categories']}")
    print(f"Note: arXiv API has strict rate limits. This may take a while...")
    print()

    all_papers = {}
    ok_cats = []
    failed_cats = []

    for i, category in enumerate(cfg["categories"]):
        if i > 0:
            # Wait between categories to respect rate limits
            wait = 5
            print(f"\nWaiting {wait}s to respect arXiv rate limits...")
            time.sleep(wait)

        print(f"\nFetching {category}...")
        # Fetch fewer papers per request to avoid timeouts
        entries, error = fetch_arxiv_category(category, days_back=days_back, max_results=100)

        if error:
            print(f"  ERROR: {error}")
            failed_cats.append(category)
            continue

        ok_cats.append(category)
        print(f"  Found {len(entries)} papers")

        for entry in entries:
            aid = entry['arxiv_id']
            if aid not in all_papers:
                all_papers[aid] = entry

    print(f"\nTotal unique papers: {len(all_papers)}")

    # Score and filter papers
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

    result = {
        'fetcher_version': 2,
        'days_back': days_back,
        'categories_ok': ok_cats,
        'categories_failed': failed_cats,
        'fetched': len(all_papers),
        'kept': kept
    }

    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\nResults:")
    print(f"  Fetched: {len(all_papers)}")
    print(f"  Kept (score >= {cfg['min_score']}): {len(kept)}")
    print(f"  Output: {output_file}")

    if kept:
        print(f"\nTop papers:")
        for p in kept[:5]:  # Show top 5
            print(f"  [{p['score']}] {p['arxiv_id']} - {p['title'][:70]}...")

if __name__ == '__main__':
    main()
