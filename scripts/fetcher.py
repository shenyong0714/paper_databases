"""Research Desk fetch+score. Usage: python3 fetcher.py keywords.json out.json
Reads rss.arxiv.org Atom feeds, keeps announce types in config, scores with config groups.
Exit 2 (and prints FETCH_ANOMALY) when feeds carried entries but none survived parsing --
on 2026-09-23 a parser read announce_type from <category> instead of <arxiv:announce_type>,
dropped all 53 entries and recorded fetched 0 as a healthy run."""
import urllib.request, xml.etree.ElementTree as ET, re, time, json, sys, collections
VERSION = 1
cfg = json.load(open(sys.argv[1])); out = sys.argv[2]
cfg = cfg.get("data", cfg)
A = "{http://www.w3.org/2005/Atom}"; AX = "{http://arxiv.org/schemas/atom}"; DC = "{http://purl.org/dc/elements/1.1/}"
def rx(t, gap=0):
    # gap > 0: up to `gap` other words may sit between the term's words
    # ("rhombohedral graphene" with gap 3 also matches "rhombohedral-stacked pentalayer graphene")
    sep = r"(?:[\s\-]+[^\s\-]+){0,%d}?[\s\-]+" % gap if gap else r"[\s\-]*"
    return re.compile(r"\b" + sep.join(re.escape(w) for w in re.split(r"[\s\-]+", t)) + r"(?:s|e|es)?\b", re.I)
groups = [(g["w"], [(t, rx(t, int(g.get("gap") or 0))) for t in g["terms"]])
          for g in cfg["groups"] if g.get("enabled", True) and g.get("terms")]
ents = {}; ok = []; bad = []; raw = 0; types = collections.Counter(); feed_updated = {}
for i, cat in enumerate(cfg["categories"]):
    if i: time.sleep(3)
    try:
        req = urllib.request.Request(f"https://rss.arxiv.org/atom/{cat}",
              headers={"User-Agent": "july-digest/1.0 (+mailto:shenyongye0714@gmail.com)"})
        root = ET.fromstring(urllib.request.urlopen(req, timeout=30).read())
        feed_updated[cat] = root.findtext(A + "updated")
        for e in root.findall(A + "entry"):
            raw += 1
            at = (e.findtext(AX + "announce_type") or "").strip()
            types[at] += 1
            if at not in cfg["announce_types"]: continue
            aid = re.sub(r"v\d+$", "", e.findtext(A + "id").split(":")[-1])
            if aid in ents: continue
            ab = re.sub(r"^.*?Abstract:\s*", "", e.findtext(A + "summary") or "", flags=re.S).strip()
            c = e.find(A + "category")
            ents[aid] = dict(arxiv_id=aid, title=" ".join(e.findtext(A + "title").split()), abstract=ab,
                authors=[a.strip() for a in (e.findtext(DC + "creator") or "").split(",") if a.strip()],
                cat=c.get("term") if c is not None else cat)
        ok.append(cat)
    except Exception as ex:
        bad.append(cat); print(f"FEED_FAILED {cat}: {type(ex).__name__}: {ex}")
kept = []
for p in ents.values():
    txt = p["title"] + " " + p["abstract"]; s = 0; m = []
    for w, ts in groups:
        for t, r in ts:
            if r.search(txt): s += w; m.append(t); break
    if s >= cfg["min_score"]: p["score"] = s; p["matched"] = m; kept.append(p)
kept.sort(key=lambda p: -p["score"])
res = dict(fetcher_version=VERSION, feeds_ok=ok, feeds_failed=bad, raw_entries=raw,
           announce_types_seen=dict(types), feed_updated=feed_updated, fetched=len(ents), kept=kept)
json.dump(res, open(out, "w"))
print(f"raw {raw} types {dict(types)} fetched {len(ents)} kept {len(kept)} ok {ok} failed {bad}")
print("feed <updated>:", feed_updated)
for p in kept: print(f"[{p['score']}] {p['arxiv_id']} {p['title']} | {p['matched']}")
if not ok: print("ALL_FEEDS_FAILED"); sys.exit(3)
if raw > 0 and len(ents) == 0: print("FETCH_ANOMALY: feeds had entries but none parsed as new/cross"); sys.exit(2)
