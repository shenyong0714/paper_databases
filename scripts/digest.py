"""Research Desk daily pipeline helper (stored in config/digest; run, never rewrite).

Why it exists: every Artifact/ArtifactData write from the scheduled task needs one
approval click from Shenyong. Uploading one fulltext.txt per paper made that 7-12
clicks a morning. Full text now goes into db docs fulltext/<id>__<k>, packed with
the paper rows and the run record into as few batch writes as possible, so a normal
day is: 1-2 PNG upload calls + 1 batch = 2-3 clicks.

Phases (S = scratchpad dir; all paths absolute):
  plan    S  -> reads S/fetch.json, S/papers_db/papers/*.json, S/cfg/config/extractor.json
                writes S/plan.json. exit 10 = nothing new and nothing stale (early exit).
  extract S  -> downloads + crops every queued paper with S/extract_figs.py, writes
                S/ext.json, prints the PNG paths in groups of <=25 (one upload call each).
  pack    S  -> reads S/uploads.txt (the upload tool results pasted verbatim, any order),
                optional S/runs/runs/<today>.json (existing run record), writes
                S/batch_<k>.json (<=50 entries each) and S/email.txt, prints both.
"""
import json, os, re, sys, glob, time, datetime, urllib.request
VERSION = 2
UA = "july-digest/1.0 (+mailto:shenyongye0714@gmail.com)"
CHUNK = 60000          # chars; worst case 4 B/char UTF-8 stays under the 256 KiB doc cap
MAX_QUEUE = 12
S = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else None
J = lambda *p: os.path.join(S, *p)
def load(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except FileNotFoundError: return d
def dump(o, p): json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False)
def iso_now(): return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def plan():
    fetch = load(J("fetch.json")); algo = load(J("cfg/config/extractor.json"))["version"]
    papers = {os.path.basename(f)[:-5]: load(f) for f in glob.glob(J("papers_db/papers/*.json"))}
    new = [p for p in fetch["kept"] if p["arxiv_id"] not in papers]
    def stale(p):
        cur = (+(p.get("fig_algo") or 0)) >= algo
        has_text = bool(p.get("text_url")) or (+(p.get("text_parts") or 0) > 0)
        if p.get("extract_error") and cur: return False
        return not has_text or "figures" not in p or not cur
    st = [p for p in papers.values() if stale(p)]
    wk = datetime.date.today().isocalendar(); week = f"{wk[0]}-W{wk[1]:02d}"
    q = [dict(arxiv_id=p["arxiv_id"], kind="stale", saved=p.get("state") != "week",
              score=p.get("score", 0), old_asset_ids=p.get("asset_ids", [])) for p in st]
    q.sort(key=lambda x: (not x["saved"], -x["score"]))
    q_new = [dict(arxiv_id=p["arxiv_id"], kind="new", saved=False, score=p["score"], old_asset_ids=[],
                  row={**{k: p[k] for k in ("arxiv_id","title","abstract","authors","cat","score","matched")},
                       "week": week, "state": "week"}) for p in new]
    rest = sorted(q_new + [x for x in q if not x["saved"]], key=lambda x: -x["score"])
    queue = ([x for x in q if x["saved"]] + rest)[:MAX_QUEUE]
    queued = {x["arxiv_id"] for x in queue}
    # new rows that did not fit in the queue are still written, just without figures
    unq_new = [x for x in q_new if x["arxiv_id"] not in queued]
    dump(dict(fig_algo=algo, week=week, queue=queue, new_unqueued=unq_new, n_new=len(new),
              n_stale=len(st), fetch={k: fetch[k] for k in ("feeds_ok","feeds_failed","raw_entries","fetched")},
              kept=len(fetch["kept"]), kept_rows=fetch["kept"]), J("plan.json"))
    print(f"NEW {len(new)}  STALE {len(st)}  queued {len(queue)}")
    for x in queue: print(f"  {x['kind']:5} {x['arxiv_id']} score {x['score']}{' (saved)' if x['saved'] else ''}")
    if not new and not st: print("EARLY_EXIT"); sys.exit(10)

def extract():
    sys.path.insert(0, S); import extract_figs
    pl = load(J("plan.json")); out = {}; pngs = []
    for i, x in enumerate(pl["queue"]):
        a = x["arxiv_id"]
        if i: time.sleep(3)
        try:
            pdf = J("pdf", f"{a}.pdf"); os.makedirs(J("pdf"), exist_ok=True)
            req = urllib.request.Request(f"https://arxiv.org/pdf/{a}", headers={"User-Agent": UA})
            open(pdf, "wb").write(urllib.request.urlopen(req, timeout=90).read())
            figs, _ = extract_figs.extract(pdf, J("ext", a))
            out[a] = dict(figs=[{k: f[k] for k in ("n","page","file","caption")} for f in figs],
                          text=J("ext", a, "fulltext.txt"))
            pngs += [os.path.abspath(f["file"]) for f in figs]
            print(f"{a}: {len(figs)} figures")
        except Exception as e:
            out[a] = dict(error=f"{type(e).__name__}: {e}"); print(f"{a}: EXTRACT_ERROR {type(e).__name__}: {e}")
    dump(out, J("ext.json"))
    for g in range(0, len(pngs), 25):
        print(f"UPLOAD_GROUP {g//25 + 1}: " + json.dumps(pngs[g:g+25]))
    if not pngs: print("NO_PNGS (skip the upload step)")

def pack():
    pl = load(J("plan.json")); ext = load(J("ext.json"), {}); now = iso_now()
    txt = open(J("uploads.txt"), encoding="utf-8").read() if os.path.exists(J("uploads.txt")) else ""
    up = {os.path.abspath(p): i for p, i in re.findall(r'"([^"]+\.png)"[^\n]*?\(id ([0-9a-f]{32})\)', txt)}
    writes, datadir, errors, zero, to_delete = [], J("batchdata"), [], [], []
    os.makedirs(datadir, exist_ok=True)
    def w(op, coll, doc, data):
        fp = os.path.join(datadir, f"{coll}__{doc}.json"); dump(data, fp)
        writes.append(dict(op=op, collection=coll, doc_id=doc, file_path=fp))
    extracted = recropped = 0
    for x in pl["queue"]:
        a = x["arxiv_id"]; e = ext.get(a)
        base = dict(x["row"]) if x["kind"] == "new" else {}
        if e is None or "error" in e:
            base["extract_error"] = (e or {}).get("error", "not extracted")
            errors.append(f"{a}: {base['extract_error']}")
        else:
            missing = [f["file"] for f in e["figs"] if os.path.abspath(f["file"]) not in up]
            if missing:
                base["extract_error"] = f"{len(missing)} figure uploads missing"
                errors.append(f"{a}: figure upload missing for {', '.join(os.path.basename(m) for m in missing)}")
            else:
                text = open(e["text"], encoding="utf-8").read()
                parts = [text[i:i+CHUNK] for i in range(0, len(text), CHUNK)] or [""]
                for k, t in enumerate(parts): w("set", "fulltext", f"{a}__{k}", {"arxiv_id": a, "k": k, "text": t})
                figs = sorted(e["figs"], key=lambda f: f["n"])
                base.update(figures=[dict(n=f["n"], page=f["page"], caption=f["caption"],
                                          url="/_blob/" + up[os.path.abspath(f["file"])]) for f in figs],
                            asset_ids=[up[os.path.abspath(f["file"])] for f in figs],
                            text_parts=len(parts), fig_algo=pl["fig_algo"], extracted_at=now)
                if x["kind"] != "new":
                    base["text_url"] = {"__delete__": True}; base["extract_error"] = {"__delete__": True}
                    to_delete += x["old_asset_ids"]; recropped += 1
                if not figs: zero.append(a)
                extracted += 1
        w("set" if x["kind"] == "new" else "update", "papers", a, base)
    for x in pl["new_unqueued"]: w("set", "papers", x["arxiv_id"], x["row"])
    pending = pl["n_stale"] + pl["n_new"] - len(pl["queue"])   # not yet attempted
    run = load(J("runs", "runs", f"{now[:10]}.json"), {}) or {}
    run.update(at=now, feeds_ok=pl["fetch"]["feeds_ok"], feeds_failed=pl["fetch"]["feeds_failed"],
               raw_entries=pl["fetch"]["raw_entries"], fetched=pl["fetch"]["fetched"], kept=pl["kept"],
               added=pl["n_new"], extracted=extracted, recropped=recropped, pending=max(pending, 0),
               zero_figures=zero, errors=list(run.get("errors", [])) + errors, digest_version=VERSION)
    w("set", "runs", now[:10], run)
    # Old assets of a re-cropped paper are NOT deleted here: Artifact asset deletes
    # go one call (= one approval click) per file. They are recorded instead, in the
    # same batch, for a bulk cleanup later.
    if to_delete: w("set", "orphans", now.replace(":", ""), {"asset_ids": to_delete, "reason": "recrop", "at": now})
    for f in glob.glob(J("batch_*.json")): os.remove(f)
    for b in range(0, len(writes), 50):
        dump(writes[b:b+50], J(f"batch_{b//50 + 1}.json"))
        print(f"BATCH {b//50 + 1} ({len(writes[b:b+50])} writes): " + json.dumps(writes[b:b+50]))
    # the email
    L = [f"{pl['n_new']} new papers, {extracted} extracted, {recropped} re-cropped, {max(pending,0)} still pending"
         + (f", {len(errors)} failures" if errors else "")]
    for p in sorted(pl["kept_rows"], key=lambda p: -p["score"]):
        if p["arxiv_id"] in {x["arxiv_id"] for x in pl["queue"] if x["kind"] == "new"} | {x["arxiv_id"] for x in pl["new_unqueued"]}:
            au = ", ".join(p["authors"][:4]) + (" et al." if len(p["authors"]) > 4 else "")
            L += [f"[{p['score']}] {p['title']}", f"        {au} · {p['cat']} · https://arxiv.org/abs/{p['arxiv_id']}",
                  f"        matched: {', '.join(p['matched'])}"]
    if zero: L.append("Zero figures (text stored): " + ", ".join(zero))
    for e in errors: L.append("FAILED " + e)
    if not pl["queue"] and not pl["n_new"] and not errors: L = ["No new papers; nothing to extract."]
    open(J("email.txt"), "w").write("\n".join(L)); print("EMAIL\n" + "\n".join(L))

if __name__ == "__main__":
    {"plan": plan, "extract": extract, "pack": pack}[sys.argv[1]]()
